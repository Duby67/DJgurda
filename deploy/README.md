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
- `cookies/`

Tracked docs в этой папке:

- `README.md` - human-only описание deploy-контура;
- `AGENTS.md` - policy и routing для агентов;
- в `deploy/cookies/` tracked остаются только `README.md` и `AGENTS.md`, а не реальные secrets.

Test-only Docker images вынесены в `test/docker/`.
