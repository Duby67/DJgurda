# Reliability

## Purpose

Этот файл фиксирует ожидания по надежности runtime, posture тестирования и важные operational gaps.

## Reliability Rules

- Внешние интеграции по умолчанию считаются нестабильными.
- Stable runtime sources требуют более строгих гарантий, чем experimental ones.
- Runtime temp storage должен создаваться и очищаться кодом, а не неявными предположениями.
- Error handling должен проявлять деградацию явно, а не скрывать ее за defaults.
- Multi-link orchestration должен вести себя детерминированно.
- Ошибки БД должны быть наблюдаемыми и не должны молча менять бизнес-поведение.

## Runtime Reality

- Stable sources:
  - TikTok
  - YouTube
  - Instagram
  - COUB
  - Yandex Music
- Experimental source:
  - VK
- `VK` должен оставаться отдельным R&D-треком, а не восприниматься как стабильный runtime-контракт.

## Handler Smoke Tests

- Один source должен соответствовать одной папке в `test/handlers/<Source>/`.
- Локальный smoke-скрипт должен называться `test_<source>_handlers_local.py`.
- Ссылки и ожидаемые content types должны храниться рядом с тестом в `<Source>_urls.py`.
- Базовый smoke-flow:
  1. `resolve_url`
  2. `ServiceManager.get_handler`
  3. `handler.process(...)`
  4. проверка `MediaResult.content_type`
  5. cleanup через `result.iter_cleanup_paths()` в `finally`
- Smoke-тесты нужно запускать с `--timeout 180`, где параметр поддерживается.

## Testing Posture

- Предпочитать целевые проверки только для затронутой подсистемы.
- Handler smoke-тесты полезны, но не должны переопределять архитектурный policy.
- Environment-sensitive проверки должны идти в изолированной среде или только после явного approval.
- Любой запуск тестов требует явного подтверждения пользователя.
- Локальные Python-проверки должны использовать проектный `venv`.

## Known Gaps

- webhook mode не реализован;
- политика доступа к командам может требовать ужесточения;
- внешнее anti-bot поведение остается постоянным источником регрессий;
- local и deploy environments различаются по ОС и набору инструментов.
