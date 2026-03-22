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
