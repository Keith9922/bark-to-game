# bark-to-game

> Generate playable HTML5 games from human-mimicked dog barks.

Inspired by [Caleb Leak — "I Taught My Dog to Vibe Code Games"](https://www.calebleak.com/posts/dog-game/), but inverted: instead of a dog typing on a keyboard, a human mimics dog barks into the microphone. The audio is feature-extracted, classified, and translated into prompts that drive Claude Agent SDK to produce a playable Phaser game.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.13 + FastAPI + librosa + YAMNet (TF Hub) + Claude Agent SDK |
| Frontend | React 19 + Vite + TypeScript + Tailwind v4 + shadcn/ui |
| Game template | Phaser 4 + Vite + TypeScript |
| Testing | pytest, Vitest, Playwright (desktop + mobile) |

## Status

Phase 0 — scaffolding in progress.

## Development

See [`CLAUDE.md`](./CLAUDE.md) for the operating manual (dev standards, branch strategy, skill loading rules, anti-homogenization mechanics).

## License

MIT — see [`LICENSE`](./LICENSE).
