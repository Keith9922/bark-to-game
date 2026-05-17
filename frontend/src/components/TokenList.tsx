import type { AnalyzeResponse, TokenSegment } from '../lib/api'

interface Props {
  result: AnalyzeResponse
}

const RHYTHM_LABEL: Record<string, string> = {
  STACCATO: '急促',
  TRIPLET: '三连',
  SPACED: '舒缓',
  SPARSE: '稀疏',
  SILENT: '静默',
}

const MOOD_LABEL: Record<string, string> = {
  AGITATED: '激动',
  MELANCHOLY: '哀伤',
  PLAYFUL: '欢快',
  STEADY: '平稳',
  CALM: '安静',
}

function localiseRhythm(value: string): string {
  return RHYTHM_LABEL[value] ?? value
}

function localiseMood(value: string): string {
  return MOOD_LABEL[value] ?? value
}

function formatToken(token: TokenSegment): string {
  return [token.type, token.pitch, token.duration, token.intensity, token.contour].join(' · ')
}

function confidenceLabel(token: TokenSegment): string {
  const pct = Math.round(token.confidence * 100)
  const source = token.source === 'yamnet' ? 'YAMNet' : '简易判别'
  return `${pct}% · ${source}`
}

export default function TokenList({ result }: Props) {
  const { tokens, summary, audio_hash, duration_ms } = result

  return (
    <section
      aria-labelledby="token-section-heading"
      className="border border-amber-crt/30 p-5 sm:p-6 w-full"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h2 id="token-section-heading" className="font-display text-2xl sm:text-3xl text-signal">
          AI 听见了什么
        </h2>
        <span className="text-xs text-amber-crt/50 font-mono">
          {(duration_ms / 1000).toFixed(2)} 秒 · {audio_hash}
        </span>
      </header>
      <p className="text-xs sm:text-sm text-amber-crt/60 mb-5">
        把你的声音切成若干"音节"，给每段标出类型 / 音高 / 时长 / 力度 / 走向。
      </p>

      <dl className="grid grid-cols-3 gap-3 text-xs sm:text-sm text-amber-crt/80 mb-5 border-b border-amber-crt/10 pb-4">
        <div>
          <dt className="text-amber-crt/50">节奏</dt>
          <dd className="text-signal mt-1">{localiseRhythm(summary.rhythm)}</dd>
          <dd className="text-amber-crt/40 text-xs">{summary.rhythm}</dd>
        </div>
        <div>
          <dt className="text-amber-crt/50">情绪</dt>
          <dd className="text-signal mt-1">{localiseMood(summary.mood)}</dd>
          <dd className="text-amber-crt/40 text-xs">{summary.mood}</dd>
        </div>
        <div>
          <dt className="text-amber-crt/50">变化度</dt>
          <dd className="text-signal mt-1">{summary.entropy.toFixed(2)}</dd>
          <dd className="text-amber-crt/40 text-xs">entropy 0-1</dd>
        </div>
      </dl>

      {tokens.length === 0 ? (
        <p className="text-sm text-amber-crt/60">
          没听到声音 —— 录音里没有可识别的"音节"。请大声再来一次。
        </p>
      ) : (
        <ol className="space-y-1 text-sm font-mono">
          {tokens.map((token, i) => (
            <li key={`${token.start_ms}-${i}`} className="flex flex-wrap gap-x-3">
              <span className="text-amber-crt/40 tabular-nums">
                {String(token.start_ms).padStart(4, ' ')}ms
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
