# Test Docker Assets

`test/docker/` хранит контейнерные артефакты, которые используются только для тестов, smoke и swarm verification.

Здесь не должно быть server deploy image или deploy-side tooling.

Важно:

- для container-based tests Docker на хосте обязателен;
- без Docker эти сценарии должны либо не запускаться, либо честно переходить в `blocked` / `skip`.

Текущее содержимое:

- `swarm-test/` - test harness image для sandbox adapter и Docker smoke-сценариев.
