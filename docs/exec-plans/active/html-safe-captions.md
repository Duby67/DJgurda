# HTML-Safe Captions

## Status

- Active.
- Discovery completed on 2026-03-24.
- Current phase: implementation planning.

## Goal

Убрать риск невалидного Telegram HTML в caption flow и сделать обрезку подписи безопасной относительно тегов.

## Current Assessment

- Проблема подтверждена и остается актуальной.
- Текущий caption собирается как HTML-строка и затем режется сырым `[:MAX_CAPTION]`, что может оборвать `<a>` или `</a>` внутри строки.
- Риск user-facing: высокий, потому что корректный media result может не отправиться из-за невалидного HTML caption.

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

## Action Plan

1. Выделить безопасный caption-truncation helper, который режет только text-segments и не ломает HTML tags.
2. Пересобрать `build_caption()` вокруг структурированных сегментов вместо финального raw slice по готовой HTML-строке.
3. Сохранять link blocks целиком и резервировать место под ellipsis до финальной сборки.
4. Добавить targeted tests на длинные caption inputs и boundary cases возле opening/closing anchor tags.
5. При необходимости ввести fallback-политику: сначала убирать менее важные текстовые блоки, а не резать HTML внутри ссылок.

## Verification Notes

- Нужны targeted tests для caption builder и sender-facing caption path.
- Запуск тестов требует отдельного approval пользователя.

## Swarm Notes

- Initial discovery orchestrated through swarm run `20260324-114634-swarm`.
- Следующий полезный increment: локальный implementation pass по `src/utils/messages.py` с последующим review и test approval boundary.
