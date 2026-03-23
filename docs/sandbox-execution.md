# Sandbox Execution

## Purpose

Этот документ фиксирует, когда и как swarm-контур должен использовать isolated execution.

## When Sandbox Is Required

Sandbox обязателен или предпочтителен, если:

- verification зависит от cookies, secrets, сети или внешних сервисов;
- проверка может менять локальное окружение или требует отдельной ОС/toolchain;
- проверка долгая, шумная или unsafe для основного workspace;
- задача затрагивает deploy, infra или другие environment-sensitive paths.

## What Runs There

В sandbox обычно уносятся:

- environment-sensitive tests;
- интеграционные проверки;
- smoke-пути, требующие operational artifacts;
- диагностика, которая не должна загрязнять основной workspace.

## Current Adapter Model

Текущая реализация поддерживает:

- `local_dry_run`
  - строит machine-readable preview sandbox plan и command logs без реального исполнения;
- `docker`
  - выполняет verification-команды в isolated container;
- `github_actions`
  - remote adapter через `workflow_dispatch + poll`, не используемый по умолчанию.
  - использует `.github/workflows/swarm-sandbox.yml` как live workflow entrypoint;
  - опирается на correlation id и artifact download, а не только на branch-based polling.
  - требует существующий workflow entrypoint `swarm-sandbox.yml`, настроенный `gh` и доступ к workflow artifacts.
  - если run уже материализовал `workspace-diff.patch`, adapter пытается передать его в workflow и воспроизвести exact run state перед remote verification.
  - large diff теперь передаются через chunked-inline payload до bounded upper limit вместо немедленного hard-block на одном field.
  - после первого точного match по correlation id adapter закрепляется на одном `workflow_run_id` и перестает каждый раз выбирать run заново из списка ветки.

## Current Operational Rules

- `docker` сейчас является единственным реальным execution backend внутри swarm-контура;
- для `docker` sandbox и container-based test flows Docker на хосте обязателен;
- для `github_actions` adapter на хосте должны быть доступны `gh`, действующая auth-сессия и доступ к Actions API целевого репозитория;
- `github_actions` adapter должен уметь скачать workflow artifacts обратно в локальный run bundle;
- `local_dry_run` полезен для preview, smoke orchestration и fallback-сценариев, но не заменяет реальную verification execution;
- при недоступности Docker sandbox-run должен завершаться явным blocked-state, а не молча деградировать;
- при недоступности `gh`, auth или workflow entrypoint `github_actions` adapter должен завершаться явным blocked-state;
- sandbox работает поверх isolated workspace, а не поверх основного корня репозитория;
- сетевой доступ в Docker sandbox выключен по умолчанию;
- env/secrets должны передаваться только через явный allowlist.
- sandbox image для тестов должен жить в тестовом слое, а не в `deploy/`; текущий image build context описан в `test/docker/swarm-test/`.
- `github_actions` live-path должен материализовать downloadable workflow artifacts, а не ограничиваться только status polling.
- при отсутствии workflow artifact download или при mismatch correlation id remote run должен считаться `blocked`, а не успешным.
- при передаче `workspace-diff.patch` remote workflow должен либо подтвердить его применение через `workspace-transfer.json`, либо завершиться как `blocked`.

## Expected Sandbox Result

`sandbox-result.json` должен по возможности возвращать:

- `conclusion`;
- краткую `summary`;
- список checks и их статусы;
- logs;
- machine-readable reports;
- failure artifacts или ссылки на них;
- описание среды исполнения.

## Security Rules

- В sandbox нельзя передавать лишние секреты.
- Предпочитать short-lived credentials и минимально необходимые permissions.
- Публикация artifacts, release action и любые destructive remote steps должны быть выключены по умолчанию.
- Sandbox не должен превращаться в обход approval boundaries.

## Related Docs

- `docs/SECURITY.md`
- `docs/RELIABILITY.md`
- `docs/testing-policy.md`
- `docs/swarm-usage.md`
- `test/docker/swarm-test/README.md`
