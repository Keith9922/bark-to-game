import { useState } from 'react'
import { audioPlayUrl, playUrlFor, type WorkItem } from '../lib/api'

interface Props {
  work: WorkItem
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

/**
 * One AI-creation card. Compact by default; the original-bark audio (when
 * preserved) lives behind a 🎙️ toggle so a column of cards stays scrollable
 * on mobile. The play action opens the work in a new tab — that's a clean
 * shareable URL and avoids us juggling iframe modal state.
 */
export default function WorkCard({ work }: Props) {
  const [audioOpen, setAudioOpen] = useState(false)
  const hasMeta = work.has_history && (work.art || work.mechanic || work.mood)
  const hasAudio = Boolean(work.audio_url)

  return (
    <article className="border border-amber-crt/20 hover:border-amber-crt/50 p-4 space-y-3 transition-colors">
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="font-display text-base sm:text-lg text-amber-crt leading-tight truncate">
          {work.title}
        </h3>
        <span className="text-[11px] text-amber-crt/50 shrink-0">
          {formatRelative(work.created_at)}
        </span>
      </header>

      {work.tagline && (
        <p className="text-xs text-amber-crt/80 italic line-clamp-3">{work.tagline}</p>
      )}

      {hasMeta && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-amber-crt/60">
          {work.art && (
            <span>
              美术 <span className="text-signal">{work.art}</span>
            </span>
          )}
          {work.mechanic && (
            <span>
              机制 <span className="text-signal">{work.mechanic}</span>
            </span>
          )}
          {work.mood && (
            <span>
              氛围 <span className="text-signal">{work.mood}</span>
            </span>
          )}
          {work.visual_recipe && (
            <span>
              配方 <span className="text-signal">{work.visual_recipe}</span>
            </span>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 pt-1">
        <a
          href={playUrlFor(work.play_url)}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 px-3 py-1.5 border-2 border-signal text-signal hover:bg-signal/10 font-display text-xs sm:text-sm"
          style={{ WebkitTapHighlightColor: 'transparent' }}
        >
          ↗ 打开作品
        </a>

        {hasAudio && (
          <button
            type="button"
            onClick={() => setAudioOpen((v) => !v)}
            className="text-xs text-amber-crt/70 hover:text-amber-crt border border-amber-crt/30 px-2.5 py-1.5"
            aria-expanded={audioOpen}
            style={{ WebkitTapHighlightColor: 'transparent' }}
          >
            🎙️ 原始狗叫 {audioOpen ? '▴' : '▾'}
          </button>
        )}
      </div>

      {hasAudio && audioOpen && work.audio_url && (
        <audio
          controls
          src={audioPlayUrl(work.audio_url)}
          className="w-full"
          preload="metadata"
        >
          您的浏览器不支持 audio 元素。
        </audio>
      )}
    </article>
  )
}
