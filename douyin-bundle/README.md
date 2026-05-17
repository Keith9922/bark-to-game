# douyin-bundle

A self-contained static showcase of bark-to-game. Used for two delivery channels:

1. **抖音虚拟创作平台 · 互动空间** — zipped (`bark-to-game-douyin.zip`) and uploaded as an interactive-space submission. Platform requires a root `index.html` and `<= 8 MB` total.
2. **Live demo host** at <http://49.234.185.33> — same bundle served by nginx from `/var/www/bark-to-game/`.

Both routes are deliberately static and dependency-free: no backend, no API key, no `node_modules`. The "real-time" record → analyze → translate → generate chain is the dev experience under `backend/` + `frontend/`; this bundle is the share-anywhere preview.

## Contents

| Path | What |
|---|---|
| `index.html` | Landing page (amber-CRT theme matching the React app) with the API-not-connected notice and the game grid. Vanilla HTML/CSS/JS, no build step. |
| `games/bark-scrambler-9000.html` | Y2K-glitch memory game (cubism + datamosh) |
| `games/concrete-verdict.html` | International Typographic Style sorting game |
| `games/schematics-rain-down.html` | Blueprint catch game |

Each `games/*.html` is an inline self-contained game (one file, Canvas 2D + Web Audio API, no CDNs) — the same artifacts our backend produces today.

## Rebuild the upload zip

```
./scripts/build-douyin-bundle.sh
```

Output: `bark-to-game-douyin.zip` in the repo root. The script asserts the size is under the 8 MB platform limit.

## Redeploy the live demo

```
# one-off: install your key on the server
ssh-copy-id root@49.234.185.33

# then any time
./scripts/deploy-static.sh
```

The script rsyncs the bundle, installs `deploy/nginx/bark-to-game.conf`, reloads nginx, and curls the URL to confirm 200.

If you don't have key auth set up yet you can fall back to a one-shot password (needs `sshpass` installed):

```
BARK_DEPLOY_PASS='...' ./scripts/deploy-static.sh
```

(Avoid keeping passwords in your shell history — prefer `ssh-copy-id` once and forget it.)

## Updating the game list

To swap or add a game:

1. Drop the self-contained HTML file into `games/`.
2. Edit the `GAMES` array at the bottom of `index.html` (title, meta, blurb, src).
3. `./scripts/build-douyin-bundle.sh` to verify the zip stays under 8 MB.
4. `./scripts/deploy-static.sh` to push to the live host.
