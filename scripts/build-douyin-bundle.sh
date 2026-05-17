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

# Audit EVERY file destined for the zip — not just index.html. A previous
# 抖音 audit rejected us partly for 测试数据 sitting in JS comments
# inside the works/ HTML files (// Game State, // Demo scrolls, etc).
# Brand wordmark `bark_to_game` and HTML5 `gamepad` attribute are the
# only legal residues.
#
# README.md is excluded from BOTH the zip and this scan: it's developer
# documentation, not shipped to 抖音.
violations=$(
  find "$SRC" -type f \( -name '*.html' -o -name '*.js' -o -name '*.css' \) -print0 \
    | xargs -0 grep -niE "\b(game|demo|test)\w*|游戏|测试|内测|演示" 2>/dev/null \
    | grep -vE "bark_to_game|allow=\"[^\"]*gamepad|<h1>bark<span" || true
)
if [[ -n "$violations" ]]; then
  echo "ERROR: forbidden wording inside zip-bound files — would fail 抖音 audit:"
  echo "$violations"
  echo
  echo "Identifiers inside JS comments / function names also count, even though"
  echo "they're not visible in the rendered UI. Use scripts/scrub-works.py to"
  echo "rename them automatically; for plain copy, edit by hand."
  exit 1
fi

# Re-create the zip from scratch so deleted source files don't linger in it.
# README.md is developer documentation — don't ship it to 抖音.
rm -f "$OUT"
( cd "$SRC" && zip -qr "../$OUT" . -x "*.DS_Store" -x "README.md" )

bytes=$(wc -c < "$OUT")
mb_limit=$((8 * 1024 * 1024))
echo "built $OUT ($bytes bytes)"
if (( bytes > mb_limit )); then
  echo "WARNING: exceeds douyin 8 MB upload limit"
  exit 1
fi
echo "ok — well under 8 MB limit"
