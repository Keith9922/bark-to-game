#!/usr/bin/env bash
# Build the douyin互动空间 upload bundle.
#
# Output: bark-to-game-douyin.zip in the repo root.
# The bundle is the static showcase:
#   - index.html: landing page with the audio → work pipeline explainer
#   - works/: AI-created interactive HTML files (each a single-file canvas piece)
# Both the source (douyin-bundle/) and the built zip are deterministic — no
# real-time inference, no backend, no secrets.
#
# After every edit to index.html, the script greps for forbidden wording
# (per the platform's audit feedback: 不可使用"游戏"相关表述、不能存在测试数据)
# and refuses to build if any user-visible occurrence sneaks back in. The
# word "game" is allowed only as part of the brand wordmark `bark_to_game`
# and as the standard HTML5 `iframe allow="gamepad"` attribute.

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

# Audit user-facing copy in index.html for forbidden wording. The brand
# wordmark `bark_to_game` and the HTML5 `gamepad` attribute are the only
# legal "game" residue.
violations=$(grep -nE "游戏|测试|内测|演示|DEMO[^_]|GAMES?[^_]" "$SRC/index.html" \
  | grep -vE "bark_to_game|allow=\"[^\"]*gamepad" || true)
if [[ -n "$violations" ]]; then
  echo "ERROR: forbidden wording in $SRC/index.html — would fail 抖音 audit:"
  echo "$violations"
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
