interface Props {
  label: string
  caption?: string
  elapsedS: number
  estimateS?: number
  onCancel?: () => void
}

function formatElapsed(s: number): string {
  const total = Math.round(s)
  const m = Math.floor(total / 60)
  const sec = total % 60
  return m > 0 ? `${m} 分 ${sec.toString().padStart(2, '0')} 秒` : `${sec} 秒`
}

export default function ProgressBar({
  label,
  caption,
  elapsedS,
  estimateS = 120,
  onCancel,
}: Props) {
  // Asymptotic curve so the bar always moves but never "completes" before the
  // real result arrives — discourages users from giving up too early.
  const ratio = 1 - Math.exp(-elapsedS / estimateS)
  const pct = Math.min(0.97, ratio) * 100

  return (
    <section className="border border-amber-crt/30 p-5 w-full space-y-3">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-display text-base sm:text-lg text-signal">{label}</span>
        <span className="text-xs text-amber-crt/60 font-mono">已用 {formatElapsed(elapsedS)}</span>
      </header>
      {caption && <p className="text-xs sm:text-sm text-amber-crt/70">{caption}</p>}
      <div
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        className="w-full h-2 bg-amber-crt/10 overflow-hidden rounded-sm"
      >
        <div
          className="h-full bg-signal transition-all duration-700 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      {onCancel && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="text-xs text-amber-crt/60 hover:text-amber-crt border border-amber-crt/30 px-3 py-1.5 hover:bg-amber-crt/10"
          >
            ✕ 中途停止
          </button>
        </div>
      )}
    </section>
  )
}
