# bark-to-game · plan

## Business requirement

Convert audio of a human mimicking dog barks into a playable HTML5 game.

```
microphone → audio analysis → "game concept" → playable Phaser game
```

The point isn't to interpret a fake bark "correctly" — there is no correct interpretation. The point is to demonstrate that **a high-quality surrounding system can turn low-information input into a coherent, repeatable creative output**. We invert Caleb Leak's [dog game](https://www.calebleak.com/posts/dog-game/): instead of a real dog producing real noise that becomes a game, a human pretends to be a dog and the system fills in the rest.

## User journey (target — fully realised by end of Phase 3)

1. Open the app on phone or desktop.
2. Grant microphone permission.
3. Hold a button and bark for 2–5 seconds.
4. See the extracted audio token sequence (transparency — show what the system "heard").
5. See a generated game concept (theme / mechanic / mood) in plain language.
6. Wait while the game is built (live progress).
7. Play the game in an iframe; share / save / regenerate.

## Phase split (one PR per phase, one worktree per PR)

| Phase | Branch | Scope | Acceptance |
|---|---|---|---|
| **0** | `feat/phase-0-scaffold` | Repo bootstrap, three sub-projects, dev tooling, docs | typecheck + lint + format + test + build green on all three; Playwright loads the placeholder on desktop + mobile |
| **1** | `feat/phase-1-audio` | Browser recording UI; `/api/audio/analyze` backend (librosa + YAMNet → compound tokens); transparency UI | Different inputs produce different tokens; mobile mic flow works; 8 edge cases handled |
| **2** | `feat/phase-2-translate` | Translation layer (tokens → game concept), Verbalized Sampling, style cards, MAP-Elites archive, Anthropic API client | Decision-quality tests pass on 3 complex AI scenarios; 10 consecutive runs produce diverse concepts |
| **3** | `feat/phase-3-generate` | Claude Agent SDK integration; per-round `CLAUDE.md` rewrite; visual recipes; game output to `generated-games/{id}/`; Playwright auto-judge + reroll; frontend game player | Generated games run; full e2e (desktop + mobile) walks every interaction in normal + edge scenarios |

## Explicit non-goals (for now)

- Multi-tenant deployment (single user, localhost).
- Auth, accounts, persistence beyond local files.
- Real-time streaming generation (we wait for completion and show progress).
- Original audio classifier training (YAMNet is sufficient).
- Hardware feeders, robot dogs, or any of the original article's hardware experiments.
