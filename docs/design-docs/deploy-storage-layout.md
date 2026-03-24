# Deploy And Storage Layout

## Purpose

Этот файл описывает, как организованы deploy, cookies, database paths и runtime temp storage.

## Main Rules

- Runtime database и cookies монтируются в контейнер.
- Runtime temp files живут внутри контейнера под `src/data/runtime`.
- `deploy/cookies` служит deploy-side materialization area и не должен хранить tracked secrets.
- В tracked-слое `deploy/cookies` должны оставаться только placeholder docs вроде `README.md` и `AGENTS.md`.
- Runtime должен сам создавать и очищать temp storage.
- `deploy/manager.sh` должен оставаться совместимым и с `dev`, и с `prod`.

## Key Path Contracts

- database path задается через `BOT_DB_PATH`;
- общая cookies directory задается через `COOKIES_DIR`;
- явные `*_COOKIES_PATH` переопределяют общую cookies directory;
- runtime temp storage остается под `/app/src/data/runtime` при containerized execution.

## Deploy Notes

- GitHub Actions может materialize `deploy/cookies` из optional secrets.
- Если secrets отсутствуют, deploy должен продолжаться с reuse уже существующих server-side cookies.
- `bot.db` живет вне контейнера и монтируется внутрь.
- Runtime temp storage больше не опирается на внешний `runtime` volume.

## Read Next

- `docs/RELIABILITY.md`
- `docs/SECURITY.md`
