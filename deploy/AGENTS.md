# AGENTS

## Purpose

Этот файл описывает локальные правила для `deploy/`.

## Scope

`deploy/` содержит только live deploy assets:

- server deploy Docker image;
- deploy scripts;
- cookie sync tooling;
- `deploy/cookies/` как staging-area для deploy-side materialization.

## Source Of Truth

- `README.md` в этой папке human-only и не является источником истины для агента.
- Для deploy behavior source of truth находится в:
  - `deploy/Dockerfile`
  - `deploy/manager.sh`
  - `.github/workflows/deploy-dev.yml`
  - `.github/workflows/deploy-prod.yml`
  - `docs/design-docs/deploy-storage-layout.md`
  - `docs/SECURITY.md`

## Context Rules

- Не читать `README.md` как замену реальным deploy scripts и workflows.
- Не смешивать `deploy/` с test-only container assets из `test/docker/`.
- Если задача касается cookies materialization, читать `deploy/cookies/AGENTS.md`.
- Помнить, что `deploy/cookies/` хранит только placeholder docs в git, а не реальные secrets.
