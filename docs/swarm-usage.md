# Swarm Usage

## Purpose

Этот документ кратко описывает, как запускать swarm-oriented automation в репозитории и какие команды являются основными точками входа в текущем Phase 3 контуре.

## Prerequisites

Перед использованием automation-контура ожидается:

- активный проектный `venv` или явный запуск через `.\venv\Scripts\python.exe`
- установленные dev-зависимости из `requirements-dev.txt`
- работа из корня репозитория

Swarm run bundles и lifecycle artifacts сохраняются в корневую папку `runs/`.

## Main Entry Points

Основной front door:

- `python -m scripts.agents.mcp`

Нижележащие module-path команды:

- `python -m scripts.agents.routing.route`
- `python -m scripts.agents.routing.plan`
- `python -m scripts.agents.routing.run`
- `python -m scripts.agents.lifecycle.execute`
- `python -m scripts.agents.lifecycle.status`
- `python -m scripts.release.automation.promote`
- `python -m scripts.release.automation.sync`

`scripts.agents.mcp` строит run bundle, создает isolated workspace, инициирует role jobs и служит основным пользовательским входом для swarm orchestration.

## Common Commands

### Plan A Task

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  plan_task `
  --prompt "Исправить release flow документацию" `
  --path docs/release-flow.md `
  --pretty
```

### Start A Swarm Run

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  start_swarm_run `
  --prompt "Исправить удаление исходного сообщения при multi-link routing" `
  --path src/bot/processing/media_router.py `
  --sandbox-adapter local_dry_run `
  --pretty
```

### Check Run Status

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  show_run_status `
  --run-id demo-media-router `
  --human
```

### Claim And Complete An External Role Job

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  claim_role_job `
  --run-id demo-media-router `
  --job-id coder `
  --claimed-by external-runtime
```

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  complete_role_job `
  --run-id demo-media-router `
  --job-id coder `
  --sandbox-adapter local_dry_run `
  --result-json "{\"summary\":\"changes applied\",\"applied_files\":[\"docs/swarm-usage.md\"]}"
```

### Preview Promotion To Dev

```powershell
.\venv\Scripts\python.exe -m scripts.release.automation.promote `
  --source-branch swarm-dev `
  --target-branch dev `
  --target-kind preview `
  --human
```

### Stable Promotion To Main

```powershell
.\venv\Scripts\python.exe -m scripts.release.automation.promote `
  --source-branch dev `
  --target-branch main `
  --target-kind stable `
  --human
```

### Validate Release Sync

```powershell
.\venv\Scripts\python.exe -m scripts.release.automation.sync --tag v1.2.4
```

## Approval Boundaries

Важно помнить:

- route/plan/status можно использовать как безопасные read-oriented команды
- lifecycle-этапы после planning могут менять run artifacts
- `start_swarm_run` создает `workspace.json`, `jobs/index.json` и другие orchestration artifacts в `runs/<run-id>/`
- `local_dry_run` строит sandbox preview, а `docker` является реальным execution backend для sandbox-проверок
- `commit`, `push`, merge и release promotion вверх по веткам выполняются только по явному запросу разработчика
- реальные тесты и smoke-прогоны все еще требуют явного approval пользователя

## Recommended Daily Flow

Обычный ежедневный путь работы выглядит так:

1. Сначала спланировать задачу через `scripts.agents.mcp plan_task`.
2. Запустить orchestration через `scripts.agents.mcp start_swarm_run`.
3. Проверять progress и blockers через `scripts.agents.mcp show_run_status`.
4. Для внешних AI-ролей использовать `claim_role_job` / `complete_role_job` / `fail_role_job`.
5. Для продвижения preview и release использовать `scripts.release.automation.promote`.

## Related Docs

- `scripts/AGENTS.md`
- `docs/release-flow.md`
- `docs/agent-context-map.md`
- `docs/testing-policy.md`
- `docs/commit-policy.md`
- `docs/sandbox-execution.md`
- `docs/verification-profiles.json`
