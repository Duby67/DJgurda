# Docker deployment

## Budget

The inspected VM has 1 vCPU, 1963 MiB RAM, no swap, and a 30 GiB root filesystem
with approximately 20 GiB free. Docker uses cgroup v2. These are observations,
not guaranteed free resources during operation.

| Environment | CPU ceiling | Memory ceiling | Restart policy |
| --- | --- | --- | --- |
| production | 0.85 CPU | 1280 MiB | unless-stopped |
| development | 0.10 CPU | 256 MiB | no |

The memory ceilings leave approximately 427 MiB outside the container budgets for
the OS and Docker. Limits are ceilings, not preallocated memory or exclusive CPU
reservations. CPU shares favor production under contention. Stop development when
unused. These are initial budgets for the current bot, not measured media capacity.

Build images on a workstation or CI, not on this VM. Run one bot process per
environment. When implementing media processing, bound concurrency, stream files
to disk, cap temporary disk use, clean up on failure, and measure peak usage before
changing these budgets. Avoid adding resident services without a demonstrated need.

## Image

From the repository root, build locally:

```bash
docker build -f deploy/Dockerfile -t djgurda:local .
```

The multi-stage image contains Python and runtime dependencies installed from
`uv.lock`; pytest and uv are not included in the final stage. It runs as UID/GID
10001 without root privileges. The build context excludes local secrets.

For server deployment, publish the image separately and use its immutable digest.
Image publishing and automated deployment workflows are not implemented yet.

## Configuration and start

Use the base Compose file together with exactly one environment override. The base
file is not a standalone deployment: resource limits and environment are in the overrides.

Create a private environment file outside Git for each bot, with permissions `600`:

```dotenv
DJGURDA_IMAGE=ghcr.io/OWNER/IMAGE@sha256:DIGEST
BOT_TOKEN=TOKEN_FOR_THIS_ENVIRONMENT
LOG_LEVEL=INFO
```

Replace the image placeholder with a published image; use `djgurda:local` for a local
build. Production and development require different Telegram bot tokens.
The override supplies APP_ENV and the Compose project name; do not set
COMPOSE_PROJECT_NAME or pass `-p` unless intentionally changing project identity.

Production, from the repository root:

```bash
docker compose --env-file /path/to/production.env \
  -f deploy/compose.yaml -f deploy/compose.production.yaml up -d
```

Development, only when needed:

```bash
docker compose --env-file /path/to/development.env \
  -f deploy/compose.yaml -f deploy/compose.development.yaml up -d

docker compose --env-file /path/to/development.env \
  -f deploy/compose.yaml -f deploy/compose.development.yaml down
```

Use the same file selection with `config --quiet` to validate without printing the
token, or with `logs --tail 50 bot` to inspect logs. `docker stats --no-stream`
shows actual resource usage once containers are running.

## Current boundaries

- No published ports: the bot uses outbound long polling.
- Read-only root filesystem; `/tmp` is a 16 MiB tmpfs counted against the memory limit.
  It is for small runtime files, not future downloaded media.
- Logs rotate at 5 MiB with two files per container (plus driver overhead).
- No database or media storage volumes yet: the Hello world bot does not use them.
  Add separate persistent volumes per environment when implementing storage.
- No fake healthcheck: process restart is not proof of Telegram connectivity.
- Exceeding the memory ceiling can cause an OOM termination; development stays stopped
  after failure, production follows its restart policy.
