import { useState } from 'react'
import ConceptCard from './components/ConceptCard'
import RecordButton from './components/RecordButton'
import TokenList from './components/TokenList'
import { postAnalyze, postTranslate, type AnalyzeResponse, type TranslateResponse } from './lib/api'

type Phase =
  | { kind: 'idle' }
  | { kind: 'recording' }
  | { kind: 'analyzing' }
  | { kind: 'translating'; tokens: AnalyzeResponse }
  | { kind: 'success'; tokens: AnalyzeResponse; concept: TranslateResponse }
  | { kind: 'error'; message: string; tokens?: AnalyzeResponse }

function statusLine(phase: Phase): string {
  switch (phase.kind) {
    case 'idle':
      return 'SYS_STATUS · READY'
    case 'recording':
      return 'SYS_STATUS · CAPTURING'
    case 'analyzing':
      return 'SYS_STATUS · ANALYZING…'
    case 'translating': {
      const n = phase.tokens.tokens.length
      return `SYS_STATUS · ${n} TOKEN${n === 1 ? '' : 'S'} · TRANSLATING…`
    }
    case 'success':
      return 'SYS_STATUS · CONCEPT READY'
    case 'error':
      return 'SYS_STATUS · ERROR'
  }
}

function statusDotClass(phase: Phase): string {
  switch (phase.kind) {
    case 'recording':
    case 'analyzing':
    case 'translating':
      return 'bg-signal motion-safe:animate-pulse'
    case 'error':
      return 'bg-red-500'
    default:
      return 'bg-signal'
  }
}

function tokensFromPhase(phase: Phase): AnalyzeResponse | undefined {
  switch (phase.kind) {
    case 'translating':
    case 'success':
    case 'error':
      return phase.tokens
    default:
      return undefined
  }
}

function App() {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })

  const handleRecorded = async (blob: Blob) => {
    setPhase({ kind: 'analyzing' })
    let tokens: AnalyzeResponse
    try {
      tokens = await postAnalyze(blob)
    } catch (err) {
      setPhase({
        kind: 'error',
        message: `analyze: ${err instanceof Error ? err.message : String(err)}`,
      })
      return
    }

    setPhase({ kind: 'translating', tokens })
    try {
      const concept = await postTranslate(tokens)
      setPhase({ kind: 'success', tokens, concept })
    } catch (err) {
      setPhase({
        kind: 'error',
        message: `translate: ${err instanceof Error ? err.message : String(err)}`,
        tokens,
      })
    }
  }

  const tokens = tokensFromPhase(phase)
  const recordDisabled = phase.kind === 'analyzing' || phase.kind === 'translating'

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
            Hold the dial below and mimic a dog. Audio is segmented and classified (librosa +
            YAMNet), then translated into a game concept via Verbalized Sampling across a rotating
            style-card triplet — diversity guaranteed.
          </p>
        </header>

        <div className="flex justify-center py-6">
          <RecordButton
            disabled={recordDisabled}
            onRecordingStart={() => setPhase({ kind: 'recording' })}
            onRecorded={handleRecorded}
            onError={(message) => setPhase({ kind: 'error', message })}
          />
        </div>

        {tokens && <TokenList result={tokens} />}

        {phase.kind === 'translating' && (
          <section className="border border-amber-crt/30 p-5 sm:p-6 text-sm text-amber-crt/70">
            <span className="font-display text-base text-signal motion-safe:animate-pulse">
              $ translating…
            </span>{' '}
            asking Claude for 5 candidate concepts under random style triplet + visual recipe,
            picking the most diverse vs recent history.
          </section>
        )}

        {phase.kind === 'success' && <ConceptCard translation={phase.concept} />}

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
          bark-to-game · phase 2 · Verbalized Sampling + MAP-Elites archive
        </footer>
      </div>
    </main>
  )
}

export default App
