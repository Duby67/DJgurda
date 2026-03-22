# AGENTS

## Purpose

Этот файл описывает локальные правила для зоны `src/handlers/resources/VK/`.

## Scope

Зона `VK/` является отдельным R&D-направлением внутри handlers/resources.

## Read First

Перед изменениями в этой зоне сначала читать:

1. `src/handlers/resources/AGENTS.md`
2. `docs/RELIABILITY.md`
3. `docs/exec-plans/tech-debt-tracker.md`
4. файлы внутри `src/handlers/resources/VK/`, связанные с задачей

## Local Invariants

- `VK` не является частью stable runtime.
- Наличие кода и локальных smoke checks не означает production readiness.
- `yt-dlp` не должен считаться надежной базовой технологией для `VK`.
- Любое текущее решение здесь нужно рассматривать как исследовательское и легко деградирующее.

## Change Rules

- Не продвигать `VK` в stable runtime через локальные точечные правки.
- Не оформлять изменения в `VK` как обычную stabilization-задачу без отдельного архитектурного решения.
- При правках extraction logic отдельно фиксировать, что именно стало лучше:
  - классификация URL;
  - cookies usage;
  - playlist/audio extraction;
  - fallback behavior.
- Не переносить VK-specific hacks в общий infrastructure-слой без очень сильного обоснования.

## Test Guidance

- Основные проверки находятся в `test/handlers/VK/`.
- Результаты smoke checks здесь не должны трактоваться как достаточное доказательство stable readiness.
- Любой запуск тестов требует явного подтверждения пользователя.

## Escalate When

- нужно менять source-status policy;
- хочется включить `VK` в registry stable runtime;
- изменение затрагивает общий handler contract или shared infra ради поддержки `VK`.
