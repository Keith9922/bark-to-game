import { useState } from 'react'
import RecordButton from './components/RecordButton'
import TokenList from './components/TokenList'
import { postAnalyze, type AnalyzeResponse } from './lib/api'

type Phase =
  | { kind: 'idle' }
  | { kind: 'recording' }
  | { kind: 'processing' }
  | { kind: 'success'; result: AnalyzeResponse }
  | { kind: 'error'; message: string }

function statusLine(phase: Phase): string {
  switch (phase.kind) {
    case 'idle':
      return 'SYS_STATUS · READY'
    case 'recording':
      return 'SYS_STATUS · CAPTURING'
    case 'processing':
      return 'SYS_STATUS · ANALYZING…'
    case 'success': {
      const n = phase.result.tokens.length
      return `SYS_STATUS · ${n} TOKEN${n === 1 ? '' : 'S'} EMITTED`
    }
    case 'error':
      return 'SYS_STATUS · ERROR'
  }
}

function statusDotClass(phase: Phase): string {
  switch (phase.kind) {
    case 'recording':
      return 'bg-signal motion-safe:animate-pulse'
    case 'error':
      return 'bg-red-500'
    default:
      return 'bg-signal'
  }
}

function App() {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })

  const handleRecorded = async (blob: Blob) => {
    setPhase({ kind: 'processing' })
    try {
      const result = await postAnalyze(blob)
      setPhase({ kind: 'success', result })
    } catch (err) {
      setPhase({ kind: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }

  return (
    <main className="min-h-dvh bg-black text-amber-crt flex flex-col items-center px-6 py-12 sm:py-16">
      <div className="w-full max-w-3xl space-y-10">
        <header className="space-y-5">
          <div className="flex items-center gap-3 text-xs sm:text-sm text-amber-crt/60 uppercase tracking-widest">
            <span
              aria-hidden
              className={`inline-block size-2 rounded-full ${statusDotClass(phase)}`}
            />
            <span>{statusLine(phase)}</span>
          </div>
          <h1 className="font-display text-5xl sm:text-6xl md:text-7xl leading-none tracking-tight text-amber-crt">
            bark<span className="text-signal">_</span>to<span className="text-signal">_</span>game
          </h1>
          <p className="text-sm sm:text-base text-amber-crt/70 max-w-xl">
            Hold the dial below and mimic a dog. We extract pitch, duration, intensity, and classify
            each segment via librosa + YAMNet. Phase 2 will translate these tokens into a game
            concept.
          </p>
        </header>

        <div className="flex justify-center py-6">
          <RecordButton
            disabled={phase.kind === 'processing'}
            onRecordingStart={() => setPhase({ kind: 'recording' })}
            onRecorded={handleRecorded}
            onError={(message) => setPhase({ kind: 'error', message })}
          />
        </div>

        {phase.kind === 'success' && <TokenList result={phase.result} />}

        {phase.kind === 'error' && (
          <section
            role="alert"
            className="border border-red-500/50 bg-red-500/5 p-5 text-sm text-red-400"
          >
            <strong className="font-display text-base text-red-400">ERROR </strong>
            {phase.message}
          </section>
        )}

        <footer className="text-xs text-amber-crt/40 pt-8">
          bark-to-game · phase 1 · librosa + YAMNet
        </footer>
      </div>
    </main>
  )
}

export default App
