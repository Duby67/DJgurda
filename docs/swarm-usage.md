# Swarm Usage

## Purpose

Этот документ кратко описывает, как использовать swarm-oriented automation в репозитории и какие команды являются основными точками входа в текущем контуре.

## Prerequisites

Перед использованием automation-контура ожидается:

- активный проектный `venv` или явный запуск через `.\venv\Scripts\python.exe`
- установленные dev-зависимости из `requirements-dev.txt`
- работа из корня репозитория
- локальные `pytest`, smoke-checks и verification-команды нельзя запускать вне проектного `venv`

Для VS Code в репозитории рекомендован tracked workspace-файл [.vscode/settings.json](/c:/Work/djgurda/.vscode/settings.json).
Он фиксирует `venv\Scripts\python.exe` как repo-default interpreter и открывает терминал с активацией `venv` через `activate.bat`, что особенно полезно на Windows-хостах с ограниченным PowerShell `ExecutionPolicy`.

Важно: `python.defaultInterpreterPath` в VS Code работает как начальный default для workspace.
Если редактор уже сохранил другой interpreter selection, нужно вручную переуказать интерпретатор на `.\venv\Scripts\python.exe`.

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

`scripts.agents.mcp` строит run bundle, создает isolated workspace, инициирует role jobs и служит основным пользовательским входом для swarm orchestration.

## Common Commands

### Plan A Task

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  plan_task `
  --prompt "Усилить dispatcher loop после completion inbox" `
  --path scripts/agents/mcp/dispatcher.py `
  --pretty
```

### Start A Swarm Run

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  start_swarm_run `
  --prompt "Улучшить статус sandbox blocked state" `
  --path scripts/agents/lifecycle/status.py `
  --pretty
```

### Start An Autonomous Swarm Run

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  start_autonomous_swarm_run `
  --prompt "Усилить runtime context trace для reviewer handoff" `
  --path scripts/agents/runtime_trace.py `
  --pretty
```

### Start A Supervised Swarm Run

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  start_supervised_swarm_run `
  --prompt "Довести supervisor до следующей human boundary" `
  --path scripts/agents/mcp/dispatcher.py `
  --pretty
```

### Continue A Swarm Run

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  continue_swarm_run `
  --run-id demo-swarm-run `
  --pretty
```

### Check Run Status

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  show_run_status `
  --run-id demo-swarm-run `
  --human
```

### Show Job Queue

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  show_job_queue `
  --run-id demo-swarm-run `
  --human
```

### Show Diff Preview

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  show_diff_preview `
  --run-id demo-swarm-run `
  --human
```

### Preview Sandbox Plan

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  preview_sandbox_plan `
  --run-id demo-swarm-run `
  --human
```

### Run Dispatcher Helper

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  run_dispatcher `
  --run-id demo-swarm-run `
  --pretty
```

Команда не заменяет executor.
Она подбирает следующий claimable external job и возвращает work item для Codex-style handoff.

### Run Supervisor

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  run_supervisor `
  --run-id demo-swarm-run `
  --pretty
```

Supervisor крутит persistent loop и, если задан `--runtime-command-json`, может сам исполнять `coder` и `reviewer` через built-in runtime worker bridge.
Тот же runtime worker можно задать через env `SWARM_RUNTIME_COMMAND_JSON`.

### Approval Wrappers

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  approve_run_checks `
  --run-id demo-swarm-run `
  --pretty
```

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  approve_run_checks_and_continue `
  --run-id demo-swarm-run `
  --pretty
```

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  approve_commit `
  --run-id demo-swarm-run `
  --pretty
```

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  approve_commit_and_continue `
  --run-id demo-swarm-run `
  --pretty
```

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  approve_push_and_continue `
  --run-id demo-swarm-run `
  --pretty
```

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  reject_checkpoint `
  --run-id demo-swarm-run `
  --checkpoint run_checks `
  --note "Нужна доработка контекста" `
  --pretty
```

### Claim And Complete An External Role Job

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  claim_role_job `
  --run-id demo-swarm-run `
  --job-id coder `
  --claimed-by external-runtime
```

```powershell
.\venv\Scripts\python.exe -m scripts.agents.mcp `
  complete_role_job `
  --run-id demo-swarm-run `
  --job-id coder `
  --result-json "{\"summary\":\"changes applied\",\"applied_files\":[\"docs/swarm-usage.md\"]}"
```

## Approval Boundaries

Важно помнить:

- route/plan/status можно использовать как безопасные read-oriented команды
- lifecycle-этапы после planning могут менять run artifacts
- `start_swarm_run` создает `workspace.json`, `jobs/index.json` и другие orchestration artifacts в `runs/<run-id>/`
- `start_autonomous_swarm_run` делает то же самое, но сразу доводит run до первого external handoff или human boundary
- `start_supervised_swarm_run` идет дальше и может сам крутить supervisor loop до следующей human boundary
- `preview_sandbox_plan` и `show_diff_preview` дают CLI-first UX без ручного чтения JSON и patch-файлов
- `show_run_status --human`, `show_job_queue --human` и `show_diff_preview --human` пишут `run-status.md`, `job-queue.md` и `diff-preview.md` прямо в run bundle
- `run_dispatcher` помогает снять ручной шов на уровне UX, но опирается на общий executor/job contract
- `run_supervisor` закрывает следующий слой и может сам запускать built-in runtime worker для внешних AI jobs
- если verification profile требует реальный sandbox, executor по умолчанию выберет `docker`
- `local_dry_run` остается явным preview-режимом, а `github_actions` доступен как explicit remote adapter
- `commit` и `push` выполняются только по явному запросу разработчика
- реальные тесты и smoke-прогоны все еще требуют явного approval пользователя

## Recommended Daily Flow

Обычный ежедневный путь работы выглядит так:

1. Сначала спланировать задачу через `scripts.agents.mcp plan_task`.
2. Запустить orchestration через `scripts.agents.mcp start_supervised_swarm_run` или `start_autonomous_swarm_run`, а `start_swarm_run` оставить как более низкоуровневый controlled entrypoint.
3. Проверять progress через `show_run_status`, очередь ролей через `show_job_queue`, а изменения через `show_diff_preview`.
4. Для sandbox intent использовать `preview_sandbox_plan`.
5. После approval или других ручных шагов возобновлять orchestration через `scripts.agents.mcp continue_swarm_run`.
6. Для внешних AI-ролей использовать `run_supervisor` с built-in runtime worker, `run_dispatcher` как UX helper или низкоуровневые `claim_role_job` / `complete_role_job` / `fail_role_job`.
7. Для approval checkpoints использовать wrappers `approve_run_checks`, `approve_run_checks_and_continue`, `approve_commit`, `approve_commit_and_continue`, `approve_push_and_continue`, `reject_checkpoint` или request-команды, когда нужен полный approval packet.

## Related Docs

- `scripts/AGENTS.md`
- `docs/agent-context-map.md`
- `docs/testing-policy.md`
- `docs/commit-policy.md`
- `docs/sandbox-execution.md`
- `docs/swarm-runtime.md`
- `docs/verification-profiles.json`
