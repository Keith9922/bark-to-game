# bark-to-game frontend

React 19 + Vite 8 + TypeScript 6 + Tailwind v4. Records audio in the browser, displays analysis tokens, and plays generated games.

Phase 0 ships a placeholder landing page that proves the toolchain works.

## Requirements

- Node 22+
- pnpm 9+

## Setup

```bash
pnpm install
```

## Develop

```bash
pnpm dev          # http://localhost:5173
```

## Quality gates

```bash
pnpm test         # vitest watch
pnpm test:run     # vitest single run
pnpm typecheck    # tsc --noEmit (project references)
pnpm lint         # eslint
pnpm format:check # prettier
pnpm build        # production build (tsc + vite)
```
