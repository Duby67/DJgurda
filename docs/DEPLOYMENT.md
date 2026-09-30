# Deployment

## Budget

Target VM: 1 vCPU, ~2 GiB RAM, no swap, 30 GiB disk.

| Environment | CPU | Memory | Restart |
| --- | --- | --- | --- |
| production | 0.85 | 1280 MiB | unless-stopped |
| development | 0.10 | 256 MiB | no |

About 430 MiB stays for the OS and Docker. CPU shares favor production. Build images off the
server, run one bot per environment, and stop development when unused. Downloads run one at a
time, capped at 50 MB; a short YouTube video peaked at ~75 MiB under both budgets. Measure before
changing budgets.

## Image and Compose

`deploy/Dockerfile` builds a multi-stage image from `uv.lock`, running as UID/GID 10001. It adds
static ffmpeg (stream merging) and deno (yt-dlp's YouTube JavaScript runtime); ~590 MB.

Compose always takes `deploy/compose.yaml` plus one override: `compose.production.yaml` or
`compose.development.yaml`. The override sets limits, `APP_ENV` and the project name.
`compose.local.yaml` builds locally, runs as the host user and keeps the database in the
git-ignored `.data/`; `scripts/local.sh` applies it (`up --build` / `down`). Not for the server.

Runtime properties:

- No published ports; outbound long polling only.
- Read-only root filesystem; `/tmp` is a 16 MiB tmpfs counted against memory.
- Logs rotate at 5 MiB, two files.
- SQLite at `/data/djgurda.sqlite3` and downloads in `/data/work` on the named volume `data`,
  one per Compose project; leftover downloads are removed on startup.
  Deployments keep it; `down -v` deletes it.
- Healthcheck confirms completed initialization (Telegram lookup and admin notifications), not
  ongoing connectivity.

## GitHub Actions

| Event | Checks | Deployment |
| --- | --- | --- |
| PR to `development` | `branch-policy`, `version-check`, `tests`, `lint` | — |
| PR to `main` | `branch-policy` | — |
| Merge to `development` | Build image | development |
| Merge to `main` | Build image | production |

- `branch-policy`: PRs into `main` only from `development`; no PRs from `main` into `development`.
- `version-check`: `pyproject.toml` version must exceed the base and match `uv.lock`.
- `lint`: `ruff check`, `ruff format --check`, `mypy` (strict); settings in `pyproject.toml`.
- Rulesets on both branches: require PR and the checks above, block force pushes and deletions,
  empty bypass list; `development` requires up-to-date branches. Push workflows rely on them.
- Promote `development` to `main` with merge commits.

### Settings

GitHub Environments `development` and `production`, limited to their branches.

| Name | Kind | Meaning |
| --- | --- | --- |
| `BOT_TOKEN` | Environment secret | `<id>:<secret>` from @BotFather; a different bot per environment |
| `ADMIN_IDS` | Secret | Nonempty JSON array of positive integers, e.g. `[123456789]` |
| `DEPLOY_SSH_PRIVATE_KEY` | Secret | SSH key for `DEPLOY_USER` |
| `DEPLOY_HOST` | Variable | Hostname or IPv4 |
| `DEPLOY_PORT` | Variable | SSH port, even if 22 |
| `DEPLOY_USER` | Variable | SSH user with Docker access |
| `DEPLOY_KNOWN_HOSTS` | Variable | known_hosts entries; `[host]:port` for nonstandard ports |
| `DEPLOY_APP_DIR` | Variable | Absolute root without spaces; the environment name is appended |

All are required. GHCR uses `GITHUB_TOKEN`; an existing package must grant this repository
Actions access.

### Server

Linux amd64 with Docker Engine, Compose v2 (`up --wait`), Bash, tar and flock. The SSH user runs
Docker without sudo and can write `DEPLOY_APP_DIR`.

Rollout, serialized by a server lock:

1. Pull the image by digest into a candidate under `<env>/releases`.
2. Wait up to 180 s for health, then watch health, restarts, OOM and digest for 30 s.
3. On success, switch `current` to the candidate and keep the prior one as `previous`.
4. On failure, restart `current` and fail the job; with no `current`, stop the candidate.

Old images are not pruned automatically.

Manual commands, from `DEPLOY_APP_DIR/<env>`:

```bash
docker compose --env-file current/runtime.env \
  -f current/compose.yaml -f current/compose.environment.yaml down   # or: logs --tail 50 bot
```

Roll back by running the same files under `previous/` with
`up -d --no-build --pull never --wait --wait-timeout 180`.
