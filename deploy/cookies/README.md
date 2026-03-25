# Deploy Cookies

Эта папка служит deploy-side staging area для cookie-файлов.

Что здесь происходит:

- GitHub Actions или ручной deploy materialize cookies в `deploy/cookies/`;
- затем `deploy/sync_cookies.sh` или `deploy/sync_cookies.bat` копируют только локально существующие `*_cookies.txt` на сервер;
- на сервере файлы синхронизируются в `/home/<REMOTE_USER>/bot_{dev|prod}/data/cookies`;
- сами секреты не должны храниться в git.

Правила:

- реальные `*_cookies.txt` не коммитятся;
- tracked в репозитории остаются только этот `README.md` и `AGENTS.md`;
- папка предназначена для deploy-потока, а не для локального source of truth приложения.
