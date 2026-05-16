const SYSTEM_CHECKS = [
  { status: 'ok', label: 'react 19 + vite 8' },
  { status: 'ok', label: 'typescript strict' },
  { status: 'ok', label: 'tailwind v4' },
  { status: 'ok', label: 'vitest + testing-library' },
  { status: 'pending', label: 'phase 1 — audio capture (browser + librosa + YAMNet)' },
  { status: 'pending', label: 'phase 2 — translation layer (VS + style cards)' },
  { status: 'pending', label: 'phase 3 — generation + feedback (Claude Agent SDK)' },
] as const

function App() {
  return (
    <main className="min-h-dvh bg-black text-amber-crt flex flex-col items-center px-6 py-16 sm:py-24">
      <div className="w-full max-w-3xl space-y-12">
        <header className="space-y-6">
          <div className="flex items-center gap-3 text-xs sm:text-sm text-amber-crt/60 uppercase tracking-widest">
            <span
              aria-hidden="true"
              className="inline-block size-2 rounded-full bg-signal motion-safe:animate-pulse"
            />
            <span>SYS_STATUS · PHASE_0_SCAFFOLD_OK</span>
          </div>

          <h1 className="font-display text-6xl sm:text-7xl md:text-8xl leading-none tracking-tight text-amber-crt">
            bark<span className="text-signal">_</span>to<span className="text-signal">_</span>game
          </h1>

          <p className="max-w-2xl text-base sm:text-lg leading-relaxed text-amber-crt/80">
            Audio interface for generating playable HTML5 games from human-mimicked dog barks.
            <br />
            librosa &amp; YAMNet route signal into Claude Agent SDK; Phaser renders the result.
          </p>
        </header>

        <section
          aria-labelledby="system-check-heading"
          className="border border-amber-crt/30 p-5 sm:p-6"
        >
          <h2
            id="system-check-heading"
            className="font-display text-2xl sm:text-3xl text-signal mb-4"
          >
            $ system_check
          </h2>
          <ul className="space-y-1 text-sm">
            {SYSTEM_CHECKS.map((check) => (
              <li
                key={check.label}
                className={check.status === 'ok' ? 'text-amber-crt/80' : 'text-amber-crt/40'}
              >
                [{check.status}] {check.label}
              </li>
            ))}
          </ul>
        </section>

        <footer className="text-xs text-amber-crt/40">
          bark-to-game · phase 0 · <span className="text-signal">●</span> all systems nominal
        </footer>
      </div>
    </main>
  )
}

export default App
