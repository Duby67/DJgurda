# Runtime Modernization Summary

## Purpose

Этот файл хранит короткое tracked-summary по модернизации runtime, которая раньше была размазана по mixed backlog-документам.

## Completed Themes

- typed runtime boundary вокруг `MediaResult`;
- внедрение sender registry и handler registry;
- cleanup статусов источников: `YandexMusic` в stable runtime, `VK` только в development-only статусе;
- cleanup lifecycle для runtime storage и cookies;
- постепенное сокращение legacy compatibility и mixin-heavy boundaries.

## Why Keep This

Эти изменения объясняют текущую форму системы и помогают понять, почему старые legacy-описания больше не стоит считать актуальной архитектурой.
