import type { AnalyzeResponse, TokenSegment } from '../lib/api'

interface Props {
  result: AnalyzeResponse
}

function formatToken(token: TokenSegment): string {
  return [token.type, token.pitch, token.duration, token.intensity, token.contour].join(' · ')
}

function confidenceLabel(token: TokenSegment): string {
  const pct = Math.round(token.confidence * 100)
  return `${pct}% ${token.source}`
}

export default function TokenList({ result }: Props) {
  const { tokens, summary, audio_hash, duration_ms } = result

  return (
    <section
      aria-labelledby="token-section-heading"
      className="border border-amber-crt/30 p-5 sm:p-6 w-full"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
        <h2 id="token-section-heading" className="font-display text-2xl sm:text-3xl text-signal">
          $ token_stream
        </h2>
        <span className="text-xs text-amber-crt/50 font-mono">
          hash <span className="text-amber-crt/80">{audio_hash}</span> · {duration_ms}ms
        </span>
      </header>

      <dl className="grid grid-cols-3 gap-3 text-xs sm:text-sm text-amber-crt/80 mb-5 border-b border-amber-crt/10 pb-4">
        <div>
          <dt className="text-amber-crt/50 uppercase tracking-wide">rhythm</dt>
          <dd className="text-signal mt-1">{summary.rhythm}</dd>
        </div>
        <div>
          <dt className="text-amber-crt/50 uppercase tracking-wide">mood</dt>
          <dd className="text-signal mt-1">{summary.mood}</dd>
        </div>
        <div>
          <dt className="text-amber-crt/50 uppercase tracking-wide">entropy</dt>
          <dd className="text-signal mt-1">{summary.entropy.toFixed(2)}</dd>
        </div>
      </dl>

      {tokens.length === 0 ? (
        <p className="text-sm text-amber-crt/60">
          no segments detected — the recording was silent or below threshold.
        </p>
      ) : (
        <ol className="space-y-1 text-sm font-mono">
          {tokens.map((token, i) => (
            <li key={`${token.start_ms}-${i}`} className="flex flex-wrap gap-x-3">
              <span className="text-amber-crt/40 tabular-nums">
                {String(token.start_ms).padStart(4, ' ')}
                ms
              </span>
              <span className="text-amber-crt">[{formatToken(token)}]</span>
              <span className="text-amber-crt/40">· {confidenceLabel(token)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
