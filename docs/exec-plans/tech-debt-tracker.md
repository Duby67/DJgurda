# Tech Debt Tracker

## Purpose

Этот файл является tracked backlog для открытого техдолга и незакрытых архитектурных рисков.

## Backlog Metadata

- Последняя ревизия backlog: 2026-03-24 | version/tag: v1.2.5_b

## High Priority

Сейчас отдельных open high-priority items в tracked backlog нет.

## Recently Completed

- `HTML-Safe Captions`
  - закрыто 2026-03-24; summary: `docs/exec-plans/completed/html-safe-captions.md`
- `DB Degradation Visibility`
  - закрыто 2026-03-24; summary: `docs/exec-plans/completed/db-degradation-visibility.md`
- `Atomic Stats Updates`
  - закрыто 2026-03-24; summary: `docs/exec-plans/completed/atomic-stats-updates.md`
- `Docs Cleanup After Typed-Runtime Transition`
  - закрыто 2026-03-24; summary: `docs/exec-plans/completed/docs-cleanup-after-typed-runtime-transition.md`

## Medium Priority

### 1. URL Extraction And Routing Robustness

- Улучшить извлечение URL, чтобы не ловить false negative из-за хвостовой пунктуации.
- Рассмотреть parallelized `resolve_url` с ограниченной конкурентностью для multi-link batches.

### 2. Chat Settings Read Amplification

- Текущий middleware flow слишком часто читает chat settings.
- Нужны bounded cache и явная стратегия invalidation.

### 3. Runtime Ownership Of Service Manager

- Убрать дублирование runtime ownership для `ServiceManager`.
- Сдвинуться к одной application-level модели владения.

### 4. External Dependency Resilience

- Добавить per-source metrics, более явные ожидания по timeout/retry и explicit degrade signals.
- Держать `VK` отдельным R&D-треком, а не оформлять его как обычную stabilization-задачу.

### 5. CODEX And Swarm Contour Ergonomics

- Улучшить взаимодействие `CODEX` со swarm-контуром.
- Снизить число ручных швов между прямой работой агента в репозитории и repo-local swarm entrypoints.

### 6. Branch Promotion Reliability

- Пофиксить проблемы при повышении ветки.
- Ужесточить predictability promotion flow для merge/push и связанных approval boundary.

## Low Priority

### 7. YouTube Swarm Rollout

- Продолжать обкатывать swarm-контур на `YouTube`.
- Использовать `YouTube` как практический stability-track для orchestration, verification и approval UX.

### 8. Helper Deduplication

- Выносить повторяющиеся lightweight helpers только после закрытия более важных задач по correctness и resilience.

### 9. Toggle Command Cleanup

- Сокращать повтор шаблонов toggle-flow уже после более срочных runtime-задач.

## Next Iteration Order

1. URL extraction, resolve performance и cache для chat settings.
2. Runtime ownership cleanup для `ServiceManager`.
3. External dependency resilience и explicit operational signals.
4. Улучшение связки `CODEX` <-> swarm contour и reliability promotion flow.
5. Продолжение обкатки swarm-контура на `YouTube`.
6. Helper deduplication и toggle-flow cleanup после более срочных runtime-задач.

## Archived Source Notes

- Более глубокие исторические backlog- и migration-notes, если они сохраняются локально, должны оставаться вне tracked-слоя.
- Эти материалы являются archive input, а не основным tracked backlog.
