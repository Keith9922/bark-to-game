import { useEffect, useState } from 'react'
import { fetchWorks, type WorkItem } from '../lib/api'
import { linkProps } from '../lib/router'
import WorkCard from './WorkCard'

interface Props {
  /** Cap visible items. Omit to render all. */
  previewLimit?: number
  /** Render the "查看全部 →" link to /works (only useful when previewLimit is set). */
  showAllLink?: boolean
}

/**
 * Grid renderer for the works catalogue. Used twice:
 *   - On the home page with previewLimit=6 + showAllLink → entry teaser
 *   - On /works with no limit → full archive
 */
export default function WorksGrid({ previewLimit, showAllLink = false }: Props) {
  const [items, setItems] = useState<WorkItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchWorks()
      .then((rows) => {
        setItems(rows)
        setLoading(false)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
  }, [])

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

  const visible = previewLimit ? items.slice(0, previewLimit) : items
  const hiddenCount = items.length - visible.length

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {visible.map((work) => (
          <WorkCard key={work.game_id} work={work} />
        ))}
      </div>

      {showAllLink && hiddenCount > 0 && (
        <div className="text-center">
          <a
            {...linkProps('/works')}
            className="inline-block text-xs text-signal hover:text-amber-crt font-mono border border-signal/50 hover:border-amber-crt px-4 py-1.5 transition-colors"
            style={{ WebkitTapHighlightColor: 'transparent' }}
          >
            查看全部 {items.length} 个作品 → See all
          </a>
        </div>
      )}
    </div>
  )
}
