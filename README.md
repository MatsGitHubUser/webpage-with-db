# webpage-with-db

A page about *Così fan tutte* with a comment wall. Visitors are asked for their
name, then they can read and write comments, which are saved in Azure Table
Storage.

- **App:** [Streamlit](https://streamlit.io) (Python), in `app/`
- **Storage:** Azure Table Storage. Locally, the [Azurite](https://github.com/Azure/Azurite) emulator in Docker
- **Hosting:** Azure Container Apps, deployed with Terraform from GitHub Actions

## Develop locally

```sh
docker compose up -d --build   # app on http://localhost:8501, Azurite tables on localhost:10002
docker compose logs -f app     # follow the app log
docker compose down            # stop (comments are kept in the tabledata volume)
docker compose down -v         # stop and delete the local comments
```

Edits in `app/` reload automatically. Restart with `docker compose up -d --build`
after changing `app/requirements.txt`.

Run the tests (they use their own in-memory Azurite, not your local comments):

```sh
docker compose --profile test run --rm --build test
docker compose --profile test down -v
```

## Set up Azure and GitHub (once)

1. Create the GitHub repository, push `main`, and let the first `service` workflow run finish.
2. Make the package public: repository > Packages > package settings > Change visibility. Azure pulls the image anonymously.
3. Run `az login` and `gh auth login`, then `scripts/bootstrap-azure.sh OWNER/REPO`.

The workflow signs in to Azure with OIDC, so no secrets are stored in GitHub.
Terraform passes the storage account's connection string to the app as a
Container App secret. It is also in the Terraform state file, in the private
state storage account.

## Start, stop, check

```sh
gh workflow run service -f action=start   # deploys the current main, also use this to update
gh workflow run service -f action=stop    # removes the web app; comments are kept
gh run watch                              # follow the run; the URL is in the run summary
```

```sh
az containerapp show -g rg-webpagedb -n ca-webpagedb --query properties.configuration.ingress.fqdn -o tsv
curl https://<that-address>/_stcore/health   # prints: ok
```

The first request after a quiet period can take 20–30 s while the app scales up from zero.

A push to `main` runs the tests and publishes the image. It does not change
what is running in Azure until the next `start`.

## Costs

- Table Storage costs a few cents a month for a site this size. It is always on; there is nothing to pause.
- The web app costs little when idle because it scales to zero. `stop` removes it completely.
- To remove everything: `az group delete -n rg-webpagedb` (this deletes the comments).
  Terraform refuses to delete the storage account on its own, to protect the comments.
