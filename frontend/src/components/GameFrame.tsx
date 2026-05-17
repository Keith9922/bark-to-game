import { playUrlFor } from '../lib/api'

export interface PlayableGame {
  game_id: string
  summary: string
  play_url: string
}

interface Props {
  game: PlayableGame
  onRestart?: () => void
}

export default function GameFrame({ game, onRestart }: Props) {
  const src = playUrlFor(game.play_url)

  return (
    <section
      aria-labelledby="play-section-heading"
      className="border border-amber-crt/30 p-3 sm:p-4 w-full space-y-3"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="play-section-heading" className="font-display text-2xl sm:text-3xl text-signal">
          🎮 游戏已就绪
        </h2>
        <span className="text-xs text-amber-crt/50">编号 {game.game_id}</span>
      </header>

      {game.summary && game.summary !== '(no summary)' && (
        <p className="text-xs sm:text-sm text-amber-crt/70 italic leading-relaxed">
          {game.summary}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3 pt-1">
        <a
          href={src}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 px-5 py-3 border-2 border-signal text-signal hover:bg-signal/10 font-display text-base sm:text-lg"
        >
          ↗ 在新标签页打开游戏
        </a>
        {onRestart && (
          <button
            type="button"
            onClick={onRestart}
            className="inline-flex items-center gap-2 px-4 py-3 border border-amber-crt/40 text-amber-crt/80 hover:bg-amber-crt/10 font-mono text-sm"
          >
            🔁 再录一次
          </button>
        )}
      </div>

      <details className="text-xs text-amber-crt/50">
        <summary className="cursor-pointer hover:text-amber-crt/80">也可以直接在下方预览</summary>
        <iframe
          src={src}
          title={`bark-to-game ${game.game_id}`}
          className="mt-2 w-full aspect-video bg-black border border-amber-crt/20"
          allow="autoplay; microphone"
        />
        <p className="mt-2 font-mono break-all">
          直链：
          <a href={src} target="_blank" rel="noreferrer" className="underline text-amber-crt/70">
            {src}
          </a>
        </p>
      </details>
    </section>
  )
}
