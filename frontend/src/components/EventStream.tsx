import { useEffect, useRef, useState } from 'react'
import { openJobStream, type JobEvent, type JobEventType } from '../lib/api'

interface Props {
  jobId: string
}

interface Line {
  id: number
  type: JobEventType
  text: string
  detail?: string // e.g. countdown for rate_limit
}

const MAX_LINES = 6
const STALE_AFTER_S = 30

function rateLimitText(
  data: Record<string, unknown>,
  nowMs: number,
): { text: string; detail: string | undefined } {
  const status = String(data.status ?? 'unknown')
  const resetsAt = typeof data.resets_at === 'number' ? data.resets_at : null

  if (status === 'rejected') {
    if (resetsAt) {
      const secondsLeft = Math.max(0, Math.round(resetsAt - nowMs / 1000))
      const minutes = Math.floor(secondsLeft / 60)
      const sec = secondsLeft % 60
      const fmt = minutes > 0 ? `${minutes} 分 ${sec} 秒` : `${secondsLeft} 秒`
      return { text: '⛔ Claude Max 配额已满', detail: `约 ${fmt} 后重置，可重试` }
    }
    return { text: '⛔ Claude Max 配额已满', detail: '请稍后重试' }
  }
  if (status === 'allowed_warning') {
    return { text: '⚠️ Claude Max 配额接近上限', detail: undefined }
  }
  return { text: `配额状态：${status}`, detail: undefined }
}

function formatEvent(event: JobEvent, nowMs: number): Omit<Line, 'id'> | null {
  // Heartbeats and the initial hello frame don't need a dedicated line.
  switch (event.type) {
    case 'heartbeat':
    case 'hello':
      return null
    case 'rate_limit':
      return { type: event.type, ...rateLimitText(event.data, nowMs) }
    case 'write': {
      const file = String(event.data.file_path ?? '?').split('/').pop()
      return { type: event.type, text: `✍️ 写入 ${file}` }
    }
    case 'message': {
      const preview = String(event.data.preview ?? '')
      return { type: event.type, text: `💭 Claude: ${preview.slice(0, 80)}` }
    }
    case 'done':
      return { type: event.type, text: '✅ 游戏文件已生成' }
    case 'failed':
      return { type: event.type, text: `❌ 生成失败：${event.data.error ?? '未知'}` }
    case 'cancelled':
      return { type: event.type, text: '✕ 已停止' }
    default:
      return null
  }
}

function lineColorClass(type: JobEventType): string {
  switch (type) {
    case 'rate_limit':
      return 'text-yellow-300'
    case 'failed':
      return 'text-red-400'
    case 'done':
      return 'text-signal'
    default:
      return 'text-amber-crt/80'
  }
}

export default function EventStream({ jobId }: Props) {
  const [lines, setLines] = useState<Line[]>([])
  const [lastContactMs, setLastContactMs] = useState<number>(() => Date.now())
  // Bumped each second so the "last contact: Ns ago" tag stays current.
  const [, setTick] = useState(0)
  const nextIdRef = useRef(0)

  useEffect(() => {
    setLines([])
    setLastContactMs(Date.now())
    nextIdRef.current = 0

    return openJobStream(jobId, {
      onEvent: (event) => {
        setLastContactMs(Date.now())
        const partial = formatEvent(event, Date.now())
        if (!partial) return
        nextIdRef.current += 1
        const line: Line = { id: nextIdRef.current, ...partial }
        setLines((prev) => [...prev, line].slice(-MAX_LINES))
      },
    })
  }, [jobId])

  useEffect(() => {
    const id = window.setInterval(() => setTick((x) => x + 1), 1000)
    return () => window.clearInterval(id)
  }, [])

  const sinceContactS = Math.max(0, Math.round((Date.now() - lastContactMs) / 1000))
  const stale = sinceContactS >= STALE_AFTER_S

  return (
    <section
      aria-label="Generation event stream"
      className="border border-amber-crt/20 bg-amber-crt/[0.02] p-3 sm:p-4 space-y-2"
    >
      <header className="flex items-center justify-between text-[10px] uppercase tracking-wider text-amber-crt/50 font-mono">
        <span>· LIVE EVENTS ·</span>
        <span className={stale ? 'text-yellow-400' : ''}>上次事件:{sinceContactS}s 前</span>
      </header>
      {lines.length === 0 ? (
        <p className="text-xs text-amber-crt/40 font-mono">等待 Claude 的第一条响应…</p>
      ) : (
        <ul className="space-y-1 font-mono text-xs">
          {lines.map((line) => (
            <li key={line.id} className={lineColorClass(line.type)}>
              <span>{line.text}</span>
              {line.detail && <span className="text-amber-crt/60 ml-2">— {line.detail}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
