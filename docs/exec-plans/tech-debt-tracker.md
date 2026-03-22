# Tech Debt Tracker

## Purpose

Этот файл является tracked backlog для открытого техдолга и незакрытых архитектурных рисков.

## Backlog Metadata

- Последняя ревизия backlog: 2026-03-22 | version/tag: v1.2.5_b

## High Priority

### 1. HTML-Safe Captions

- Problem:
  - сборка caption все еще может давать невалидный HTML, если обрезка попадает внутрь разметки.
- Impact:
  - Telegram send failures даже при корректном результате обработки.
- Main Area:
  - `src/utils/messages.py`

### 2. DB Degradation Visibility

- Problem:
  - ошибки чтения из БД могут схлопываться в defaults вместо явной деградации.
- Impact:
  - поведение в production меняется без понятного operational signal.
- Main Areas:
  - `src/middlewares/bot_enabled.py`
  - `src/middlewares/db/processing/bot_settings_processor.py`

### 3. Atomic Stats Updates

- Problem:
  - создание `Source` в stats flow не гарантированно атомарно при конкуренции.
- Impact:
  - возможны race conditions и потеря части статистики.
- Main Areas:
  - `src/middlewares/db/processing/stats_processor.py`
  - `src/middlewares/db/models/sources.py`

### 4. Docs Cleanup After Typed-Runtime Transition

- Problem:
  - часть репозитория все еще описывает устаревшие legacy boundaries.
- Impact:
  - будущие изменения и выбор агентного контекста становятся менее понятными.
- Main Areas:
  - tracked docs
  - отдельные code comments и docstrings

## Medium Priority

### 5. URL Extraction And Routing Robustness

- Улучшить извлечение URL, чтобы не ловить false negative из-за хвостовой пунктуации.
- Рассмотреть parallelized `resolve_url` с ограниченной конкурентностью для multi-link batches.

### 6. Chat Settings Read Amplification

- Текущий middleware flow слишком часто читает chat settings.
- Нужны bounded cache и явная стратегия invalidation.

### 7. Runtime Ownership Of Service Manager

- Убрать дублирование runtime ownership для `ServiceManager`.
- Сдвинуться к одной application-level модели владения.

### 8. External Dependency Resilience

- Добавить per-source metrics, более явные ожидания по timeout/retry и explicit degrade signals.
- Держать `VK` отдельным R&D-треком, а не оформлять его как обычную stabilization-задачу.

## Low Priority

### 9. Helper Deduplication

- Выносить повторяющиеся lightweight helpers только после закрытия более важных задач по correctness и resilience.

### 10. Toggle Command Cleanup

- Сокращать повтор шаблонов toggle-flow уже после более срочных runtime-задач.

## Next Iteration Order

1. HTML-safe captions и routing correctness.
2. DB resilience и atomic stats behavior.
3. Оставшийся docs cleanup после архитектурного перехода.
4. URL extraction, resolve performance и cache для chat settings.

## Archived Source Notes

- Более глубокие исторические backlog- и migration-notes теперь лежат в `local/legacy-docs/` и `local/REFACTORING.md`.
- Эти файлы являются archive input, а не основным tracked backlog.
