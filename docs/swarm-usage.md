# Swarm Usage

## Purpose

Этот документ кратко описывает, как запускать swarm-oriented automation в репозитории и какие команды являются основными точками входа.

## Prerequisites

Перед использованием automation-контура ожидается:

- активный проектный `venv` или явный запуск через `.\venv\Scripts\python.exe`
- установленные dev-зависимости из `requirements-dev.txt`
- работа из корня репозитория

## Main Entry Points

Основные module-path команды:

- `python -m scripts.agents.routing.route`
- `python -m scripts.agents.routing.plan`
- `python -m scripts.agents.routing.run`
- `python -m scripts.agents.lifecycle.execute`
- `python -m scripts.agents.lifecycle.status`
- `python -m scripts.release.automation.promote`
- `python -m scripts.release.automation.sync`

## Common Commands

### Classify A Task

```powershell
.\venv\Scripts\python.exe -m scripts.agents.routing.route `
  --prompt "Исправить release flow документацию" `
  --path docs/release-flow.md `
  --pretty
```

### Build A Run Bundle

```powershell
.\venv\Scripts\python.exe -m scripts.agents.routing.run `
  --prompt "Исправить удаление исходного сообщения при multi-link routing" `
  --path src/bot/processing/media_router.py `
  --pretty
```

### Load Context For An Existing Run

```powershell
.\venv\Scripts\python.exe -m scripts.agents.lifecycle.execute `
  --run-id demo-media-router `
  --pretty
```

### Check Run Status

```powershell
.\venv\Scripts\python.exe -m scripts.agents.lifecycle.status `
  --run-id demo-media-router `
  --human
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
- `commit`, `push`, merge и release promotion вверх по веткам выполняются только по явному запросу разработчика
- реальные тесты и smoke-прогоны все еще требуют явного approval пользователя

## Recommended Daily Flow

Обычный ежедневный путь работы выглядит так:

1. Сначала классифицировать задачу через `scripts.agents.routing.route`.
2. При необходимости собрать run bundle через `scripts.agents.routing.run`.
3. Проверять progress и blockers через `scripts.agents.lifecycle.status`.
4. Для продвижения preview и release использовать `scripts.release.automation.promote`.

## Related Docs

- `scripts/AGENTS.md`
- `docs/release-flow.md`
- `docs/agent-context-map.md`
