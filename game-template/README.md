# bark-to-game · game template

Phaser 4 + Vite + TypeScript scaffold. Claude Agent SDK clones this template per generation and emits game-specific scenes / sprites / mechanics on top of it.

Based on the official [phaserjs/template-vite-ts](https://github.com/phaserjs/template-vite-ts) (MIT). Telemetry (`log.js`) and marketing build messages have been stripped — we don't want noise during automated generation.

## What's here

```
src/
├── main.ts                  # Mounts Phaser to #game-container
├── vite-env.d.ts
└── game/
    ├── main.ts              # Phaser.Game config (size, scenes, physics)
    └── scenes/
        ├── Boot.ts          # Tiny preloader (loading bar assets)
        ├── Preloader.ts     # Loads game assets (images, audio)
        ├── MainMenu.ts      # Title screen
        ├── Game.ts          # Main gameplay scene
        └── GameOver.ts      # Win / loss screen
```

`public/assets/` holds runtime assets (`bg.png`, `logo.png`). Generated games will add more assets here.

## Setup

```bash
pnpm install
```

## Develop

```bash
pnpm dev       # http://localhost:8080
```

## Quality gates

```bash
pnpm typecheck    # tsc --noEmit
pnpm build        # production build (terser-minified)
```

## Why a separate sub-project (not nested in `frontend/`)?

Generated games are self-contained — each is a clone of this template with custom scenes. Keeping the template independent makes it trivial for Claude Agent SDK to `cp -r game-template generated-games/{id}` and work on a sealed copy.

## Attribution

This template is derived from [phaserjs/template-vite-ts](https://github.com/phaserjs/template-vite-ts) (MIT, Phaser Studio Inc.).
