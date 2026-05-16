import { useState } from 'react'
import ConceptCard from './components/ConceptCard'
import GameFrame, { type PlayableGame } from './components/GameFrame'
import RecordButton from './components/RecordButton'
import TokenList from './components/TokenList'
import {
  pollJobUntilDone,
  postAnalyze,
  postGenerate,
  postTranslate,
  type AnalyzeResponse,
  type JobView,
  type TranslateResponse,
} from './lib/api'

type Phase =
  | { kind: 'idle' }
  | { kind: 'recording' }
  | { kind: 'analyzing' }
  | { kind: 'translating'; tokens: AnalyzeResponse }
  | {
      kind: 'generating'
      tokens: AnalyzeResponse
      concept: TranslateResponse
      jobId: string | null
      elapsedS: number
      jobStatus: 'pending' | 'running'
    }
  | {
      kind: 'playable'
      tokens: AnalyzeResponse
      concept: TranslateResponse
      game: PlayableGame
    }
  | {
      kind: 'error'
      message: string
      tokens?: AnalyzeResponse
      concept?: TranslateResponse
    }

function formatElapsed(s: number): string {
  const total = Math.round(s)
  const m = Math.floor(total / 60)
  const sec = total % 60
  return m > 0 ? `${m}m ${sec.toString().padStart(2, '0')}s` : `${sec}s`
}

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
    case 'generating':
      return `SYS_STATUS · ${phase.concept.chosen.title.toUpperCase()} · BUILDING (${formatElapsed(phase.elapsedS)})`
    case 'playable':
      return 'SYS_STATUS · GAME READY · PLAY'
    case 'error':
      return 'SYS_STATUS · ERROR'
  }
}

function statusDotClass(phase: Phase): string {
  switch (phase.kind) {
    case 'recording':
    case 'analyzing':
    case 'translating':
    case 'generating':
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
    case 'generating':
    case 'playable':
    case 'error':
      return phase.tokens
    default:
      return undefined
  }
}

function conceptFromPhase(phase: Phase): TranslateResponse | undefined {
  switch (phase.kind) {
    case 'generating':
    case 'playable':
    case 'error':
      return phase.concept
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
    let concept: TranslateResponse
    try {
      concept = await postTranslate(tokens)
    } catch (err) {
      setPhase({
        kind: 'error',
        message: `translate: ${err instanceof Error ? err.message : String(err)}`,
        tokens,
      })
      return
    }

    setPhase({
      kind: 'generating',
      tokens,
      concept,
      jobId: null,
      elapsedS: 0,
      jobStatus: 'pending',
    })

    try {
      const accepted = await postGenerate(tokens, concept)
      setPhase({
        kind: 'generating',
        tokens,
        concept,
        jobId: accepted.job_id,
        elapsedS: 0,
        jobStatus: accepted.status === 'running' ? 'running' : 'pending',
      })

      const onProgress = (job: JobView) => {
        setPhase((current) =>
          current.kind === 'generating' && current.jobId === job.job_id
            ? {
                ...current,
                elapsedS: job.elapsed_s,
                jobStatus: job.status === 'running' ? 'running' : 'pending',
              }
            : current,
        )
      }

      const final = await pollJobUntilDone(accepted.job_id, {
        intervalMs: 5000,
        onProgress,
      })

      if (final.status === 'done' && final.game_id && final.play_url) {
        setPhase({
          kind: 'playable',
          tokens,
          concept,
          game: {
            game_id: final.game_id,
            summary: final.summary ?? '',
            play_url: final.play_url,
          },
        })
      } else {
        setPhase({
          kind: 'error',
          message: `generate: ${final.error ?? 'unknown failure'}`,
          tokens,
          concept,
        })
      }
    } catch (err) {
      setPhase({
        kind: 'error',
        message: `generate: ${err instanceof Error ? err.message : String(err)}`,
        tokens,
        concept,
      })
    }
  }

  const tokens = tokensFromPhase(phase)
  const concept = conceptFromPhase(phase)
  const recordDisabled =
    phase.kind === 'analyzing' || phase.kind === 'translating' || phase.kind === 'generating'

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
            Hold the dial below and mimic a dog. Audio → librosa + YAMNet tokens → Claude translates
            into a game concept (with Verbalized Sampling + diversity guard) → Claude Code writes a
            playable HTML5 game using the asset playbook.
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
          <section className="border border-amber-crt/30 p-5 text-sm text-amber-crt/70">
            <span className="font-display text-base text-signal motion-safe:animate-pulse">
              $ translating…
            </span>{' '}
            5 candidate concepts under a random style triplet + visual recipe; picking the most
            diverse.
          </section>
        )}

        {concept && <ConceptCard translation={concept} />}

        {phase.kind === 'generating' && (
          <section className="border border-amber-crt/30 p-5 text-sm text-amber-crt/70 space-y-2">
            <div>
              <span className="font-display text-base text-signal motion-safe:animate-pulse">
                $ building…
              </span>{' '}
              Claude Code is writing a self-contained HTML game (concept + visual recipe +
              playbook). This is an async job; polling every 5 s.
            </div>
            <div className="text-xs text-amber-crt/50 font-mono">
              {phase.jobId ? (
                <>
                  job <span className="text-amber-crt/80">{phase.jobId}</span> · status{' '}
                  <span className="text-signal">{phase.jobStatus}</span> · elapsed{' '}
                  <span className="text-amber-crt/80">{formatElapsed(phase.elapsedS)}</span>
                </>
              ) : (
                'queuing job…'
              )}
            </div>
          </section>
        )}

        {phase.kind === 'playable' && <GameFrame game={phase.game} />}

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
          bark-to-game · phase 3 · Claude Agent SDK + playbook · async jobs
        </footer>
      </div>
    </main>
  )
}

export default App
