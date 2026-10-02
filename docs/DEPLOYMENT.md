# Deployment

## Budget

The VM is dedicated exclusively to DJgurda. Production runs the bot and its local Bot API server
and takes nearly all resources; development runs only the bot, on the cloud Bot API (50 MB
uploads), for a deployment check. Target: 1 vCPU, ~2 GiB RAM, no swap, 30 GiB disk.

| Environment | Service | CPU | Memory | Restart |
| --- | --- | --- | --- | --- |
| production | bot | 0.85 | 1152 MiB | unless-stopped |
| production | bot-api | 0.50 | 256 MiB | unless-stopped |
| development (deployment check only) | bot | 0.10 | 256 MiB | no |

About 300 MiB stays for the OS and Docker during a deployment check. CPU shares favor production.
Development stops after its deployment check, on both success and failure. The Bot API limits
are preliminary: measure its peak while sending a 512 MB file before relying on them. Build
images off the server.

One short download (up to 20 minutes) and one long download (up to 60 minutes) may run at the
same time; files are capped at 512 MB (50 MB on the cloud Bot API) and need twice their size free on disk for merging. A
YouTube download peaks at ~330 MiB, of which deno (YouTube's JavaScript challenge) takes
~290 MiB, so two parallel downloads fit the production budget. Under the 256 MiB development
budget deno is OOM-killed and yt-dlp continues with fewer formats. Measure before changing
budgets.

## Image and Compose

`deploy/Dockerfile` builds a multi-stage image from `uv.lock`, running as UID/GID 10001. It adds
static ffmpeg (stream merging), deno (yt-dlp's YouTube JavaScript runtime) and curl_cffi
(browser impersonation that TikTok requires); ~645 MB.

`deploy/bot-api.Dockerfile` builds the official
[telegram-bot-api](https://github.com/tdlib/telegram-bot-api) at a pinned commit, also as
UID/GID 10001. It runs in `--local` mode: uploads up to 2000 MB, and the bot passes files as
`file://` paths from the shared `data` volume, mounted read-only into `bot-api`.

Compose always takes `deploy/compose.yaml` plus one override: `compose.production.yaml` or
`compose.development.yaml`. The override sets limits, `APP_ENV` and the project name;
the production override also defines `bot-api` and points the bot at it with `BOT_API_URL`,
which production requires. `compose.local.yaml` is for functional checks on top of the
development override, so it uses the cloud Bot API: it builds the bot image locally, runs as the
host user with 1 CPU / 1280 MiB, and keeps the database in the git-ignored `.data/` under project
`djgurda-local`. The Bot API image is built only in CI; its local build crashes WSL.
`scripts/local.sh` applies it (`up --build` / `down`). Use a separate local bot token so a server
deployment check cannot compete for its updates. Not for the server.

Runtime properties:

- No published ports; outbound long polling only. In production the bot reaches `bot-api` on
  the internal Compose network.
- Read-only root filesystem; `/tmp` is a 16 MiB tmpfs counted against memory.
- Logs rotate at 5 MiB, two files.
- SQLite at `/data/djgurda.sqlite3` and downloads in `/data/work` on the named volume `data`,
  one per Compose project; leftover downloads are removed on startup.
  Deployments keep it; `down -v` deletes it.
- Production keeps Bot API state in the named volume `bot-api` and starts the bot after
  `bot-api` is healthy (its statistics port answers). The bot healthcheck
  confirms completed initialization (Telegram lookup and admin notifications), not ongoing
  connectivity.

## GitHub Actions

| Event | Checks | Deployment |
| --- | --- | --- |
| PR to `development` | `branch-policy`, `version-check`, `tests`, `lint` | — |
| PR to `main` | `branch-policy` | — |
| Merge to `development` | Build image | temporary deployment check, then stop |
| Merge to `main` | Build bot and Bot API images | production |

- `branch-policy`: PRs into `main` only from `development`; no PRs from `main` into `development`.
- `version-check`: `pyproject.toml` version, `GENERATION.MAJOR.MINOR.PATCH` (e.g. `2.0.4.0`),
  must exceed the base and match `uv.lock`.
- `lint`: `ruff check`, `ruff format --check`, `mypy` (strict); settings in `pyproject.toml`.
- Rulesets on both branches: require PR and the checks above, block force pushes and deletions,
  empty bypass list; `development` requires up-to-date branches. Push workflows rely on them.
- Promote `development` to `main` with merge commits.

### Settings

GitHub Environments `development` and `production`, limited to their branches.

| Name | Kind | Meaning |
| --- | --- | --- |
| `BOT_TOKEN` | Environment secret | `<id>:<secret>` from @BotFather; a different bot per environment |
| `TELEGRAM_API_ID` | Production environment secret | Application ID from my.telegram.org for the local Bot API |
| `TELEGRAM_API_HASH` | Production environment secret | Application hash from my.telegram.org |
| `YANDEX_MUSIC_TOKEN` | Secret | Optional; Yandex Music account token with a subscription |
| `ADMIN_IDS` | Secret | Nonempty JSON array of positive integers, e.g. `[123456789]` |
| `DEPLOY_SSH_PRIVATE_KEY` | Secret | SSH key for `DEPLOY_USER` |
| `DEPLOY_HOST` | Variable | Hostname or IPv4 |
| `DEPLOY_PORT` | Variable | SSH port, even if 22 |
| `DEPLOY_USER` | Variable | SSH user with Docker access |
| `DEPLOY_KNOWN_HOSTS` | Variable | known_hosts entries; `[host]:port` for nonstandard ports |
| `DEPLOY_APP_DIR` | Variable | Absolute root without spaces; the environment name is appended |

All except `YANDEX_MUSIC_TOKEN` are required. GHCR uses `GITHUB_TOKEN`; an existing package must
grant this repository Actions access.

### Server

Linux amd64 with Docker Engine, Compose v2 (`up --wait`), Bash, tar and flock. The SSH user runs
Docker without sudo and can write `DEPLOY_APP_DIR`.

Rollout, serialized by a server lock:

1. Pull the image by digest into a candidate under `<env>/releases`.
2. Wait up to 180 s for health, then watch health, restarts, OOM and digest of every service
   (`bot`, and `bot-api` in production) for 30 s.
3. In development, stop the bot after the check. On success, switch `current` to the candidate
   and keep the prior one as `previous`.
4. On failure, fail the job. Production restarts `current`, or stops the candidate if no prior
   release exists. Development stops the candidate without restarting the prior release.

Old images are not pruned automatically.

Manual commands, from `DEPLOY_APP_DIR/<env>`:

```bash
docker compose --env-file current/runtime.env \
  -f current/compose.yaml -f current/compose.environment.yaml down   # or: logs --tail 50 bot
```

Roll back production by running the same files under `previous/` with
`up -d --no-build --pull never --wait --wait-timeout 180`.
