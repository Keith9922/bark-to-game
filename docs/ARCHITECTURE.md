# bark-to-game · architecture

## Pipeline

```
[browser microphone]
        │  MediaRecorder API (16 kHz mono)
        ▼
[upload audio blob → POST /api/audio/analyze]
        │
        ▼
[backend audio module]
        │  ├─ silence-based segmentation (energy threshold)
        │  ├─ librosa: pyin (F0), onset, spectral centroid, MFCC, RMS, ZCR
        │  └─ YAMNet (tf-keras legacy): Bark / Howl / Yip / Growl / Whimper / Bow-wow
        ▼
[compound token sequence]
        e.g.  [BARK · pitch=LOW · dur=SHORT · int=LOUD · contour=FLAT]
              [HOWL · pitch=HIGH · dur=LONG · int=NORMAL · contour=RISE]
        + session prefix (rhythm, mood, entropy)
        + audio SHA256 → LLM seed
        ▼
[backend translate module — Verbalized Sampling, k=5]
        │  random triplet style-card injection (art × mechanic × mood)
        │  MAP-Elites archive de-dup
        ▼
[game concept JSON]
        { theme, player, mechanic, art_style, audio_mood }
        ▼
[backend generate module — Claude Agent SDK]
        │  cp -r game-template generated-games/{id}
        │  rewrite generated-games/{id}/CLAUDE.md with style contract + visual recipe
        │  spawn Claude Code session in that dir; let it write scenes, sprites, audio
        │  Playwright self-validation loop: load, click, screenshot, judge
        │  reroll if visual similarity ≥7 vs last 5 generations
        ▼
[generated-games/{id}/dist/index.html (built artifact)]
        ▼
[frontend serves & embeds in iframe]
```

## Anti-homogenization (the part most projects skip)

1. **Input** — compound tokens use 5+ orthogonal dimensions, so two recordings rarely produce identical sequences. Audio hash → LLM seed makes the same recording reproducible across runs.
2. **Translation** — Verbalized Sampling forces the model to surface `k=5` alternatives with probabilities, bypassing RLHF mode collapse (recovers 66.8% of base diversity vs 23.8% with naive prompting — per [arXiv 2510.01171](https://arxiv.org/abs/2510.01171)). Style-card triplet plus recent-N archive ensure new outputs land in unoccupied `(style, mechanic, palette)` cells (MAP-Elites pattern).
3. **Generation** — per-round `CLAUDE.md` rewrite (Caleb Leak's verified fix) plus a randomly chosen `visual_recipes/*.md` as a hard style contract. Auto-judge + reroll on visual similarity.

## Module boundaries (single-responsibility enforcement)

| Module | Owns | Does not own |
|---|---|---|
| `backend/audio/` | Segmentation, feature extraction, classification, token formatting | Translation logic, anything LLM |
| `backend/translate/` | Verbalized Sampling, style cards, archive, prompt assembly | Audio interpretation, code generation |
| `backend/generate/` | Claude Agent SDK orchestration, template copy, validation loop | Game logic itself (that lives in `game-template/`) |
| `frontend/` | UI, recording, transparency display, iframe game player | Any audio processing (browser is just a recorder) |
| `game-template/` | Generic Phaser scaffold | Game-specific code (lives only in `generated-games/{id}/`) |

## Why a separate `game-template/` instead of nesting inside `frontend/`

Each generated game is a sealed clone of `game-template/`. The generation module does `cp -r game-template generated-games/{id}` and Claude operates inside that copy — no risk of touching the frontend, the backend, or other generated games. Keeping it top-level makes the boundary obvious from `ls`.
