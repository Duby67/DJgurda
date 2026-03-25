# Deploy

`deploy/` хранит только live deploy-контур проекта.

Здесь должны лежать только файлы, которые реально участвуют в доставке бота на сервер при workflow или ручном deploy:

- production/dev Docker image для самого бота;
- server-side deploy scripts;
- cookie sync tooling и `deploy/cookies` как staging-area.

Что не должно жить в `deploy/`:

- sandbox/test Dockerfiles;
- swarm verification images;
- локальные или экспериментальные container configs, не участвующие в server deploy.

Текущий live deploy surface:

- `Dockerfile`
- `Dockerfile.dockerignore`
- `manager.sh`
- `sync_cookies.sh`
- `sync_cookies.bat`
- `sync_cookies.env.example`
- `cookies/`

Tracked docs в этой папке:

- `README.md` - human-only описание deploy-контура;
- `AGENTS.md` - policy и routing для агентов;
- в `deploy/cookies/` tracked остаются только `README.md` и `AGENTS.md`, а не реальные secrets.

Ручной cookie-sync path:

- локальный `deploy/sync_cookies.env` хранит только параметры подключения и не коммитится;
- `sync_cookies.sh` и `sync_cookies.bat` загружают только `deploy/cookies/*_cookies.txt`;
- на сервере файлы попадают в `/home/<REMOTE_USER>/bot_{dev|prod}/data/cookies`.

CI/CD deploy path:

- workflow materializes `deploy/cookies` на runner из secrets;
- затем файлы и `deploy/manager.sh` копируются во временный staging-каталог под `/tmp/djgurda-deploy-<env>-<run>`;
- после завершения deploy этот staging-каталог удаляется, поэтому постоянная папка `~/deploy` на хосте больше не нужна.

Test-only Docker images вынесены в `test/docker/`.
