# Tech Debt Tracker

## Purpose

Этот файл является tracked backlog для открытого техдолга и незакрытых архитектурных рисков.

## Backlog Metadata

- Последняя ревизия backlog: 2026-03-24 | version/tag: v1.2.5_b

## High Priority

Сейчас отдельных open high-priority items в tracked backlog нет.

## Medium Priority

### 1. Chat Settings Read Amplification

- Текущий middleware flow слишком часто читает chat settings.
- Нужны bounded cache и явная стратегия invalidation.
- Active Task:
  - `docs/exec-plans/active/chat-settings-read-amplification.md`

### 2. Runtime Ownership Of Service Manager

- Убрать дублирование runtime ownership для `ServiceManager`.
- Сдвинуться к одной application-level модели владения.
- Active Task:
  - `docs/exec-plans/active/runtime-ownership-of-service-manager.md`

### 3. External Dependency Resilience

- Добавить per-source metrics, более явные ожидания по timeout/retry и explicit degrade signals.
- Держать `VK` отдельным R&D-треком, а не оформлять его как обычную stabilization-задачу.
- Active Task:
  - `docs/exec-plans/active/external-dependency-resilience.md`

### 4. CODEX And Swarm Contour Ergonomics

- Улучшить взаимодействие `CODEX` со swarm-контуром.
- Снизить число ручных швов между прямой работой агента в репозитории и repo-local swarm entrypoints.
- Active Task:
  - `docs/exec-plans/active/codex-and-swarm-contour-ergonomics.md`

### 5. Branch Promotion Reliability

- Пофиксить проблемы при повышении ветки.
- Ужесточить predictability promotion flow для merge/push и связанных approval boundary.
- Active Task:
  - `docs/exec-plans/active/branch-promotion-reliability.md`

## Low Priority

### 7. YouTube Swarm Rollout

- Продолжать обкатывать swarm-контур на `YouTube`.
- Использовать `YouTube` как практический stability-track для orchestration, verification и approval UX.

### 8. Helper Deduplication

- Выносить повторяющиеся lightweight helpers только после закрытия более важных задач по correctness и resilience.

### 9. Toggle Command Cleanup

- Сокращать повтор шаблонов toggle-flow уже после более срочных runtime-задач.

## Next Iteration Order

1. Cache для chat settings и снижение read amplification.
2. Runtime ownership cleanup для `ServiceManager`.
3. External dependency resilience и explicit operational signals.
4. Улучшение связки `CODEX` <-> swarm contour и reliability promotion flow.
5. Продолжение обкатки swarm-контура на `YouTube`.
6. Helper deduplication и toggle-flow cleanup после более срочных runtime-задач.

## Archived Source Notes

- Более глубокие исторические backlog- и migration-notes, если они сохраняются локально, должны оставаться вне tracked-слоя.
- Эти материалы являются archive input, а не основным tracked backlog.
