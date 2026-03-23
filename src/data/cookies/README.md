# Cookies

Эта папка хранит локальные cookie-файлы для source handlers и smoke-проверок.

Что здесь может находиться:

- cookies для YouTube, Instagram, TikTok и VK;
- локальные operational artifacts, нужные для обхода anti-bot ограничений;
- временные или вручную подготовленные cookie bundles для разработки.

Правила:

- содержимое папки не является source of truth для поведения системы;
- реальные cookie-файлы не должны коммититься в git;
- tracked в репозитории остается только этот `README.md`.
