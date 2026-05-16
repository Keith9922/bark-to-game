import type { ReactNode } from 'react'
import type { TranslateResponse } from '../lib/api'

interface Props {
  translation: TranslateResponse
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-amber-crt/50">{label}</div>
      <div className="text-amber-crt/90 text-sm mt-0.5 leading-relaxed">{children}</div>
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
      <header className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h2 id="concept-section-heading" className="font-display text-2xl sm:text-3xl text-signal">
          AI 想做的游戏
        </h2>
        <span className="text-xs text-amber-crt/50">
          从 {candidate_count} 个候选里挑了置信度最高的 ({chosen_probability.toFixed(2)})
        </span>
      </header>
      <p className="text-xs sm:text-sm text-amber-crt/60 mb-5">
        基于刚才听到的内容 + 一份随机抽到的风格契约。下一步会根据这个生成可玩游戏。
      </p>

      <div className="space-y-5">
        <div>
          <h3 className="font-display text-3xl sm:text-4xl text-amber-crt leading-tight">
            {chosen.title}
          </h3>
          <p className="text-amber-crt/80 mt-1 italic text-sm sm:text-base">{chosen.tagline}</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
          <Field label="🎮 玩家角色">{chosen.player}</Field>
          <Field label="🎯 核心玩法">{chosen.core_mechanic}</Field>
          <Field label="🏆 胜利条件">{chosen.win_condition}</Field>
          <Field label="💀 失败条件">{chosen.fail_condition}</Field>
        </div>

        <div className="space-y-3">
          <Field label="🎨 视觉风格">{chosen.visual_summary}</Field>
          <Field label="🔊 声音氛围">{chosen.audio_summary}</Field>
        </div>
      </div>

      <footer className="mt-6 pt-4 border-t border-amber-crt/10 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-amber-crt/60">
        <div>
          美术：<span className="text-signal">{style_triplet.art.name}</span>
        </div>
        <div>
          机制：<span className="text-signal">{style_triplet.mechanic.name}</span>
        </div>
        <div>
          氛围：<span className="text-signal">{style_triplet.mood.name}</span>
        </div>
        <div className="sm:col-span-3">
          配方：<span className="text-signal">{visual_recipe}</span>
        </div>
      </footer>
    </section>
  )
}
