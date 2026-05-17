# bark-to-game · references

## Inspiration

- Caleb Leak — [I Taught My Dog to Vibe Code Games](https://www.calebleak.com/posts/dog-game/) — the original (forward) direction we're inverting.

## Reusable code (MIT)

- [cleak/quasar-saz](https://github.com/cleak/quasar-saz) — the dog-generated game; ships a full `CLAUDE.md` (~981 lines) with the "eccentric designer" system prompt and 16 dev guidelines. We adapt the prompt to our domain in Phase 3.
- [cleak/tea-leaves](https://github.com/cleak/tea-leaves) — Godot DevTools (only relevant if we ever pivot from HTML5 to Godot).
- [cleak/DogKeyboard](https://github.com/cleak/DogKeyboard) — Rust HID proxy with input allowlist. Architectural reference for our recording pipeline.
- [abagames/claude-one-button-game-creation](https://github.com/abagames/claude-one-button-game-creation) — HTML5 closest analog. Tag-seed → generate → GA balance-test → iterate. We replace the tag-seed with our audio tokens.
- [htdt/godogen](https://github.com/htdt/godogen) — screenshot-grounded self-repair loop. Architectural reference for Phase 3.
- [lackeyjb/playwright-skill](https://github.com/lackeyjb/playwright-skill) — Claude Code Skill for browser automation. Drop-in for our auto-judge loop.

## Tooling

- [Claude Agent SDK (Python)](https://github.com/anthropics/claude-agent-sdk-python) — primary AI integration. Package: `claude-agent-sdk` ≥ 0.2.82.
- [YAMNet on Kaggle Models](https://www.kaggle.com/models/google/yamnet) — 521-class audio classifier. Requires `tf-keras` + `TF_USE_LEGACY_KERAS=1`.
- [librosa](https://librosa.org/) — audio feature extraction.
- [Phaser 4](https://phaser.io/) — game engine.
- [phaserjs/template-vite-ts](https://github.com/phaserjs/template-vite-ts) — official template our `game-template/` is derived from.

## Papers

- [Verbalized Sampling (arXiv 2510.01171)](https://arxiv.org/abs/2510.01171) — k-candidate sampling that bypasses RLHF mode collapse. Foundation of our translation layer.
- [Creative Beam Search (arXiv 2405.00099)](https://arxiv.org/abs/2405.00099) — LLM-as-judge for diverse outputs.
- [Quality-Diversity / MAP-Elites (arXiv 1907.04053)](https://arxiv.org/pdf/1907.04053) — basis of our anti-homogenization archive.
- [Random concept infusion (arXiv 2601.18053)](https://arxiv.org/abs/2601.18053) — basis of our style-card injection.

## Internal navigation

- Operating manual: [`../CLAUDE.md`](../CLAUDE.md)
- Phases + user journey: [`./PLAN.md`](./PLAN.md)
- Pipeline + module boundaries: [`./ARCHITECTURE.md`](./ARCHITECTURE.md)
