# CLAUDE.md

A page about *Così fan tutte* with a comment wall: a Streamlit (Python) app that
shows the opening of a Google Docs listening guide, then asks for a visitor's
name and lets them read and post comments stored in Azure Table Storage. It runs
locally in Docker Compose, with the Azurite emulator standing in for Table
Storage, and in Azure Container Apps. Terraform deploys it from GitHub Actions.
See [README.md](README.md) for the commands people run.

## How the files relate

```
                        app/requirements.txt ──┐
app/.streamlit/config.toml ─┐                  │
app/assets/ ────────────────┤                  │
app/db.py ◄── app/app.py ───┴──────────────────┴─► Dockerfile
   ▲                                                 │  stages: base → test
   │                                                 │          base → runtime
tests/conftest.py ◄── tests/test_db.py               │
   ▲              ◄── tests/test_app.py (runs app.py)│
   │                                                 │
requirements-dev.txt ──► Dockerfile (test stage)     │
.dockerignore ─────────► limits the build context    │
                                                     ▼
                        compose.yaml  (azurite + app → runtime image,
                                       testazurite + test → test image)
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
                                                         + Storage account (Table Storage)
```

The app finds its storage only through the environment variable
`AZURE_STORAGE_CONNECTION_STRING` (and optionally `COMMENTS_TABLE`, default
`comments`). Each environment sets it in its own place:
- local app: `compose.yaml`, service `app` (Azurite's public development account on `azurite`)
- tests: `compose.yaml`, service `test` (points at `testazurite`, in memory)
- Azure: `infra/main.tf`, the container's `env` block, from a Container App secret holding the storage account's connection string

## Which files are used where

| Area | Files |
|---|---|
| App, used everywhere | `app/app.py`, `app/db.py`, `app/assets/`, `app/requirements.txt`, `app/.streamlit/config.toml` |
| Image build, used locally and in CI | `Dockerfile`, `.dockerignore` |
| Local development and tests, also run by CI's `test` job | `compose.yaml`, `requirements-dev.txt`, `tests/` |
| CI/CD | `.github/workflows/service.yml` |
| Azure infrastructure, run only from the workflow's `deploy` job | `infra/main.tf`, `infra/variables.tf`, `infra/outputs.tf`, `infra/.terraform.lock.hcl` |
| One-time Azure and GitHub setup, run by hand | `scripts/bootstrap-azure.sh` |

## Important files

### App (`app/`)
- **`app/app.py`**: the Streamlit page. `show_guide()` always shows the text copied from the first page of the Google Doc (`GUIDE_URL`), the poster from `app/assets/`, and a link to the doc. Below it, a name form until `st.session_state.visitor_name` is set, then the comment section. It opens the table client once with `@st.cache_resource` and escapes all user text with `as_plain_markdown()` so it is never rendered as Markdown. When storage cannot be reached (`AzureError`) it shows an error message instead of crashing.
- **`app/db.py`**: all storage access, using `azure-data-tables`. `open_table()` connects and creates the table if needed, so there is no setup step. All comments are in one partition, and the RowKey counts down with time, so the table's natural order is newest first. `clean()` validates input against `MAX_NAME` and `MAX_BODY`, which the UI also uses for `max_chars`. `add_comment()` and `list_comments()` return `Comment` dataclasses.
- **`app/requirements.txt`**: pinned runtime dependencies (streamlit, azure-data-tables).
- **`app/.streamlit/config.toml`**: headless server on `0.0.0.0:8501`, usage stats off. Port 8501 is also hard-coded in `Dockerfile`, `compose.yaml`, `infra/main.tf` (`target_port`) and the CI smoke test.

### Build and local development
- **`Dockerfile`**: multi-stage. `base` installs the app. `test` adds pytest and `tests/` and sets `APP_DIR=/app`. `runtime` (the default target) runs as a non-root user with `streamlit run app.py`.
- **`.dockerignore`**: allow-list. Only `app/`, `tests/` and `requirements-dev.txt` go into the build context.
- **`compose.yaml`**: services `azurite` (tables only) and `app` for development. The app's `./app` folder is bind-mounted read-only and run-on-save is on, so code edits reload live. Comments are kept in the `tabledata` volume. The `test` profile adds `testazurite` (in memory, so it is thrown away) and `test`. CI runs this same profile.

### Tests (`tests/`)
- **`tests/conftest.py`**: puts `APP_DIR` on `sys.path` so `import db` works. Provides a session-scoped `table` fixture and an autouse fixture that deletes every comment before each test. The tests need Azurite, so run them through compose.
- **`tests/test_db.py`**: unit tests for `clean()`, ordering and validation.
- **`tests/test_app.py`**: end-to-end tests of `app.py` using `streamlit.testing.v1.AppTest`.

### CI/CD
- **`.github/workflows/service.yml`**: the only workflow.
  - On a **push to `main`** it runs `test` and then `build`. `build` builds the runtime image, smoke-tests `/_stcore/health` without any storage, and pushes `ghcr.io/<owner>/<repo>:<sha>`. A push does **not** deploy.
  - **`workflow_dispatch` with `action=start`** runs test, then build, then `deploy`. `deploy` runs `terraform apply` with `running=true` and the new image. Terraform signs in to Azure with OIDC through the `ARM_*` environment variables.
  - **`workflow_dispatch` with `action=stop`** skips test and build. It runs `terraform apply` with `running=false`, which removes the Container App. The comments stay in the storage account.
  - It reads the repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` and `TFSTATE_STORAGE_ACCOUNT`, which the bootstrap script sets. It uses no stored secrets apart from `GITHUB_TOKEN`.

### Azure infrastructure (`infra/`)
- **`infra/main.tf`**: uses the azurerm backend, configured by `-backend-config` flags in the workflow. It uses the existing resource group as a data source (it does not create it). It creates:
  - a storage account for the comments, `st<name><first 8 hex of sha1(subscription id)>`, with `prevent_destroy`. The app creates the table itself.
  - a Container App Environment, kept while stopped
  - a Container App with `count = var.running ? 1 : 0`, scaling 0 to 1 replicas, with the storage connection string as a secret
- **`infra/variables.tf`**: `running` and `image` drive start and stop. `location` (North Europe) is where the resources go, not the resource group's region (Sweden Central). Its description says why.
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
- Names are hard-coded in several files. `rg-webpagedb` appears in `variables.tf`, the bootstrap script and the README, and `rg-webpagedb-tfstate` in the workflow and the bootstrap script. Change them everywhere together.
- The Azure subscription is limited: one Container Apps environment in total (it is `cae-webpagedb`), Postgres Flexible Server sizes refused (`SkuNotAvailable`), and West Europe not accepting new customers. That is why the app uses Table Storage in North Europe.
- The CI identity is only a Contributor, so it cannot create role assignments. That is why the app uses a connection string rather than a managed identity.
- Table Storage has no schema. Adding a property to new comments is fine; old comments simply lack it.
- The guide text in `app/app.py` is a copy. Edits to the Google Doc don't reach the page until the code is updated.
- After changing `app/requirements.txt`, rebuild with `docker compose up -d --build`. Changes to `.py` files hot-reload.
- Run the tests with `docker compose --profile test run --rm --build test`, then `docker compose --profile test down -v`.
- The ghcr.io package must be public, because Azure pulls the image without credentials.
- Never commit `*.tfstate` or `*.tfvars` (they are in `.gitignore`). The state holds the storage account's keys.

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