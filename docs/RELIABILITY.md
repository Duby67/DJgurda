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

- Active runtime sources:
  - TikTok
  - YouTube
  - Instagram
  - COUB
  - Yandex Music
  - VK
- `VK` включен в active runtime, но остается самым хрупким cookie-sensitive source и требует более осторожной проверки, чем core sources.

## Active Source Resilience Posture

- `TikTok`
  - Основные зависимости: `yt-dlp`, `TikWM API`, profile fetch path.
  - Явные ожидания: `TikWM` bounded to `20s`, profile fetch bounded to `15s`, shared thumbnail/audio downloads stay on the `10s` posture.
  - Допустимый degrade path: один bounded fallback `TikWM -> yt-dlp`, затем явный `failed` outcome без бесконечных повторов.
- `YouTube`
  - Основные зависимости: `yt-dlp`, cookies, shared thumbnail/audio downloads.
  - Явные ожидания: extraction latency доминируется `yt-dlp`, а direct HTTP media helpers остаются на shared `10s` posture.
  - Допустимый degrade path: один format fallback до `best`, дальше cookie/anti-bot failures не маскируются повторными retry loops.
- `Instagram`
  - Основные зависимости: `yt-dlp`, `web_profile_info` fallback, cookie-sensitive web requests.
  - Явные ожидания: `web_profile_info` bounded to `12s`, shared thumbnail/audio downloads stay on the `10s` posture.
  - Допустимый degrade path: profile metadata может один раз перейти на web fallback, затем ошибка должна оставаться наблюдаемой.
- `COUB`
  - Основные зависимости: COUB JSON APIs, direct media downloads, `ffmpeg`, ytdlp-style fallback.
  - Явные ожидания: metadata API bounded to `15s`, direct media downloads bounded to `90s`.
  - Допустимый degrade path: bounded source switching across segments/share/ytdlp, но без бесконечных mux attempts и без молчаливого partial output.
- `Yandex.Music`
  - Основные зависимости: Yandex Music API client, direct track links, shared HTTP audio/cover downloads.
  - Явные ожидания: shared HTTP downloads stay on the `10s` posture, auth/metadata gaps должны завершаться быстро и явно.
  - Допустимый degrade path: один fallback при извлечении `track_id` из `resolved_url`; отсутствие token/direct link не должно превращаться в blind retry.
- `VK`
  - Основные зависимости: cookie-sensitive HTML/JSON extraction, embedded payload parsing для `post/profile`, `al_audio` web endpoints, direct/HLS downloads и bounded `yt-dlp` fallback для части путей.
  - Явные ожидания: VK smoke остается network-sensitive, cookies должны быть актуальными, а bounded fallbacks не должны превращаться в скрытые retry loops.
  - Текущий runtime scope: `audio`, `playlist`, `clip`, `post`, `profile/community`; smoke-покрытие в `test/handlers/VK/` должно оставаться синхронизированным с этим scope и не требовать optional payload-поля как будто они обязательны всегда.
  - Допустимый degrade path: один ограниченный fallback внутри VK-модуля, затем явный fail-closed outcome без маскировки interstitial/cookie проблем.

## Observability Signals

- Active runtime должен держать per-source resilience posture в tracked contract, а не в неявном tribal knowledge.
- Для каждого active source нужно сохранять именованные degrade signals, которые совпадают с documented fallback path и могут использоваться в логах, review и future metrics.
- Registry metadata является главным tracked слоем для этого posture; markdown-документы должны лишь объяснять его human-readable версию.

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
