#!/usr/bin/env bash
# Build the douyin互动空间 upload bundle.
#
# Output: bark-to-game-douyin.zip in the repo root.
# The bundle is the static-only display version:
#   - index.html landing page with the API-not-connected notice
#   - games/ contains the AI-generated demo HTML files
# Both the source (douyin-bundle/) and the built zip are deterministic — no
# real-time inference, no backend, no secrets.

set -euo pipefail

cd "$(dirname "$0")/.."

OUT="bark-to-game-douyin.zip"
SRC="douyin-bundle"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: $SRC/ not found"
  exit 1
fi

if [[ ! -f "$SRC/index.html" ]]; then
  echo "ERROR: $SRC/index.html missing — douyin platform requires it as the entry"
  exit 1
fi

# Re-create the zip from scratch so deleted source files don't linger in it.
rm -f "$OUT"
( cd "$SRC" && zip -qr "../$OUT" . -x "*.DS_Store" )

bytes=$(wc -c < "$OUT")
mb_limit=$((8 * 1024 * 1024))
echo "built $OUT ($bytes bytes)"
if (( bytes > mb_limit )); then
  echo "WARNING: exceeds douyin 8 MB upload limit"
  exit 1
fi
echo "ok — well under 8 MB limit"
