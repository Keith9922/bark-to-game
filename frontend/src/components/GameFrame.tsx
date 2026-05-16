import { playUrlFor } from '../lib/api'

export interface PlayableGame {
  game_id: string
  summary: string
  play_url: string
}

interface Props {
  game: PlayableGame
}

export default function GameFrame({ game }: Props) {
  const src = playUrlFor(game.play_url)

  return (
    <section
      aria-labelledby="play-section-heading"
      className="border border-amber-crt/30 p-3 sm:p-4 w-full"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <h2 id="play-section-heading" className="font-display text-2xl sm:text-3xl text-signal">
          $ play
        </h2>
        <span className="text-xs text-amber-crt/50">game {game.game_id}</span>
      </header>

      <iframe
        src={src}
        title={`bark-to-game ${game.game_id}`}
        className="w-full aspect-video bg-black border border-amber-crt/20"
        allow="autoplay; microphone"
      />

      {game.summary && game.summary !== '(no summary)' && (
        <p className="text-xs text-amber-crt/60 mt-3 italic leading-relaxed">{game.summary}</p>
      )}

      <p className="text-xs text-amber-crt/40 mt-2 font-mono">
        play directly at{' '}
        <a href={src} target="_blank" rel="noreferrer" className="underline text-amber-crt/60">
          {src}
        </a>
      </p>
    </section>
  )
}
