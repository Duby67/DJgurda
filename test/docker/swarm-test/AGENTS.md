# AGENTS

## Purpose

Этот файл задает локальные правила для `test/docker/swarm-test/`.

## Scope

Папка содержит test harness image для:

- Docker-based swarm verification;
- sandbox adapter checks;
- Docker smoke scenarios.

## Source Of Truth

- `README.md` в этой папке human-only.
- Основные источники истины для агента:
  - `test/docker/swarm-test/Dockerfile`
  - `test/docker/swarm-test/Dockerfile.dockerignore`
  - `scripts/agents/sandbox_adapters.py`
  - `test/scripts/test_swarm_sandbox_adapters.py`
  - `docs/testing-policy.md`

## Context Rules

- Не трактовать этот image как deploy image.
- Для container-based tests считать Docker обязательной предпосылкой на хосте.
- Если Docker недоступен, ожидать blocked или skip-path, а не silent fallback к real execution.
