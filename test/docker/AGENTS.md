# AGENTS

## Purpose

Этот файл описывает правила для test-only container assets в `test/docker/`.

## Scope

`test/docker/` содержит Docker artifacts, которые используются только для tests, smoke и swarm verification.

## Source Of Truth

- `README.md` в этой папке human-only.
- Для agent work source of truth находится в:
  - `test/AGENTS.md`
  - `docs/testing-policy.md`
  - `docs/sandbox-execution.md`
  - `scripts/agents/sandbox_adapters.py`

## Context Rules

- Не путать `test/docker/` с live deploy assets из `deploy/`.
- Не читать `README.md` как замену Dockerfile, test code и sandbox adapter logic.
- Если задача касается конкретного swarm test image, переходить в `test/docker/swarm-test/AGENTS.md`.
