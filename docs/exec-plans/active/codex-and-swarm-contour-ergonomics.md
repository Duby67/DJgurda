# CODEX And Swarm Contour Ergonomics

## Status

- Active.
- Initial planning started on 2026-03-24.
- Current phase: first implementation slice in progress.

## Goal

Снизить число ручных швов между прямой работой агента в репозитории и repo-local swarm entrypoints.

## Problem Statement

- Между прямым agent-driven flow и repo-local swarm runtime все еще есть заметные UX/manual seams.
- Это мешает использовать swarm contour как более естественный daily workflow.
- Повторяется `instruction_conflict`, когда входной path указывает только на planning/doc файл вроде `docs/exec-plans/tech-debt-tracker.md`, а фактическая работа быстро разворачивается в planning-layer, code assessment и multi-file orchestration.
- Текущий выбор agent-моделей и ролей недостаточно гибко подстраивается под тип задачи, особенно для coding-heavy workstreams.

## Main Areas

- `scripts/agents/mcp/`
- `scripts/agents/routing/`
- `docs/swarm-runtime.md`
- `docs/swarm-usage.md`
- related planning/routing tests in `test/scripts/`

## Planned Work

1. Зафиксировать текущие ручные швы между direct Codex flow и swarm entrypoints.
2. Определить, какие seams снимаются docs/UX, а какие требуют runtime changes.
3. Разобрать recurring `instruction_conflict` path:
   - когда docs/planning entrypoint автоматически маршрутизуется слишком узко;
   - когда реальный task scope быстро выходит в code analysis, active task materialization и multi-file orchestration;
   - когда orchestrator вынужден вручную продолжать run поверх already-created swarm artifacts.
4. Сформировать более гибкую policy для выбора agent-моделей и ролей по task type.
   - В частности, оценить default/use-preference для `gpt-5.3-codex` во всех code-oriented workstreams, где основной результат - код, тесты и refactor implementation.
   - Отдельно описать, где frontier general-purpose model полезнее оставить для planning/review/docs-heavy phases.
5. Сформировать bounded ergonomics roadmap без расползания в unrelated swarm refactors.
6. Подготовить implementation plan и targeted verification set.

## Progress Snapshot

- Первый bounded slice взят в route-stage.
- Для planning/doc entrypoint в `docs/exec-plans/*` начат переход от false-positive `instruction_conflict` к context expansion в swarm runtime orchestration context.
- В первую очередь расширяется кодовый и test context для `swarm_runtime_orchestration_change`, чтобы direct Codex flow не требовал ручного шва сразу после planning anchor.
