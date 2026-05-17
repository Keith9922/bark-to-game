import { useEffect, useState } from 'react'
import { fetchShowcase, playUrlFor, type ShowcaseItem } from '../lib/api'

/**
 * Showcase of every playable work the backend has ever generated, scanned
 * from `generated-games/`. The intent is that a brand-new visitor — who
 * hasn't recorded anything yet — can immediately see (and open) what AI
 * has produced before, so they understand what's about to happen when
 * they hit the record button.
 *
 * Independent of the per-session history panel: history is scoped to one
 * session_id, showcase is the global archive across every session.
 */

function extractTitle(summary: string, fallbackId: string): string {
  // SUMMARY.md files typically open with `**TITLE** — blurb` or `TITLE — blurb`.
  // Strip leading markdown bold + grab everything before the first em/en dash.
  const stripped = summary.replace(/^\*+|\*+$/g, '').trim()
  const match = stripped.match(/^([^—–\-\n]+?)(?:\s*[—–\-]|\n|$)/)
  const candidate = match ? match[1].trim() : ''
  return candidate || `作品 ${fallbackId.slice(0, 6)}`
}

function extractBlurb(summary: string): string {
  // After the title separator, take the next sentence.
  const after = summary.replace(/^[^—–\-]+[—–\-]\s*/, '').trim()
  return after.split('\n')[0].trim()
}

export default function ShowcasePanel() {
  const [items, setItems] = useState<ShowcaseItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<ShowcaseItem | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchShowcase()
      .then((rows) => {
        setItems(rows)
        setLoading(false)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (open === null) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(null)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  if (loading) {
    return (
      <section className="border border-amber-crt/20 bg-amber-crt/[0.02] p-5">
        <p className="text-xs text-amber-crt/40 font-mono">加载历史作品…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="border border-amber-crt/20 bg-amber-crt/[0.02] p-5">
        <p className="text-xs text-amber-crt/40 font-mono">
          作品索引暂不可用（{error}）
        </p>
      </section>
    )
  }

  if (items.length === 0) {
    return null
  }

  return (
    <>
      <section
        aria-label="历史作品集"
        className="border border-amber-crt/30 bg-amber-crt/[0.02] p-4 sm:p-5 space-y-4"
      >
        <header className="space-y-1">
          <h2 className="font-display text-xl text-amber-crt">
            🎨 作品集 · {items.length} 个 AI 创作
          </h2>
          <p className="text-xs text-amber-crt/60 leading-relaxed">
            过去每一声狗叫都被 AI 翻译成了一个互动小作品。点开看看是什么样。
          </p>
        </header>

        <div className="grid gap-3 sm:grid-cols-2">
          {items.map((item) => {
            const title = extractTitle(item.summary, item.game_id)
            const blurb = extractBlurb(item.summary)
            return (
              <button
                key={item.game_id}
                type="button"
                onClick={() => setOpen(item)}
                className="text-left border border-amber-crt/20 hover:border-amber-crt/60 hover:bg-amber-crt/5 p-3 transition-colors group"
              >
                <div className="font-display text-base text-signal group-hover:text-amber-crt truncate">
                  {title}
                </div>
                {blurb && (
                  <div className="text-xs text-amber-crt/60 mt-1 line-clamp-2">{blurb}</div>
                )}
                <div className="text-[10px] text-amber-crt/40 mt-2 font-mono">
                  {(item.size_bytes / 1024).toFixed(1)} KB · {item.game_id.slice(0, 8)}
                </div>
              </button>
            )
          })}
        </div>
      </section>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="作品查看器"
          className="fixed inset-0 z-50 flex flex-col bg-black"
        >
          <div
            className="flex items-center justify-between px-3 py-2 border-b border-amber-crt/20"
            style={{ paddingTop: 'max(0.5rem, env(safe-area-inset-top))' }}
          >
            <span className="text-xs text-amber-crt/60 font-mono truncate flex-1 mr-3">
              {extractTitle(open.summary, open.game_id)}
            </span>
            <button
              type="button"
              onClick={() => setOpen(null)}
              className="text-xs text-amber-crt border border-amber-crt/30 px-3 py-1.5 hover:bg-amber-crt/10"
            >
              ✕ 关闭
            </button>
          </div>
          <iframe
            title={open.game_id}
            src={playUrlFor(open.play_url)}
            allow="autoplay; gamepad; fullscreen"
            className="flex-1 w-full border-0 bg-black"
          />
        </div>
      )}
    </>
  )
}
