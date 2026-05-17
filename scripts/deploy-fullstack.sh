#!/usr/bin/env bash
# Deploy the full-stack bark-to-game (React SPA + FastAPI backend) to the
# demo host.
#
# Reads SSH credentials from environment (DO NOT hardcode passwords):
#   BARK_DEPLOY_HOST=root@49.234.185.33   (default if unset)
#   BARK_DEPLOY_PASS=...                  (optional one-shot; prefer ssh-copy-id)
#
# What it does:
#   1. Build the frontend locally (relative API base) -> frontend/dist/
#   2. Ensure server has: uv, ffmpeg, libsndfile1, nginx
#   3. rsync backend source (no .venv, no __pycache__) + style_cards +
#      visual_recipes + game_assets to /opt/bark-to-game/
#   4. rsync frontend/dist/ -> /opt/bark-to-game/frontend-dist/
#   5. Upload backend/.env (assumed to live locally, gitignored)
#   6. uv sync on the server (installs Python 3.13 + deps in /opt/.../backend/.venv)
#   7. Install + restart systemd unit
#   8. Install + reload nginx site (replaces the static-only site if present)
#   9. curl the public URL and the API health to verify
#
# Idempotent: re-runs upgrade frontend dist + restart backend + reload nginx.

set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${BARK_DEPLOY_HOST:-root@49.234.185.33}"
REMOTE_ROOT="/opt/bark-to-game"
HOSTNAME_ONLY="${HOST#*@}"

SSH=(ssh -o StrictHostKeyChecking=accept-new)
SCP=(scp -o StrictHostKeyChecking=accept-new)
RSYNC_RSH="ssh -o StrictHostKeyChecking=accept-new"
if [[ -n "${BARK_DEPLOY_PASS:-}" ]]; then
  if ! command -v sshpass >/dev/null; then
    echo "ERROR: BARK_DEPLOY_PASS is set but sshpass is not installed."
    echo "  brew install sshpass    # macOS"
    echo "  apt install sshpass     # Debian/Ubuntu"
    exit 1
  fi
  SSH=(sshpass -p "$BARK_DEPLOY_PASS" ssh -o StrictHostKeyChecking=accept-new)
  SCP=(sshpass -p "$BARK_DEPLOY_PASS" scp -o StrictHostKeyChecking=accept-new)
  RSYNC_RSH="sshpass -p $BARK_DEPLOY_PASS ssh -o StrictHostKeyChecking=accept-new"
fi

if [[ ! -f backend/.env ]]; then
  echo "ERROR: backend/.env not found. Copy backend/.env.example -> backend/.env"
  echo "       and fill BARK_API_KEY before deploying."
  exit 1
fi

echo "==> [1/9] build frontend (relative API base)"
( cd frontend && npm install --silent && VITE_BACKEND_URL='' npm run build )
test -f frontend/dist/index.html

echo "==> [2/9] ensure server prerequisites"
"${SSH[@]}" "$HOST" '
  set -e
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ffmpeg libsndfile1 nginx >/dev/null
  if ! command -v uv >/dev/null && ! [ -x /root/.local/bin/uv ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  /root/.local/bin/uv --version
  mkdir -p /opt/bark-to-game/backend /opt/bark-to-game/frontend-dist /opt/bark-to-game/data
'

echo "==> [3/9] sync backend source"
rsync -az --delete \
  -e "$RSYNC_RSH" \
  --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  backend/ "$HOST:$REMOTE_ROOT/backend/"
rsync -az --delete -e "$RSYNC_RSH" style_cards/      "$HOST:$REMOTE_ROOT/style_cards/"
rsync -az --delete -e "$RSYNC_RSH" visual_recipes/   "$HOST:$REMOTE_ROOT/visual_recipes/"
rsync -az --delete -e "$RSYNC_RSH" game_assets/      "$HOST:$REMOTE_ROOT/game_assets/"

echo "==> [4/9] sync frontend dist"
rsync -az --delete -e "$RSYNC_RSH" frontend/dist/ "$HOST:$REMOTE_ROOT/frontend-dist/"

echo "==> [5/9] upload backend/.env (gitignored secret, mode 600)"
"${SCP[@]}" backend/.env "$HOST:$REMOTE_ROOT/backend/.env"
"${SSH[@]}" "$HOST" "chmod 600 $REMOTE_ROOT/backend/.env"

echo "==> [6/9] uv sync on server (installs Python 3.13 + deps)"
"${SSH[@]}" "$HOST" "
  set -e
  cd $REMOTE_ROOT/backend
  /root/.local/bin/uv sync
"

echo "==> [7/9] install + restart systemd unit"
"${SCP[@]}" deploy/systemd/bark-to-game.service "$HOST:/etc/systemd/system/bark-to-game.service"
"${SSH[@]}" "$HOST" '
  set -e
  systemctl daemon-reload
  systemctl enable bark-to-game.service
  systemctl restart bark-to-game.service
  sleep 3
  systemctl --no-pager --full status bark-to-game.service | head -20 || true
'

echo "==> [8/9] install + reload nginx (full-stack site)"
"${SCP[@]}" deploy/nginx/bark-to-game-fullstack.conf \
  "$HOST:/etc/nginx/sites-available/bark-to-game"
"${SSH[@]}" "$HOST" '
  set -e
  ln -sf /etc/nginx/sites-available/bark-to-game /etc/nginx/sites-enabled/bark-to-game
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl reload nginx
'

echo "==> [9/9] verify"
echo "  curl http://${HOSTNAME_ONLY}/"
curl -fsS -o /dev/null -w "    -> HTTP %{http_code}  (%{size_download} bytes)\n" \
  "http://${HOSTNAME_ONLY}/"
echo "  curl http://${HOSTNAME_ONLY}/health  (retry up to 60 s for backend cold-load)"
for i in $(seq 1 30); do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
    "http://${HOSTNAME_ONLY}/health" || echo "000")
  if [[ "$code" == "200" ]]; then
    echo "    -> HTTP 200 (after ${i}x2s)"
    break
  fi
  sleep 2
done
echo "done. open http://${HOSTNAME_ONLY}/"
