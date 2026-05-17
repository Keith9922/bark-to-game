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
  const [expanded, setExpanded] = useState(true)

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

  if (entries.length === 0 && !loading && !error) return null

  return (
    <section
      aria-labelledby="history-section-heading"
      className="border border-amber-crt/30 p-5 sm:p-6 w-full"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h2 id="history-section-heading" className="font-display text-2xl sm:text-3xl text-signal">
          📜 历史记录
        </h2>
        <div className="flex items-center gap-3 text-xs text-amber-crt/50">
          <span>{entries.length} 个游戏 · 当前话题</span>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="border border-amber-crt/30 px-2 py-0.5 hover:bg-amber-crt/10"
            aria-expanded={expanded}
          >
            {expanded ? '收起 ▴' : '展开 ▾'}
          </button>
        </div>
      </header>
      <p className="text-xs sm:text-sm text-amber-crt/60 mb-4">
        这个话题下生成过的游戏。点击链接打开新标签页玩；保留原始录音的可以直接回放。
      </p>

      {error && <p className="text-xs text-red-400 mb-3">载入历史失败：{error}</p>}

      {expanded && (
        <ol className="space-y-4">
          {entries.map((entry) => (
            <li key={entry.game_id} className="border border-amber-crt/15 p-4 space-y-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-display text-lg sm:text-xl text-amber-crt leading-tight">
                  {entry.title}
                </h3>
                <span className="text-xs text-amber-crt/50">
                  {formatRelative(entry.created_at)}
                </span>
              </div>

              <p className="text-xs sm:text-sm text-amber-crt/80 italic">{entry.tagline}</p>

              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-amber-crt/60">
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
                  <div className="text-xs text-amber-crt/50">🎙️ 原始录音</div>
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
                  className="inline-flex items-center gap-1 px-4 py-2 border-2 border-signal text-signal hover:bg-signal/10 font-display text-sm"
                >
                  ↗ 玩这个游戏
                </a>
                {!entry.has_audio && (
                  <span className="text-xs text-amber-crt/40">
                    （此版本之前生成的游戏没有保留录音）
                  </span>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
