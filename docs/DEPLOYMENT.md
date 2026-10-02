# Deployment

## Budget

The VM is dedicated exclusively to DJgurda. Production runs the bot (project
`djgurda-production`) and its local Bot API server (project `djgurda-bot-api`), deployed
separately, and takes nearly all resources; development runs only the bot, on the cloud Bot API (50 MB
uploads), for a deployment check. Target: 1 vCPU, ~2 GiB RAM, no swap, 30 GiB disk.

| Environment | Service | CPU | Memory | Restart |
| --- | --- | --- | --- | --- |
| production | bot | 0.85 | 1152 MiB | unless-stopped |
| production | bot-api | 0.50 | 256 MiB | unless-stopped |
| development (deployment check only) | bot | 0.10 | 256 MiB | no |

About 300 MiB stays for the OS and Docker during a deployment check. CPU shares favor production.
Development stops after its deployment check, on both success and failure. The Bot API limits
are preliminary: measure its peak while sending a 2000 MB file before relying on them. Build
images off the server.

One short download (up to 20 minutes) and one long download (up to 2 hours) may run at the
same time; files are capped at 2000 MB (50 MB on the cloud Bot API) and need twice their size free on disk for merging. A
YouTube download peaks at ~330 MiB, of which deno (YouTube's JavaScript challenge) takes
~290 MiB, so two parallel downloads fit the production budget. Under the 256 MiB development
budget deno is OOM-killed and yt-dlp continues with fewer formats. Measure before changing
budgets.

## Image and Compose

Each service has its own directory: `deploy/bot/` and `deploy/bot-api/`.

`deploy/bot/Dockerfile` builds a multi-stage image from `uv.lock`, running as UID/GID 10001. It adds
static ffmpeg (stream merging), deno (yt-dlp's YouTube JavaScript runtime) and curl_cffi
(browser impersonation that TikTok requires); ~645 MB.

`deploy/bot-api/Dockerfile` builds the official
[telegram-bot-api](https://github.com/tdlib/telegram-bot-api) at a pinned commit, also as
UID/GID 10001. It runs in `--local` mode: uploads up to 2000 MB, and the bot passes files as
`file://` paths from the production bot's `data` volume, mounted read-only into `bot-api`.

A bot deployment takes `deploy/bot/compose.yaml` plus one override: `compose.production.yaml` or
`compose.development.yaml`. The override sets limits, `APP_ENV` and the project name; the
production override points the bot at `bot-api` with `BOT_API_URL`, which production requires,
over the external network `djgurda-bot-api`. A Bot API deployment (environment
`production-botapi`) takes `deploy/bot-api/compose.yaml` plus `compose.production.yaml`; it owns that network and
needs the production volume `djgurda-production_data`, so production must exist first, and the
bot needs the network, so the Bot API must be deployed before a production bot that uses it. `compose.local.yaml` is for functional checks on top of the
development override, so it uses the cloud Bot API: it builds the bot image locally, runs as the
host user with 1 CPU / 1280 MiB, and keeps the database in the git-ignored `.data/` under project
`djgurda-local`. The Bot API image is built only in CI; its local build crashes WSL.
`scripts/local.sh` applies it (`up --build` / `down`). Use a separate local bot token so a server
deployment check cannot compete for its updates. Not for the server.

Runtime properties:

- No published ports; outbound long polling only. In production the bot reaches `bot-api` on
  the internal network `djgurda-bot-api`.
- Read-only root filesystem; `/tmp` is a 16 MiB tmpfs counted against memory.
- Logs rotate at 5 MiB, two files.
- SQLite at `/data/djgurda.sqlite3` and downloads in `/data/work` on the named volume `data`,
  one per Compose project; leftover downloads are removed on startup.
  Deployments keep it; `down -v` deletes it.
- The Bot API keeps its state in the named volume `djgurda-bot-api_state`; its healthcheck
  is the statistics port. The bot healthcheck confirms completed initialization (Telegram lookup and admin notifications), not ongoing
  connectivity.

## GitHub Actions

| Event | Checks | Deployment |
| --- | --- | --- |
| PR to `development` | `branch-policy`, `version-check`, `tests`, `lint` | — |
| PR to `main` or `production-botapi` | `branch-policy` | — |
| Merge to `development` | Build bot image | temporary deployment check, then stop |
| Merge to `main` | Build bot image | production bot only |
| Merge to `production-botapi` | Build Bot API image | production Bot API only |

- `branch-policy`: PRs into `main` and `production-botapi` only from `development`; no PRs from
  them into `development`.
- `version-check`: `pyproject.toml` version, `GENERATION.MAJOR.MINOR.PATCH` (e.g. `2.0.4.0`),
  must exceed the base and match `uv.lock`.
- `lint`: `ruff check`, `ruff format --check`, `mypy` (strict); settings in `pyproject.toml`.
- Rulesets on `development`, `main` and `production-botapi`: require PR and the checks above, block force pushes and deletions,
  empty bypass list; `development` requires up-to-date branches. Push workflows rely on them.
- Promote `development` to `main` and `production-botapi` with merge commits.

### Settings

GitHub Environments `development` (branch `development`) and `production` (branches `main` and
`production-botapi`).

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
2. Start the project and remove services it no longer defines. Wait up to 180 s for health,
   then watch health, restarts, OOM and digest of its service for 30 s.
3. In development, stop the bot after the check. On success, switch `current` to the candidate
   and keep the prior one as `previous`.
4. On failure, fail the job. Production and production-botapi restart `current`, or stops the candidate if no prior
   release exists. Development stops the candidate without restarting the prior release.

Old images are not pruned automatically.

Manual commands, from `DEPLOY_APP_DIR/<env>` (`<env>` is `development`, `production` or
`production-botapi`):

```bash
docker compose --env-file current/runtime.env \
  -f current/compose.yaml -f current/compose.environment.yaml down   # or: logs --tail 50 bot
```

Roll back production by running the same files under `previous/` with
`up -d --no-build --pull never --wait --wait-timeout 180`.
