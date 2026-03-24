# Agent-First Docs Migration

## Status

Завершено.

## Goal

Перенести контекст репозитория из нескольких перегруженных mixed-файлов в набор небольших и agent-friendly документов с коротким reading path.

## What Landed

- корневой reading order теперь начинается с `AGENTS.md` и `ARCHITECTURE.md`;
- application runtime-контекст разложен по `docs/PRODUCT_SENSE.md`, `docs/RELIABILITY.md`, `docs/SECURITY.md`, `docs/PLANS.md`, `docs/product-specs/` и `docs/design-docs/`;
- swarm-контекст вынесен в `scripts/AGENTS.md`, `docs/swarm-runtime.md`, `docs/swarm-usage.md` и связанные policy-docs;
- tracked mixed legacy-файлы больше не участвуют в основном reading path и не считаются source of truth.

## Migrated Sources

Следующие legacy-источники больше не являются основным tracked контекстом:

- `README.md`
- `.github/ai-context.md`
- `.github/ai-agent-technical-task.md`
- `docs/documentation-sources.md`
- `docs/repository-root-map.md`
- `docs/deploy_layout.md`
- `docs/improvements.md`

## Completion Notes

- success criteria по discoverability и reading order выполнены;
- legacy markdown больше не используется как основной источник истины для агента;
- локальные архивные материалы, если они сохраняются разработчиком, остаются вне tracked source of truth.
