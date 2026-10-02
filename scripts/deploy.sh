#!/usr/bin/env bash
# Runs on the GitHub-hosted runner. Never enable shell tracing here.
set -euo pipefail

required=(DEPLOY_ENV DEPLOY_APP_DIR DEPLOY_HOST DEPLOY_PORT DEPLOY_USER \
  DEPLOY_KNOWN_HOSTS DEPLOY_SSH_PRIVATE_KEY GHCR_USER GHCR_TOKEN)
# production-botapi deploys only the production Bot API server; the others deploy only the bot.
if [[ ${DEPLOY_ENV:-} == production-botapi ]]; then
  required+=(BOT_API_IMAGE TELEGRAM_API_ID TELEGRAM_API_HASH)
else
  required+=(DJGURDA_IMAGE BOT_TOKEN ADMIN_IDS)
fi
for name in "${required[@]}"; do
  if [[ -z ${!name:-} ]]; then
    echo "Missing required deployment setting: $name" >&2
    exit 1
  fi
done

python3 - <<'PY'
import json, os, re
from pathlib import PurePosixPath

def require(condition, message):
    if not condition:
        raise SystemExit(message)

e = os.environ
require(e['DEPLOY_ENV'] in ('development', 'production', 'production-botapi'), 'Invalid DEPLOY_ENV')
require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', e['DEPLOY_HOST']), 'DEPLOY_HOST must be a hostname or IPv4 address')
require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', e['DEPLOY_USER']), 'Invalid DEPLOY_USER')
require(e['DEPLOY_PORT'].isdigit() and 1 <= int(e['DEPLOY_PORT']) <= 65535, 'Invalid DEPLOY_PORT')
p = PurePosixPath(e['DEPLOY_APP_DIR'])
require(p.is_absolute() and len(p.parts) > 1 and '..' not in p.parts and re.fullmatch(r'/[A-Za-z0-9_./-]+', str(p)), 'DEPLOY_APP_DIR must be an absolute non-root path without spaces or ..')
if e['DEPLOY_ENV'] == 'production-botapi':
    require(re.fullmatch(r'ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}', e['BOT_API_IMAGE']), 'BOT_API_IMAGE must be a GHCR digest')
    require(re.fullmatch(r'[1-9][0-9]*', e['TELEGRAM_API_ID']), 'TELEGRAM_API_ID must be a positive integer from my.telegram.org')
    require(re.fullmatch(r'[a-f0-9]{32}', e['TELEGRAM_API_HASH']), 'TELEGRAM_API_HASH must be 32 hex characters from my.telegram.org')
    raise SystemExit(0)
require(re.fullmatch(r'ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}', e['DJGURDA_IMAGE']), 'DJGURDA_IMAGE must be a GHCR digest')
require(re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', e['BOT_TOKEN']), 'Invalid BOT_TOKEN format')
require(re.fullmatch(r'[A-Za-z0-9_.-]*', e.get('YANDEX_MUSIC_TOKEN', '')), 'Invalid YANDEX_MUSIC_TOKEN format')
try:
    admins = json.loads(e['ADMIN_IDS'])
except ValueError:
    raise SystemExit('ADMIN_IDS must be a JSON array of positive integer IDs') from None
require(isinstance(admins, list) and admins and all(type(v) is int and v > 0 for v in admins), 'ADMIN_IDS must be a nonempty JSON array of positive integer IDs')
PY

umask 077
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
printf '%s\n' "$DEPLOY_SSH_PRIVATE_KEY" > "$work/key"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$work/known_hosts"
mkdir "$work/payload"
service=bot overlay=$DEPLOY_ENV
[[ $DEPLOY_ENV == production-botapi ]] && service=bot-api overlay=production
cp "deploy/$service/compose.yaml" "$work/payload/compose.yaml"
cp "deploy/$service/compose.$overlay.yaml" "$work/payload/compose.environment.yaml"
cp scripts/deploy-remote.sh "$work/payload/deploy-remote.sh"
printf '%s' "$GHCR_TOKEN" > "$work/payload/registry-token"
printf '%s' "$GHCR_USER" > "$work/payload/registry-user"
python3 - "$work/payload/runtime.env" <<'PY'
import json, os, sys
from pathlib import Path
if os.environ['DEPLOY_ENV'] == 'production-botapi':
    values = {name: os.environ[name] for name in ('BOT_API_IMAGE', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH')}
else:
    values = {
        'DJGURDA_IMAGE': os.environ['DJGURDA_IMAGE'],
        'BOT_TOKEN': os.environ['BOT_TOKEN'],
        'ADMIN_IDS': json.dumps(json.loads(os.environ['ADMIN_IDS']), separators=(',', ':')),
        'YANDEX_MUSIC_TOKEN': os.environ.get('YANDEX_MUSIC_TOKEN', ''),  # Optional.
        'LOG_LEVEL': 'INFO',
    }
Path(sys.argv[1]).write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
PY

# Quote the remote command once; SSH concatenates its command arguments.
remote=$(python3 - <<'PY'
import os, shlex
script = '''set -euo pipefail
umask 077
mkdir -p "$1"
cd "$1"
exec 9>.deploy.lock
flock -w 600 9 || { echo "Deployment lock timed out" >&2; exit 1; }
stage=$(mktemp -d .deploy.XXXXXX)
trap 'rm -rf "$stage"' EXIT
tar -xf - -C "$stage"
bash "$stage/deploy-remote.sh" "$stage" "$2"
'''
print(shlex.join(['bash', '-c', script, 'deploy', os.environ['DEPLOY_APP_DIR'], os.environ['DEPLOY_ENV']]))
PY
)
tar -C "$work/payload" -cf - . | ssh \
  -i "$work/key" -p "$DEPLOY_PORT" \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$work/known_hosts" -o ConnectTimeout=15 \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  "$DEPLOY_USER@$DEPLOY_HOST" "$remote"
