# CLAUDE.md

A comment wall: a Streamlit (Python) app that asks for a visitor's name, then
lets them read and post comments stored in Postgres 17. It runs locally in Docker
Compose and in Azure Container Apps with Azure Database for PostgreSQL Flexible
Server. Terraform deploys it from GitHub Actions. See [README.md](README.md) for
the commands people run.

## How the files relate

```
                        app/requirements.txt ──┐
app/.streamlit/config.toml ─┐                  │
app/db.py ◄── app/app.py ───┴──────────────────┴─► Dockerfile
   ▲                                                 │  stages: base → test
   │                                                 │          base → runtime
tests/conftest.py ◄── tests/test_db.py               │
   ▲              ◄── tests/test_app.py (runs app.py)│
   │                                                 │
requirements-dev.txt ──► Dockerfile (test stage)     │
.dockerignore ─────────► limits the build context    │
                                                     ▼
                        compose.yaml  (db + app → runtime image,
                                       testdb + test → test image)
                                                     │
          ┌──────────────────────────────────────────┤
          ▼ LOCAL                                     ▼ CI/CD
   docker compose up                      .github/workflows/service.yml
   docker compose --profile test run test   job test   → compose test profile
                                            job build  → Dockerfile runtime → ghcr.io
                                            job deploy → infra/*.tf (terraform apply)
                                                              │
                         scripts/bootstrap-azure.sh ──────────┤ (once, by hand:
                         creates RG, tfstate storage,          │  resource groups,
                         OIDC identity, sets GitHub vars ─────►│  repo vars used by
                                                               ▼  the workflow)
                                                         Azure: Container App
                                                         + Postgres Flexible Server
```

The app code connects to the database only through the libpq environment
variables `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` and `PGSSLMODE`. Each
environment sets them in its own place:
- local app: `compose.yaml`, service `app` (`PGSSLMODE=disable`)
- tests: `compose.yaml`, service `test` (points at `testdb`)
- Azure: `infra/main.tf`, the container's `env` blocks (`PGSSLMODE=require`, password from a Container App secret)

## Which files are used where

| Area | Files |
|---|---|
| App, used everywhere | `app/app.py`, `app/db.py`, `app/requirements.txt`, `app/.streamlit/config.toml` |
| Image build, used locally and in CI | `Dockerfile`, `.dockerignore` |
| Local development and tests, also run by CI's `test` job | `compose.yaml`, `requirements-dev.txt`, `tests/` |
| CI/CD | `.github/workflows/service.yml` |
| Azure infrastructure, run only from the workflow's `deploy` job | `infra/main.tf`, `infra/variables.tf`, `infra/outputs.tf`, `infra/.terraform.lock.hcl` |
| One-time Azure and GitHub setup, run by hand | `scripts/bootstrap-azure.sh` |

## Important files

### App (`app/`)
- **`app/app.py`**: the Streamlit page. It shows a name form until `st.session_state.visitor_name` is set, then the comment page. It opens the connection pool once with `@st.cache_resource` and escapes all user text with `as_plain_markdown()` so it is never rendered as Markdown. When the database cannot be reached it shows an error message instead of crashing.
- **`app/db.py`**: all database access. `open_pool()` opens a `psycopg_pool.ConnectionPool` and runs `CREATE TABLE IF NOT EXISTS`, so there are no migrations. `clean()` validates input against `MAX_NAME` and `MAX_BODY`, which are also used in the table's `CHECK` constraints and the UI's `max_chars`. `add_comment()` and `list_comments()` return `Comment` dataclasses.
- **`app/requirements.txt`**: pinned runtime dependencies (streamlit, psycopg, psycopg-pool).
- **`app/.streamlit/config.toml`**: headless server on `0.0.0.0:8501`, usage stats off. Port 8501 is also hard-coded in `Dockerfile`, `compose.yaml`, `infra/main.tf` (`target_port`) and the CI smoke test.

### Build and local development
- **`Dockerfile`**: multi-stage. `base` installs the app. `test` adds pytest and `tests/` and sets `APP_DIR=/app`. `runtime` (the default target) runs as a non-root user with `streamlit run app.py`.
- **`.dockerignore`**: allow-list. Only `app/`, `tests/` and `requirements-dev.txt` go into the build context.
- **`compose.yaml`**: services `db` and `app` for development. The app's `./app` folder is bind-mounted read-only and run-on-save is on, so code edits reload live. Data is kept in the `pgdata` volume. The `test` profile adds `testdb` (on tmpfs, so it is thrown away) and `test`. CI runs this same profile.

### Tests (`tests/`)
- **`tests/conftest.py`**: puts `APP_DIR` on `sys.path` so `import db` works. Provides a session-scoped `pool` fixture and an autouse fixture that truncates `comments` before every test. The tests need a real Postgres, so run them through compose.
- **`tests/test_db.py`**: unit tests for `clean()`, ordering and validation.
- **`tests/test_app.py`**: end-to-end tests of `app.py` using `streamlit.testing.v1.AppTest`.

### CI/CD
- **`.github/workflows/service.yml`**: the only workflow.
  - On a **push to `main`** it runs `test` and then `build`. `build` builds the runtime image, smoke-tests `/_stcore/health` without a database, and pushes `ghcr.io/<owner>/<repo>:<sha>`. A push does **not** deploy.
  - **`workflow_dispatch` with `action=start`** runs test, then build, then `deploy`. `deploy` signs in to Azure with OIDC, starts Postgres if it is stopped, and runs `terraform apply` with `running=true` and the new image.
  - **`workflow_dispatch` with `action=stop`** skips test and build. It runs `terraform apply` with `running=false`, which removes the Container App, then pauses Postgres.
  - It reads the repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `TFSTATE_STORAGE_ACCOUNT` and `PG_SERVER_NAME`, which the bootstrap script sets. It uses no stored secrets apart from `GITHUB_TOKEN`.

### Azure infrastructure (`infra/`)
- **`infra/main.tf`**: uses the azurerm backend, configured by `-backend-config` flags in the workflow. It uses the existing resource group as a data source (it does not create it). It creates:
  - a Postgres Flexible Server and the `comments` database, both with `prevent_destroy`
  - a `random_password` for the database, kept only in Terraform state
  - a firewall rule that allows Azure services
  - a Container App Environment, kept while stopped
  - a Container App with `count = var.running ? 1 : 0`, scaling 0 to 1 replicas
- **`infra/variables.tf`**: `running` and `image` drive start and stop. `postgres_version` must stay in step with the image tag in `compose.yaml`.
- **`infra/outputs.tf`**: `url`, the public URL or `"stopped"`. The workflow prints it in the run summary.
- **`infra/.terraform.lock.hcl`**: provider lock file. Commit it whenever provider versions change.

### One-time setup
- **`scripts/bootstrap-azure.sh OWNER/REPO`**: safe to run again. It needs `az login` (Owner) and `gh auth login`. It:
  - registers resource providers, because the CI identity is not allowed to (see `resource_provider_registrations = "none"` in `main.tf`)
  - creates `rg-webpagedb` and `rg-webpagedb-tfstate` and the state storage account
  - creates an Entra app with a federated credential for `refs/heads/main`
  - gives it Contributor on the app resource group only, and Storage Blob Data Contributor on the state storage
  - sets the GitHub repository variables

## Conventions and gotchas
- Names are hard-coded in several files. `rg-webpagedb` appears in the workflow, `variables.tf` and the bootstrap script, and `rg-webpagedb-tfstate` in the workflow and the bootstrap script. Change them everywhere together.
- The schema is created at runtime in `db.SCHEMA`. If you change the table, existing databases (local `pgdata` and Azure) are not migrated automatically.
- After changing `app/requirements.txt`, rebuild with `docker compose up -d --build`. Changes to `.py` files hot-reload.
- Run the tests with `docker compose --profile test run --rm --build test`, then `docker compose --profile test down -v`.
- The ghcr.io package must be public, because Azure pulls the image without credentials.
- Never commit `*.tfstate` or `*.tfvars` (they are in `.gitignore`). The state holds the database password.

============== TEXT FROM .MD prompt =======================
I've written CLAUDE.md at the repo root. I haven't committed it. It has four parts:

How the files fit together: a diagram tracing the app code into the image build, then compose, then the two paths: local commands, and the GitHub workflow that builds the image, pushes it to GitHub's container registry and runs Terraform to deploy to Azure. It also shows how the one-time setup script feeds that workflow. One thread runs through it: the app connects to Postgres only through the standard PG* environment variables. Those are set in compose.yaml for local runs and tests, and in infra/main.tf for Azure.
Which files are used where: a table that splits the files into the app itself, the image build, local development and tests, CI/CD, Azure infrastructure, and one-time setup.
Important files: a short note on each one that matters.
Gotchas:
A push to main tests and builds the image but doesn't deploy. Only a manual start run does.
Resource-group names are hard-coded in several files.
Port 8501 is also hard-coded in several files.
The table is created when the app starts, and nothing migrates it if the schema changes.
The Postgres version has to match between compose and Terraform.
The image package on GitHub