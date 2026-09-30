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
The push workflow builds on GitHub-hosted runners, publishes to GHCR and deploys
by digest. Configure the prerequisites below before the first merge.

## Configuration and start

Use the base Compose file together with exactly one environment override. The base
file is not a standalone deployment: resource limits and environment are in the overrides.
For local WSL runs, additionally use `compose.local.yaml` to build the same runtime
image locally; see [local startup](../README.md#локальный-запуск). Do not use the
local build override on the server.

Create a private environment file outside Git for each bot, with permissions `600`:

```dotenv
DJGURDA_IMAGE=ghcr.io/OWNER/IMAGE@sha256:DIGEST
BOT_TOKEN=TOKEN_FOR_THIS_ENVIRONMENT
ADMIN_IDS=[123456789]
LOG_LEVEL=INFO
```

Replace the image placeholder with a published image; use `djgurda:local` for a local
build. Production and development require different Telegram bot tokens.
Set ADMIN_IDS to the administrator IDs as a nonempty JSON array. A GitHub secret
is passed explicitly by the deployment workflow; manual launches need it in the
environment file.
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
- No database or media storage volumes yet: the startup notification bot does not use them.
  Add separate persistent volumes per environment when implementing storage.
- Healthcheck checks an initialization marker written after Telegram identity lookup and
  all administrator notifications succeed. It is cleared on startup and shutdown.
  It confirms completed initialization, not ongoing Telegram connectivity.
- Exceeding the memory ceiling can cause an OOM termination; development stays stopped
  after failure, production follows its restart policy.


## GitHub Actions

| Event | Checks | Deployment |
| --- | --- | --- |
| PR to `development` | `branch-policy`, `version-check`, `tests` | None |
| PR to `main` | `branch-policy` only | None |
| Push after merge to `development` | Build image | development |
| Push after merge to `main` | Build image | production |

`branch-policy` rejects PRs from `main` or `production` into `development` and
accepts PRs into `main` only from `development` in this repository. PR jobs have
read-only repository access and no deployment secrets. The version gate requires
`MAJOR.MINOR.PATCH` to increase above the PR base version and match `uv.lock`.
Update `pyproject.toml` and run `uv lock` before opening each development PR.
Tests run with `uv sync --locked` and `uv run --locked pytest -q`.

Configure active GitHub branch rulesets for both branches: require a PR, block
force pushes and deletions, and leave the bypass list empty. After the first CI
run, require the exact checks in the table above. For `development`, enable
**Require branches to be up to date before merging** so the version comparison
and tests include the latest target changes. Use merge commits when promoting
`development` to `main` to preserve their shared history. Push workflows rely on
these rulesets: they do not rerun PR tests or enforce PR origin themselves.

### GitHub settings and secrets

Create GitHub Environments named `development` and `production`. Restrict their
allowed deployment branches to `development` and `main`, respectively.
Set `BOT_TOKEN` separately in each environment, using different bots.
The repository secret `ADMIN_IDS` must contain a nonempty JSON array of positive
integer IDs. Administrators must have started a chat with each bot.

Supply these repository **Variables** (environment overrides can point to another server):

| Variable | Meaning |
| --- | --- |
| `DEPLOY_HOST` | SSH hostname or IPv4 address |
| `DEPLOY_PORT` | SSH port, explicitly set even when it is 22 |
| `DEPLOY_USER` | SSH user with Docker access |
| `DEPLOY_KNOWN_HOSTS` | Verified OpenSSH known_hosts entries; nonstandard ports use `[host]:port` |
| `DEPLOY_APP_DIR` | Shared application root without spaces: `/home/DJgurda/apps`; the script appends the environment |

Keep `DEPLOY_SSH_PRIVATE_KEY`, `ADMIN_IDS` and each environment's `BOT_TOKEN` in
**Secrets**. The workflow reads the five connection settings above from `vars`,
not `secrets`. All settings are required; missing settings fail the deployment. Key verification
uses `DEPLOY_KNOWN_HOSTS` with strict checking, without dynamically trusting keys
from the deployment connection. The pipeline uses the automatic `GITHUB_TOKEN`
for GHCR publishing and pulling; a personal registry token is not needed. If a
GHCR package already exists, grant this repository Actions access to that package.

### Server prerequisites and rollout

The server must be Linux amd64 with Docker Engine, Compose v2 supporting `up --wait`,
Bash, tar and flock. The SSH user must be able to run Docker without interactive
sudo and create/write `DEPLOY_APP_DIR`. No Python, uv, source checkout or image
build is required on the server. Stop the legacy bot before the first deployment
if it uses either new environment's token.

Both environments can share one server and the same `DEPLOY_APP_DIR`. They use
separate subdirectories and Compose projects. A shared server lock serializes
rollouts; GitHub also serializes runs per branch without interrupting an active
deployment. Each run checks that its commit is still the branch tip before build
and again before SSH, so rerunning an outdated commit fails explicitly.

The server pulls the image and creates a private candidate directory under
`DEPLOY_APP_DIR/<environment>/releases`. Compose waits up to 180 seconds for the
initialization healthcheck, then observes health, restart count, OOM state and
image digest for 30 seconds. Telegram identity lookup and administrator
notifications have a shared 60-second initialization timeout. Application logs
stay on the server and are not copied to Actions logs automatically.

Only after these checks pass does the script atomically switch `current` to the
candidate and retain the last successful release as `previous`. Failed attempts
and retries do not replace the saved successful configuration. On a startup
failure, the script attempts to restart `current` with its saved image and
configuration and waits for readiness; the deployment job still fails. If there
is no successful release, it stops the candidate. A recovery failure is reported
explicitly and needs operator intervention. Recovery restarts send the normal
startup notification again.

Runtime env files have mode `600`, release directories `700`. Registry credentials
and transfer staging are temporary. At most two successful configuration releases
are retained; old application images still need disk maintenance. This is not a
database rollback mechanism. Development remains running until manually stopped.
Registry credentials expire with the workflow,
so a later manual pull of a private image requires registry authentication.

To stop development when unused, run from `DEPLOY_APP_DIR/development`:

```bash
docker compose --env-file current/runtime.env \
  -f current/compose.yaml -f current/compose.environment.yaml down
```

Use the same file arguments with `logs --tail 50 bot` for local diagnostics.
For manual recovery, use the three files under `previous/` with
`up -d --no-build --pull never --wait --wait-timeout 180`. This starts the saved
release without changing the release pointers. Keep disk usage under observation
and remove obsolete application images that are no longer needed for rollback.
