import { useCallback, useEffect, useState } from 'react'
import { audioPlayUrl, fetchHistory, playUrlFor, type HistoryEntry } from '../lib/api'

interface Props {
  sessionId: string
  /** Bumped by the parent when a new game completes — triggers a re-fetch. */
  refreshKey?: number
}

function formatRelative(unixSeconds: number): string {
  const ms = Date.now() - unixSeconds * 1000
  if (ms < 0) return '刚刚'
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec} 秒前`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  if (day < 30) return `${day} 天前`
  return new Date(unixSeconds * 1000).toLocaleDateString()
}

export default function HistoryPanel({ sessionId, refreshKey = 0 }: Props) {
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await fetchHistory(sessionId)
      setEntries(list)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  if (loading) {
    return <p className="text-xs text-amber-crt/40 font-mono">加载历史中…</p>
  }
  if (error) {
    return <p className="text-xs text-red-400 font-mono">载入历史失败：{error}</p>
  }
  if (entries.length === 0) {
    return (
      <p className="text-xs text-amber-crt/40 font-mono">
        这个话题还没有生成过作品 — 录一声狗叫开始第一个。
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-amber-crt/60">
        当前话题下生成过的作品，共
        <span className="text-signal mx-1">{entries.length}</span>
        个。保留原始录音的可以直接回放。
      </p>

      <ol className="space-y-3">
        {entries.map((entry) => (
          <li key={entry.game_id} className="border border-amber-crt/15 p-3 sm:p-4 space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-display text-base sm:text-lg text-amber-crt leading-tight">
                {entry.title}
              </h3>
              <span className="text-[11px] text-amber-crt/50">
                {formatRelative(entry.created_at)}
              </span>
            </div>

            <p className="text-xs text-amber-crt/80 italic">{entry.tagline}</p>

            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-amber-crt/60">
              <span>
                美术 <span className="text-signal">{entry.art}</span>
              </span>
              <span>
                机制 <span className="text-signal">{entry.mechanic}</span>
              </span>
              <span>
                氛围 <span className="text-signal">{entry.mood}</span>
              </span>
              <span>
                配方 <span className="text-signal">{entry.visual_recipe}</span>
              </span>
            </div>

            {entry.has_audio && entry.audio_url && (
              <div className="space-y-1">
                <div className="text-[11px] text-amber-crt/50">🎙️ 原始录音</div>
                <audio
                  controls
                  src={audioPlayUrl(entry.audio_url)}
                  className="w-full"
                  preload="none"
                >
                  您的浏览器不支持 audio 元素。
                </audio>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3 pt-1">
              <a
                href={playUrlFor(entry.play_url)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 px-3 py-1.5 border-2 border-signal text-signal hover:bg-signal/10 font-display text-xs sm:text-sm"
                style={{ WebkitTapHighlightColor: 'transparent' }}
              >
                ↗ 玩这个作品
              </a>
              {!entry.has_audio && (
                <span className="text-[10px] text-amber-crt/40">
                  （早期版本未保留录音）
                </span>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
