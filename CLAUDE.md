# bark-to-game — Project CLAUDE.md

This file is the operating manual for any Claude (Code / Sonnet / Opus) working on this repo.

## Mission

Convert human-mimicked dog barks into playable HTML5 games.

```
microphone → audio features (librosa + YAMNet) → compound token sequence
  → translation layer (Claude API, Verbalized Sampling, style cards)
  → game spec → Claude Agent SDK → Phaser 4 game in generated-games/{id}/
  → Playwright self-validation loop → playable game served to frontend
```

Inspiration: <https://www.calebleak.com/posts/dog-game/>. Core thesis: **the magic is not in the input, it is in the surrounding system.**

## Stack

- Backend: Python 3.13, FastAPI, `uv`, librosa, TF Hub YAMNet (requires `tf-keras` + `TF_USE_LEGACY_KERAS=1`), `claude-agent-sdk` (>=0.2.82)
- Frontend: Vite, React 19, TypeScript (strict), Tailwind v4, shadcn/ui, TanStack Router + Query
- Game template: Phaser 4, Vite, TypeScript (based on `phaserjs/template-vite-ts`)
- Tests: pytest (backend), Vitest (frontend), Playwright (e2e desktop + mobile)

## Branch strategy

- `main` — stable, manually promoted from `dev`
- `dev` — integration branch; all feature PRs merge here
- `feat/phase-N-*` — feature branches developed in `git worktree`

## Skill loading rules (mandatory)

| When | Skill |
|---|---|
| Every task start | `using-superpowers` |
| Worktree operation | `git-worktree` |
| Frontend work | `frontend-design` + `ui-ux-pro-max` |
| End of dev, before PR | `simplify` |
| Merging PR to `dev` | `git-pr-merge` (PJR) |
| End-to-end validation | `webapp-testing` (Playwright) |

Never skip a skill. If a required skill is missing, **stop and report** rather than improvise.

## 5 development principles (non-negotiable)

1. **Single responsibility** — one service / method does one thing.
2. **Minimal code** — no backwards compatibility, prefer breaking change to bloat.
3. **Strict types** — TypeScript: no `any`, compile errors fixed immediately. Python: type-hinted, `mypy` clean.
4. **KISS** — if it needs explanation, it is too complex.
5. **Documentation confidence** — never write code from speculation. For critical surfaces (payments, DB, external APIs, AI tool contracts), if docs are unclear, **stop and ask the user for verified references**.

## Modification rule (no patching)

Solve at the root. Refactor / adjust / integrate with existing logic instead of layering patches. The final code must be concise and complete — not "the change was small," but "the result is clean."

## Acceptance — fault-finder mindset

The job is not to verify it works; the job is **to find what is wrong**.

### Frontend
- Playwright must drive both desktop and mobile viewports.
- Walk full user journeys: every button click, every input, every navigation. Screenshots alone are not validation.
- Test normal flow + edge / error flow.
- Cross-page audit checklist:
  - text overflow / truncation
  - inconsistent wording across pages
  - information density / layout balance
  - noise / out-of-scope / leaking info
  - inconsistent corner radius / shadow / spacing tokens

### Backend (non-AI endpoints)
- Expected success path + expected error path.

### Backend (AI endpoints)
Two dimensions:
- **Decision quality** — does the prompt / context / constraint enable the AI to complete complex tasks?
- **Execution quality** — do the tools, once called, return results aligned with what the AI expected?

Minimum 3 complex scenarios per AI endpoint:
- minimal input (can the AI plausibly expand?)
- complex / noisy input (does the AI extract a coherent theme?)
- deceptive input (does the AI degrade gracefully or misclassify?)

## Anti-homogenization mechanics

Reference: [Verbalized Sampling (arXiv 2510.01171)](https://arxiv.org/abs/2510.01171).

| Layer | Strategy |
|---|---|
| Input | compound tokens (type × pitch × duration × intensity × contour) + session-level summary prefix + audio SHA256 → LLM seed |
| Translation | Verbalized Sampling (k=5 candidates with probabilities) + style-card triplet (art × mechanic × mood) + MAP-Elites archive de-dup |
| Generation | per-round rewrite of generation `CLAUDE.md` + random `visual_recipes/` injection + auto judge + reroll on similarity |

## Directory layout

```
bark-to-game/
├── backend/             # FastAPI (audio, translation, generation orchestration)
├── frontend/            # React (recording UI, game list, game player)
├── game-template/       # Phaser 4 template Claude builds on top of
├── generated-games/     # gitignored output dir
├── style_cards/         # JSON pools: art_styles / mechanics / moods
├── visual_recipes/      # markdown recipes (palette + fonts + motion vocabulary)
└── docs/                # PLAN, ARCHITECTURE, REFERENCES
```

## PR workflow per phase

1. Open worktree on `feat/phase-N-*` based on `dev`.
2. Develop. Stay inside worktree.
3. Run `simplify` skill on changed code.
4. Push branch, open PR against `dev`.
5. Run `git-pr-merge` (PJR) — lint, build, logic verification, merge.
6. Playwright end-to-end on `dev` after merge (desktop + mobile).
7. Remove worktree.

## References

- Caleb Leak's full stack (MIT): <https://github.com/cleak/quasar-saz>, <https://github.com/cleak/tea-leaves>, <https://github.com/cleak/DogKeyboard>
- HTML5 closest analog (MIT): <https://github.com/abagames/claude-one-button-game-creation>
- Phaser 4 official Vite TS template (MIT): <https://github.com/phaserjs/template-vite-ts>
- Claude Agent SDK (Python): <https://github.com/anthropics/claude-agent-sdk-python>
- Verbalized Sampling paper: <https://arxiv.org/abs/2510.01171>
