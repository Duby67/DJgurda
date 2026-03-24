# Swarm Test Image

`test/docker/swarm-test/` хранит Docker image для swarm verification и smoke-сценариев.

Этот образ не участвует в `deploy-dev` или `deploy-prod` workflows и не должен использоваться как серверный runtime-образ бота.

## What It Is For

- isolated verification в swarm sandbox;
- локальные и CI smoke-прогоны orchestration-контура;
- воспроизводимый test environment для `docker` sandbox adapter.

## Build Flow

Сборка должна идти из корня репозитория, чтобы образ получил доступ к `src/`, `scripts/`, `test/`, `docs/` и требованиям Python:

```bash
docker build -f test/docker/swarm-test/Dockerfile -t djgurda-swarm-test:latest .
```

Для этого рядом лежит отдельный `Dockerfile.dockerignore`, который:

- вырезает `runs/`, `venv/`, `.git/` и другие локальные артефакты;
- не тащит deploy-only слой из `deploy/`;
- оставляет только то, что нужно для swarm test image.

## Test Flow

Практический поток проверки такой:

1. Собирается `djgurda-swarm-test:latest`.
2. Swarm sandbox adapter запускает verification-команды внутри контейнера.
3. Локальные smoke-тесты могут проверять наличие и запуск этого image.
4. Результаты сохраняются в run artifacts, а не смешиваются с live deploy-контуром.

Предпосылка:

- Docker на локальном хосте обязателен для этого test flow;
- без Docker образ не собирается, а container-based verification не выполняется.

Если образ не собран заранее, честный Docker smoke path должен сначала попытаться собрать его, а уже потом выполнять live adapter path.

## Boundary Rule

- `deploy/` отвечает за реальные server deploy assets.
- `test/docker/` отвечает за test-only container assets.
- Если когда-нибудь появится отдельный server-side verification image, его лучше держать в отдельной подпапке с явным README, а не смешивать с `swarm-test`.
