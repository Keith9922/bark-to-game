import { linkProps } from './lib/router'
import WorksGrid from './components/WorksGrid'

/**
 * The /works route — full archive of every AI-created work. Reachable by:
 *   - clicking 📚 作品集 in the home page header
 *   - clicking 查看全部 → at the bottom of the home preview
 *   - typing /works in the URL bar (nginx falls back unknown paths to
 *     index.html, so direct-loads work)
 */
export default function WorksPage() {
  return (
    <main className="min-h-dvh bg-black text-amber-crt flex flex-col items-center px-6 py-10 sm:py-14">
      <div className="w-full max-w-3xl space-y-8">
        <header className="space-y-4">
          <div className="text-xs">
            <a
              {...linkProps('/')}
              className="text-amber-crt/60 hover:text-signal transition-colors"
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              ← 返回主页
            </a>
          </div>

          <h1 className="font-display text-4xl sm:text-5xl leading-none tracking-tight text-amber-crt">
            bark<span className="text-signal">_</span>to<span className="text-signal">_</span>game
            <span className="block text-base sm:text-lg text-amber-crt/70 font-mono mt-3">
              · 作品集 · The Works
            </span>
          </h1>

          <p className="text-sm text-amber-crt/80 max-w-xl leading-relaxed">
            过去每一声狗叫都被 AI 翻译成了一个互动小作品。所有创作都按时间倒序排在下面 — 点开 ↗
            打开作品，点 🎙️ 听当时的原始狗叫。
          </p>
        </header>

        <section aria-label="完整作品列表">
          <WorksGrid />
        </section>

        <footer className="pt-6 border-t border-amber-crt/20 text-[11px] text-amber-crt/40">
          <p>每一份作品都是 AI 现场写成的单文件交互。</p>
          <p>
            <a
              {...linkProps('/')}
              className="text-amber-crt/60 hover:text-signal"
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              ← 回到录音主页
            </a>
          </p>
        </footer>
      </div>
    </main>
  )
}
