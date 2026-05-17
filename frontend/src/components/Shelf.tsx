import { useState } from 'react'
import HistoryPanel from './HistoryPanel'
import ShowcasePanel from './ShowcasePanel'

interface Props {
  sessionId: string
  refreshKey: number
  /**
   * How many showcase items to render by default when the showcase tab is
   * the active one. The full panel internally hides the rest behind a
   * "查看全部" button so the page doesn't get overwhelming on idle.
   */
  showcasePreviewLimit?: number
}

type Tab = 'showcase' | 'history'

/**
 * Bottom-of-page shelf that swaps between the cross-session showcase and the
 * current-session history. Mounted only when the app is idle (not analyzing,
 * not generating) — once a recording starts, the active flow takes over the
 * page and the shelf is removed entirely.
 *
 * Default tab is the showcase: a brand-new visitor has no history yet, so
 * the most useful "what is this thing" answer is "look at these works".
 */
export default function Shelf({ sessionId, refreshKey, showcasePreviewLimit = 6 }: Props) {
  const [tab, setTab] = useState<Tab>('showcase')

  return (
    <section
      aria-label="历史与作品集"
      className="border border-amber-crt/20 bg-amber-crt/[0.015]"
    >
      <div
        role="tablist"
        aria-label="切换 历史 / 作品集"
        className="flex border-b border-amber-crt/20"
      >
        <TabButton active={tab === 'showcase'} onClick={() => setTab('showcase')}>
          🎨 作品集 · Works
        </TabButton>
        <TabButton active={tab === 'history'} onClick={() => setTab('history')}>
          📝 历史记录 · History
        </TabButton>
      </div>

      <div className="p-3 sm:p-4">
        {tab === 'showcase' ? (
          <ShowcasePanel previewLimit={showcasePreviewLimit} />
        ) : (
          <HistoryPanel sessionId={sessionId} refreshKey={refreshKey} />
        )}
      </div>
    </section>
  )
}

interface TabButtonProps {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}

function TabButton({ active, onClick, children }: TabButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={[
        'flex-1 px-3 sm:px-4 py-2.5 text-xs sm:text-sm font-mono transition-colors',
        '-webkit-tap-highlight-color: transparent',
        active
          ? 'text-signal border-b-2 border-signal -mb-px bg-amber-crt/5'
          : 'text-amber-crt/60 hover:text-amber-crt hover:bg-amber-crt/[0.03]',
      ].join(' ')}
      style={{ WebkitTapHighlightColor: 'transparent' }}
    >
      {children}
    </button>
  )
}
