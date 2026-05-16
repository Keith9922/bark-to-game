import type { ReactNode } from 'react'
import type { TranslateResponse } from '../lib/api'

interface Props {
  translation: TranslateResponse
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-amber-crt/50">{label}</div>
      <div className="text-amber-crt/90 text-sm mt-0.5">{children}</div>
    </div>
  )
}

export default function ConceptCard({ translation }: Props) {
  const { chosen, style_triplet, visual_recipe, candidate_count, chosen_probability } = translation

  return (
    <section
      aria-labelledby="concept-section-heading"
      className="border border-amber-crt/30 p-5 sm:p-6 w-full"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-5">
        <h2 id="concept-section-heading" className="font-display text-2xl sm:text-3xl text-signal">
          $ concept
        </h2>
        <span className="text-xs text-amber-crt/50">
          chosen 1 of {candidate_count} · p={chosen_probability.toFixed(2)}
        </span>
      </header>

      <div className="space-y-5">
        <div>
          <h3 className="font-display text-3xl sm:text-4xl text-amber-crt leading-tight">
            {chosen.title}
          </h3>
          <p className="text-amber-crt/80 mt-1 italic text-sm sm:text-base">{chosen.tagline}</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
          <Field label="player">{chosen.player}</Field>
          <Field label="mechanic">{chosen.core_mechanic}</Field>
          <Field label="win">{chosen.win_condition}</Field>
          <Field label="fail">{chosen.fail_condition}</Field>
        </div>

        <div className="space-y-3">
          <Field label="visual">{chosen.visual_summary}</Field>
          <Field label="audio">{chosen.audio_summary}</Field>
        </div>
      </div>

      <footer className="mt-6 pt-4 border-t border-amber-crt/10 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-amber-crt/60">
        <div>
          art: <span className="text-signal">{style_triplet.art.name}</span>
        </div>
        <div>
          mechanic: <span className="text-signal">{style_triplet.mechanic.name}</span>
        </div>
        <div>
          mood: <span className="text-signal">{style_triplet.mood.name}</span>
        </div>
        <div className="sm:col-span-3">
          recipe: <span className="text-signal">{visual_recipe}</span>
        </div>
      </footer>
    </section>
  )
}
