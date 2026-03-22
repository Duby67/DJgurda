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
  - зарезервирован как будущий adapter и пока возвращает `blocked`.

## Current Operational Rules

- `docker` сейчас является единственным реальным execution backend внутри swarm-контура;
- `local_dry_run` полезен для preview, smoke orchestration и fallback-сценариев, но не заменяет реальную verification execution;
- при недоступности Docker sandbox-run должен завершаться явным blocked-state, а не молча деградировать;
- sandbox работает поверх isolated workspace, а не поверх основного корня репозитория;
- сетевой доступ в Docker sandbox выключен по умолчанию;
- env/secrets должны передаваться только через явный allowlist.

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
