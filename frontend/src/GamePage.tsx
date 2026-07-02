import { useState } from 'react'
import { playUrlFor } from './lib/api'
import { linkProps, navigate } from './lib/router'

/**
 * Standalone, shareable game page at /game/{id}. Renders the generated game
 * full-screen by id alone — it does NOT depend on the generation pipeline, so
 * a shared link (or a refresh) loads the game directly. Reached three ways:
 *   - auto-navigated to when a fresh generation finishes
 *   - opened from a /works card
 *   - a shared/pasted URL
 */
interface Props {
  gameId: string
  /** Reset the pipeline and go home to make a new one. */
  onMakeYourOwn: () => void
}

const VALID_ID = /^[A-Za-z0-9-]+$/

export default function GamePage({ gameId, onMakeYourOwn }: Props) {
  const [shareMsg, setShareMsg] = useState<string | null>(null)

  if (!VALID_ID.test(gameId)) {
    return (
      <main className="min-h-dvh bg-black text-amber-crt flex flex-col items-center justify-center gap-4 px-6">
        <p className="font-display text-2xl">游戏不存在</p>
        <a
          {...linkProps('/')}
          className="px-5 py-2 border-2 border-signal text-signal hover:bg-signal/10 font-display"
        >
          ← 返回主页
        </a>
      </main>
    )
  }

  const src = playUrlFor(`/api/game/${gameId}/play`)
  const shareUrl = typeof window !== 'undefined' ? window.location.href : ''

  const share = async () => {
    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({ title: 'bark_to_game', url: shareUrl })
        return
      } catch {
        /* user cancelled or unsupported — fall through to clipboard */
      }
    }
    try {
      await navigator.clipboard.writeText(shareUrl)
      setShareMsg('链接已复制')
    } catch {
      setShareMsg('复制失败，请手动复制地址栏')
    }
    window.setTimeout(() => setShareMsg(null), 2500)
  }

  const goBack = () => {
    if (window.history.length > 1) window.history.back()
    else navigate('/')
  }

  return (
    <main className="min-h-dvh bg-black text-amber-crt flex flex-col">
      <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-amber-crt/20">
        <button
          type="button"
          onClick={goBack}
          className="text-xs text-amber-crt/70 hover:text-signal border border-amber-crt/30 hover:border-signal px-3 py-1.5 transition-colors"
          style={{ WebkitTapHighlightColor: 'transparent' }}
        >
          ← 返回
        </button>
        <span className="font-mono text-[11px] text-amber-crt/50 truncate">游戏 {gameId}</span>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={share}
            className="text-xs text-signal border border-signal/50 hover:bg-signal/10 px-3 py-1.5 transition-colors"
            style={{ WebkitTapHighlightColor: 'transparent' }}
          >
            🔗 {shareMsg ?? '分享'}
          </button>
          <button
            type="button"
            onClick={onMakeYourOwn}
            className="text-xs text-amber-crt/80 border border-amber-crt/30 hover:border-signal hover:text-signal px-3 py-1.5 transition-colors"
            style={{ WebkitTapHighlightColor: 'transparent' }}
          >
            🐕 做一个你自己的
          </button>
        </div>
      </header>

      <iframe
        src={src}
        title={`bark-to-game ${gameId}`}
        className="flex-1 w-full bg-black"
        allow="autoplay; microphone"
      />
    </main>
  )
}
