# HTML-Safe Captions

## Status

- Completed on 2026-03-24.
- Implementation and focused verification finished.

## Goal

Убрать риск невалидного Telegram HTML в caption flow и сделать обрезку подписи безопасной относительно тегов.

## Outcome

- HTML-safe truncation внедрена в caption flow.
- Caption builder больше не режет готовую HTML-строку сырым slice по потенциально незавершенным тегам.
- User-facing риск Telegram send failures из-за сломанного caption существенно снижен.

## Evidence

- `src/utils/messages.py`
- `src/bot/processing/link_extractor.py`
- `src/bot/processing/media_processor.py`
- `src/bot/processing/senders/registry.py`
- bot default parse mode в `src/main.py`

## Main Areas

- `src/utils/messages.py`
- при необходимости `src/bot/processing/media_processor.py`
- sender-facing validation/tests в `test/`

## Landed Changes

1. В `src/utils/messages.py` caption flow перестроен вокруг безопасного сокращения structured sections.
2. Text-segments теперь сокращаются до HTML-escaping boundary, а anchor tags сохраняются валидными.
3. Добавлены focused tests на длинные caption inputs и oversized user-link anchors.

## Verification Notes

- Пройдены targeted tests для caption builder и соседнего sender-facing path.
- Verification закрыт в проектном `venv`.

## Swarm Notes

- Initial discovery orchestrated through swarm run `20260324-114634-swarm`.
- Работа завершена в рамках follow-up implementation pass и verification boundary.
