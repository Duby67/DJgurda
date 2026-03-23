# AGENTS

## Purpose

Этот файл задает правила для artifact-слоя `runs/`.

## Scope

`runs/` хранит только локальные swarm run artifacts и временные orchestration bundles.

## Source Of Truth

- `runs/` не является source of truth для product behavior или policy.
- `README.md` human-only.
- Для агента source of truth по swarm runtime находится в:
  - корневом `AGENTS.md`
  - `scripts/AGENTS.md`
  - `docs/swarm-runtime.md`
  - `docs/swarm-usage.md`

## Context Rules

- Не читать `runs/` по умолчанию.
- Не использовать старые run artifacts как замену чтению кода или tracked docs.
- Читать конкретный `runs/<run-id>/` только если:
  - пользователь явно сослался на этот run;
  - задача касается debugging конкретного orchestration запуска;
  - tracked docs прямо требуют сверить реальный artifact.

## Change Rules

- Не создавать tracked файлов в подпапках run artifacts.
- Не опираться на содержимое `runs/` как на долговременный контракт.
