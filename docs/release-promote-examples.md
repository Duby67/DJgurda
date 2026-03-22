# Release Promote Examples

## Purpose

Этот документ показывает типовые команды для использования `scripts.release.automation.promote` в двух основных сценариях:

- `swarm-dev -> dev`
- `dev -> main`

## Preview Promotion Example

Сценарий:

- исходная ветка: `swarm-dev`
- целевая ветка: `dev`
- цель: выпустить preview-версию для dev-бота

### Dry Run

Сначала всегда стоит построить план без реального merge и push:

```powershell
.\venv\Scripts\python.exe -m scripts.release.automation.promote `
  --source-branch swarm-dev `
  --target-branch dev `
  --target-kind preview `
  --human
```

Что делает dry-run:

- проверяет состояние `main`, `dev` и `swarm-dev`
- рассчитывает следующий preview tag, например `v1.2.5_a` или `v1.2.5_b`
- показывает план merge, version bump, tag и push

### Execute And Push

Если dry-run корректен, можно выполнить реальный promotion:

```powershell
.\venv\Scripts\python.exe -m scripts.release.automation.promote `
  --source-branch swarm-dev `
  --target-branch dev `
  --target-kind preview `
  --execute `
  --push `
  --human
```

Что произойдет:

- `swarm-dev` будет влит в `dev`
- `src/__init__.py` получит preview-версию
- будет создан preview tag
- `dev` и tag будут отправлены в `origin`

## Stable Promotion Example

Сценарий:

- исходная ветка: `dev`
- целевая ветка: `main`
- цель: выпустить стабильную версию после проверки на dev-боте

### Dry Run

```powershell
.\venv\Scripts\python.exe -m scripts.release.automation.promote `
  --source-branch dev `
  --target-branch main `
  --target-kind stable `
  --human
```

Что делает dry-run:

- читает текущую stable baseline из `main`
- проверяет состояние preview-версии в `dev`
- рассчитывает итоговый stable tag без preview suffix

Например:

- если `dev` находится на `v1.2.5_c`, promotion подготовит `v1.2.5`

### Execute And Push

```powershell
.\venv\Scripts\python.exe -m scripts.release.automation.promote `
  --source-branch dev `
  --target-branch main `
  --target-kind stable `
  --execute `
  --push `
  --human
```

Что произойдет:

- `dev` будет влит в `main`
- preview suffix будет снят
- `src/__init__.py` получит stable-версию
- будет создан stable release tag
- `main` и tag будут отправлены в `origin`

## Notes

- `--execute` без `--push` позволяет выполнить merge/tag локально без отправки в `origin`
- `--push` допустим только вместе с `--execute`
- прямой promotion `swarm-dev -> main` возможен, но считается исключением
- перед каждым реальным promotion рекомендуется запускать dry-run
