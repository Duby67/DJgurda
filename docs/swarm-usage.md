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
  --pretty
```

### Start An Autonomous Swarm Run

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  start_autonomous_swarm_run `
  --prompt "Исправить удаление исходного сообщения при multi-link routing" `
  --path src/bot/processing/media_router.py `
  --pretty
```

### Continue A Swarm Run

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  continue_swarm_run `
  --run-id demo-media-router `
  --pretty
```

### Check Run Status

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  show_run_status `
  --run-id demo-media-router `
  --human
```

### Show Job Queue

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  show_job_queue `
  --run-id demo-media-router `
  --human
```

### Show Diff Preview

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  show_diff_preview `
  --run-id demo-media-router `
  --human
```

### Preview Sandbox Plan

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  preview_sandbox_plan `
  --run-id demo-media-router `
  --human
```

### Run Dispatcher Helper

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  run_dispatcher `
  --run-id demo-media-router `
  --pretty
```

Команда не заменяет executor.
Она подбирает следующий claimable external job и возвращает work item для Codex-style handoff.

### Approval Wrappers

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  approve_run_checks `
  --run-id demo-media-router `
  --pretty
```

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  approve_commit `
  --run-id demo-media-router `
  --pretty
```

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  reject_checkpoint `
  --run-id demo-media-router `
  --checkpoint run_checks `
  --note "Нужна доработка контекста" `
  --pretty
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
- `start_autonomous_swarm_run` делает то же самое, но сразу доводит run до первого external handoff или human boundary
- `preview_sandbox_plan` и `show_diff_preview` дают CLI-first UX без ручного чтения JSON и patch-файлов
- `show_run_status --human`, `show_job_queue --human` и `show_diff_preview --human` пишут `run-status.md`, `job-queue.md` и `diff-preview.md` прямо в run bundle
- `run_dispatcher` помогает снять ручной шов на уровне UX, но опирается на общий executor/job contract
- если verification profile требует реальный sandbox, executor по умолчанию выберет `docker`
- `local_dry_run` остается явным preview-режимом, а `github_actions` доступен как explicit remote adapter
- `commit`, `push`, merge и release promotion вверх по веткам выполняются только по явному запросу разработчика
- реальные тесты и smoke-прогоны все еще требуют явного approval пользователя

## Recommended Daily Flow

Обычный ежедневный путь работы выглядит так:

1. Сначала спланировать задачу через `scripts.agents.mcp plan_task`.
2. Запустить orchestration через `scripts.agents.mcp start_autonomous_swarm_run`, а `start_swarm_run` оставить как более низкоуровневый controlled entrypoint.
3. Проверять progress через `show_run_status`, очередь ролей через `show_job_queue`, а изменения через `show_diff_preview`.
4. Для sandbox intent использовать `preview_sandbox_plan`.
5. После approval или других ручных шагов возобновлять orchestration через `scripts.agents.mcp continue_swarm_run`.
6. Для внешних AI-ролей использовать `run_dispatcher` как UX helper или низкоуровневые `claim_role_job` / `complete_role_job` / `fail_role_job`.
7. Для approval checkpoints использовать wrappers `approve_run_checks`, `approve_commit`, `reject_checkpoint` или request-команды, когда нужен полный approval packet.
8. Для продвижения preview и release использовать `scripts.release.automation.promote`.

## Related Docs

- `scripts/AGENTS.md`
- `docs/release-flow.md`
- `docs/agent-context-map.md`
- `docs/testing-policy.md`
- `docs/commit-policy.md`
- `docs/sandbox-execution.md`
- `docs/swarm-runtime.md`
- `docs/verification-profiles.json`
