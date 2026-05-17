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

interface Props {
  /**
   * If set, render only the first N items by default and show a "查看全部"
   * button that expands the rest. Useful when the panel is mounted inside
   * a Shelf and we don't want to dump 18 cards on the page at once.
   */
  previewLimit?: number
}

export default function ShowcasePanel({ previewLimit }: Props = {}) {
  const [items, setItems] = useState<ShowcaseItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<ShowcaseItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(false)

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
    return <p className="text-xs text-amber-crt/40 font-mono">加载作品中…</p>
  }

  if (error) {
    return (
      <p className="text-xs text-amber-crt/40 font-mono">
        作品索引暂不可用（{error}）
      </p>
    )
  }

  if (items.length === 0) {
    return (
      <p className="text-xs text-amber-crt/40 font-mono">
        还没有作品 — 录一声狗叫，AI 就给你做一个。
      </p>
    )
  }

  // When previewLimit is set, only show the first N items until the user
  // explicitly asks for more.
  const visible = previewLimit && !expanded ? items.slice(0, previewLimit) : items
  const hiddenCount = items.length - visible.length

  return (
    <>
      <div className="space-y-3">
        <p className="text-xs text-amber-crt/60 leading-relaxed">
          过去每一声狗叫都被 AI 翻译成了一个互动小作品。共
          <span className="text-signal mx-1">{items.length}</span>
          个，点开看看是什么样。
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          {visible.map((item) => {
            const title = extractTitle(item.summary, item.game_id)
            const blurb = extractBlurb(item.summary)
            return (
              <button
                key={item.game_id}
                type="button"
                onClick={() => setOpen(item)}
                className="text-left border border-amber-crt/20 hover:border-amber-crt/60 hover:bg-amber-crt/5 p-3 transition-colors group"
                style={{ WebkitTapHighlightColor: 'transparent' }}
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

        {hiddenCount > 0 && (
          <div className="pt-1 text-center">
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="text-xs text-amber-crt/70 hover:text-signal font-mono border border-amber-crt/30 hover:border-signal px-4 py-1.5 transition-colors"
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              查看全部 {items.length} 个作品 · See all ({hiddenCount} more)
            </button>
          </div>
        )}
      </div>

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
