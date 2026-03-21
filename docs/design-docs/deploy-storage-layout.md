# Deploy And Storage Layout

## Purpose

This file describes how deploy, cookies, database paths, and runtime temp storage are organized.

## Main Rules

- Runtime database and cookies are mounted into the container.
- Runtime temp files live under `src/data/runtime` inside the container.
- `local/cookies` is for local smoke and manual testing only.
- `deploy/cookies` is the deploy-side materialization area and should not store tracked secrets.
- Runtime should create and clean temp storage itself.
- `deploy/manager.sh` must stay compatible with both `dev` and `prod`.

## Key Path Contracts

- database path is driven by `BOT_DB_PATH`;
- shared cookies directory is driven by `COOKIES_DIR`;
- explicit `*_COOKIES_PATH` values override the shared cookies directory;
- runtime temp storage stays under `/app/src/data/runtime` in containerized execution.

## Deploy Notes

- GitHub Actions may materialize `deploy/cookies` from optional secrets.
- If secrets are missing, deploy should continue by reusing existing server-side cookies.
- `bot.db` lives outside the container and is mounted in.
- Runtime temp storage no longer relies on an external `runtime` volume.

## Read Next

- `docs/RELIABILITY.md`
- `docs/SECURITY.md`
