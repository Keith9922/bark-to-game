#!/usr/bin/env bash
# Deploy the douyin-bundle static site to the demo host.
#
# Reads SSH credentials from environment (DO NOT hardcode passwords):
#   BARK_DEPLOY_HOST=root@49.234.185.33   (default if unset)
#   BARK_DEPLOY_PASS=...                  (optional — required only if you
#                                         can't set up SSH keys yet)
#
# Recommended: install your public key on the server once
#   ssh-copy-id $BARK_DEPLOY_HOST
# then this script will use key auth and BARK_DEPLOY_PASS becomes unnecessary.
#
# What it does:
#   1. rsync douyin-bundle/* to /var/www/bark-to-game/ on the host
#   2. copy deploy/nginx/bark-to-game.conf into sites-enabled (idempotent)
#   3. nginx -t && systemctl reload nginx

set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${BARK_DEPLOY_HOST:-root@49.234.185.33}"
REMOTE_ROOT="/var/www/bark-to-game"

# Pick the right SSH/SCP wrapper. Password-auth fallback uses sshpass — only
# active when BARK_DEPLOY_PASS is set; otherwise we trust the user's SSH keys.
SSH=(ssh -o StrictHostKeyChecking=accept-new)
RSYNC_RSH=(ssh -o StrictHostKeyChecking=accept-new)
SCP=(scp -o StrictHostKeyChecking=accept-new)
if [[ -n "${BARK_DEPLOY_PASS:-}" ]]; then
  if ! command -v sshpass >/dev/null; then
    echo "ERROR: BARK_DEPLOY_PASS is set but sshpass is not installed."
    echo "  brew install sshpass    # macOS"
    echo "  apt install sshpass     # Debian/Ubuntu"
    exit 1
  fi
  SSH=(sshpass -p "$BARK_DEPLOY_PASS" ssh -o StrictHostKeyChecking=accept-new)
  RSYNC_RSH=(sshpass -p "$BARK_DEPLOY_PASS" ssh -o StrictHostKeyChecking=accept-new)
  SCP=(sshpass -p "$BARK_DEPLOY_PASS" scp -o StrictHostKeyChecking=accept-new)
fi

echo "==> ensure remote dir + nginx exist"
"${SSH[@]}" "$HOST" "
  set -e
  mkdir -p $REMOTE_ROOT
  if ! command -v nginx >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq nginx
  fi
"

echo "==> sync douyin-bundle -> $HOST:$REMOTE_ROOT"
if command -v rsync >/dev/null; then
  rsync -az --delete -e "${RSYNC_RSH[*]}" \
    douyin-bundle/ "$HOST:$REMOTE_ROOT/"
else
  echo "(rsync missing, falling back to scp -r)"
  "${SCP[@]}" -r douyin-bundle/. "$HOST:$REMOTE_ROOT/"
fi

echo "==> install nginx site"
"${SCP[@]}" deploy/nginx/bark-to-game.conf \
  "$HOST:/etc/nginx/sites-available/bark-to-game"
"${SSH[@]}" "$HOST" "
  set -e
  ln -sf /etc/nginx/sites-available/bark-to-game /etc/nginx/sites-enabled/bark-to-game
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl reload nginx
"

echo "==> verify"
url="http://${HOST#*@}/"
echo "  curl $url"
curl -fsS -o /dev/null -w "  -> HTTP %{http_code}  (%{size_download} bytes)\n" "$url"
echo "done."
