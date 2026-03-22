# Deploy Cookies

Эта папка служит deploy-side staging area для cookie-файлов.

Что здесь происходит:

- GitHub Actions или ручной deploy materialize cookies в `deploy/cookies/`;
- затем файлы копируются на сервер и синхронизируются в runtime cookies directory;
- сами секреты не должны храниться в git.

Правила:

- реальные `*_cookies.txt` не коммитятся;
- tracked в репозитории остаются только этот `README.md` и `AGENTS.md`;
- папка предназначена для deploy-потока, а не для локального source of truth приложения.
