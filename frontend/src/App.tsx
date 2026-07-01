import { useEffect } from 'react'
import ConceptCard from './components/ConceptCard'
import EventStream from './components/EventStream'
import ProgressBar from './components/ProgressBar'
import Recorder from './components/Recorder'
import SessionSwitcher from './components/SessionSwitcher'
import TokenList from './components/TokenList'
import WorksGrid from './components/WorksGrid'
import GamePage from './GamePage'
import WorksPage from './WorksPage'
import type { AnalyzeResponse, TranslateResponse } from './lib/api'
import { linkProps, navigate, usePath } from './lib/router'
import { useCurrentSessionId } from './lib/useSession'
import { useGenerationJob, type GenPhase, type GenerationJob } from './lib/useGenerationJob'

const STATUS: Record<string, { cn: string; en: string }> = {
  idle: { cn: '等待录音', en: 'READY' },
  analyzing: { cn: '正在分析声音', en: 'ANALYZING' },
  no_sound: { cn: '没听到声音', en: 'NO SOUND' },
  not_a_bark: { cn: '听到了，但不是狗叫', en: 'NOT A BARK' },
  translating: { cn: '正在构思游戏', en: 'TRANSLATING' },
  generating: { cn: '正在生成游戏', en: 'BUILDING' },
  playable: { cn: '游戏就绪', en: 'READY TO PLAY' },
  error: { cn: '出错了', en: 'ERROR' },
}

function statusLine(phase: GenPhase): string {
  const v = STATUS[phase.kind] ?? STATUS.idle
  return `状态：${v.cn} · ${v.en}`
}

function statusDotClass(phase: GenPhase): string {
  switch (phase.kind) {
    case 'analyzing':
    case 'translating':
    case 'generating':
      return 'bg-signal motion-safe:animate-pulse'
    case 'error':
      return 'bg-red-500'
    case 'no_sound':
      return 'bg-amber-crt/60'
    default:
      return 'bg-signal'
  }
}

function tokensFromPhase(phase: GenPhase): AnalyzeResponse | undefined {
  switch (phase.kind) {
    case 'translating':
      return phase.tokens
    case 'generating':
    case 'playable':
    case 'error':
      return phase.tokens ?? undefined
    default:
      return undefined
  }
}

function conceptFromPhase(phase: GenPhase): TranslateResponse | undefined {
  switch (phase.kind) {
    case 'generating':
    case 'playable':
    case 'error':
      return phase.concept ?? undefined
    default:
      return undefined
  }
}

/**
 * The persistent shell. Holds the ONE generation controller and switches views
 * by path — it never unmounts across `/` ↔ `/create` ↔ `/game/{id}`, so the
 * controller's state (concept, result) survives navigation and the browser
 * back button walks game → studio → home naturally.
 */
function App() {
  const path = usePath()
  const [sessionId] = useCurrentSessionId()
  const job = useGenerationJob(sessionId)

  // Route the active generation to its own URL as it progresses. Keyed on the
  // phase kind only, so browser back/forward (which changes path, not phase)
  // is never overridden.
  const phaseKind = job.phase.kind
  const gameId = job.phase.kind === 'playable' ? job.phase.game.game_id : null
  useEffect(() => {
    if (phaseKind === 'playable' && gameId) {
      navigate(`/game/${gameId}`)
    } else if (phaseKind === 'translating' || phaseKind === 'generating') {
      if (window.location.pathname === '/') navigate('/create')
    }
  }, [phaseKind, gameId])

  if (path.startsWith('/game/')) {
    return (
      <GamePage
        gameId={path.slice('/game/'.length)}
        onMakeYourOwn={() => {
          job.reset()
          navigate('/')
        }}
      />
    )
  }
  if (path === '/works') return <WorksPage />
  if (path === '/create') return <StudioView job={job} />
  return <HomeView job={job} />
}

/** `/` — landing + record + showcase. Recording and analysis happen here; once
 *  analysis confirms a bark the shell pushes the run into the studio. */
function HomeView({ job }: { job: GenerationJob }) {
  const { phase, start, reset, fail } = job
  const busy = phase.kind === 'analyzing'

  return (
    <main className="min-h-dvh bg-black text-amber-crt flex flex-col items-center px-6 py-10 sm:py-14">
      <div className="w-full max-w-3xl space-y-8 sm:space-y-10">
        <header className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs sm:text-sm">
            <div className="flex items-center gap-3 text-amber-crt/70">
              <span
                aria-hidden
                className={`inline-block size-2 rounded-full ${statusDotClass(phase)}`}
              />
              <span>{statusLine(phase)}</span>
            </div>
            <div className="flex items-center gap-3">
              <a
                {...linkProps('/works')}
                className="text-xs text-amber-crt/70 hover:text-signal border border-amber-crt/30 hover:border-signal px-3 py-1.5 transition-colors"
                style={{ WebkitTapHighlightColor: 'transparent' }}
              >
                📚 作品集
              </a>
              <SessionSwitcher disabled={busy} onSessionChange={reset} />
            </div>
          </div>

          <h1 className="font-display text-5xl sm:text-6xl md:text-7xl leading-none tracking-tight text-amber-crt">
            bark<span className="text-signal">_</span>to<span className="text-signal">_</span>game
          </h1>

          <div className="space-y-2 max-w-xl">
            <p className="text-base sm:text-lg text-amber-crt/90">
              对着话筒<strong className="text-signal">模仿狗叫</strong>，让 AI
              帮你做一个可玩的小游戏。
            </p>
            <p className="text-xs sm:text-sm text-amber-crt/55 leading-relaxed">
              流程：录音 → 提取声学特征（librosa + YAMNet）→ Claude 翻译成游戏概念 → Claude Code
              写出可玩的 HTML5 游戏。
            </p>
          </div>
        </header>

        <div className="flex justify-center py-4">
          <Recorder disabled={busy} onRecorded={start} onCancel={reset} onError={fail} />
        </div>

        {phase.kind === 'analyzing' && (
          <ProgressBar
            label="正在分析声音 · ANALYZING"
            caption="把你的录音切片，提取音高/时长/力度/节奏。首次冷启动可能 60 秒，之后秒级响应。"
            elapsedS={phase.elapsedS}
            estimateS={20}
          />
        )}

        {phase.kind === 'no_sound' && (
          <section className="border border-amber-crt/40 bg-amber-crt/5 p-5 space-y-3">
            <h3 className="font-display text-xl text-amber-crt">🐕 没听到声音</h3>
            <p className="text-sm text-amber-crt/80">录音里没有可识别的音节。可能是：</p>
            <ul className="text-sm text-amber-crt/70 list-disc list-inside space-y-1">
              <li>话筒离嘴太远</li>
              <li>录音时长太短</li>
              <li>录的是环境噪声，没有清晰的一声</li>
            </ul>
            <button
              type="button"
              onClick={reset}
              className="mt-2 px-5 py-2 border-2 border-signal text-signal hover:bg-signal/10 font-display"
            >
              🔁 重新录音
            </button>
          </section>
        )}

        {phase.kind === 'not_a_bark' && (
          <section className="border border-amber-crt/40 bg-amber-crt/5 p-5 space-y-3">
            <h3 className="font-display text-xl text-amber-crt">🐶 听到了，但不像狗叫</h3>
            <p className="text-sm text-amber-crt/80">
              AI 听到的更像是
              <strong className="text-signal mx-1">{phase.detectedClass || '其他声音'}</strong>
              {phase.rejectedCount > 1 ? `（共 ${phase.rejectedCount} 段都判定为非狗叫）` : ''}。
            </p>
            <p className="text-xs text-amber-crt/60">
              对着话筒认真学一声「汪 / 嗷呜 / 嗯哼」试试。声音越像狗，AI 越能解读。
            </p>
            <button
              type="button"
              onClick={reset}
              className="mt-2 px-5 py-2 border-2 border-signal text-signal hover:bg-signal/10 font-display"
            >
              🔁 再来一声
            </button>
          </section>
        )}

        {phase.kind === 'error' && (
          <section
            role="alert"
            className="border border-red-500/50 bg-red-500/5 p-5 text-sm text-red-400 space-y-3"
          >
            <div>
              <strong className="font-display text-base text-red-400">出错了 · ERROR </strong>
              {phase.message}
            </div>
            <button
              type="button"
              onClick={reset}
              className="px-4 py-2 border border-red-400/60 text-red-300 hover:bg-red-500/10 font-mono text-xs"
            >
              🔁 重试
            </button>
          </section>
        )}

        {phase.kind !== 'analyzing' && (
          <section aria-label="作品预览" className="space-y-3">
            <div className="flex items-baseline justify-between">
              <h2 className="font-display text-lg sm:text-xl text-amber-crt">📚 作品集预览</h2>
              <a
                {...linkProps('/works')}
                className="text-[11px] text-amber-crt/60 hover:text-signal font-mono"
                style={{ WebkitTapHighlightColor: 'transparent' }}
              >
                完整作品集 →
              </a>
            </div>
            <WorksGrid previewLimit={6} showAllLink />
          </section>
        )}

        <footer className="text-xs text-amber-crt/40 pt-8 space-y-1">
          <div>bark-to-game · 模仿狗叫生成游戏</div>
          <div className="text-amber-crt/30">
            想要不同风格？右上角「话题」下拉里新建一个新话题，AI 会记住已用过的风格、刻意避开。
          </div>
        </footer>
      </div>
    </main>
  )
}

/** `/create` — the studio: shows the active run (analyze/translate/generate)
 *  and, on completion, the result with a play CTA. Browser-back from the game
 *  lands here. Empty on a cold visit → bounce home. */
function StudioView({ job }: { job: GenerationJob }) {
  const { phase, cancel, reset } = job

  useEffect(() => {
    if (phase.kind === 'idle') navigate('/', { replace: true })
  }, [phase.kind])

  const tokens = tokensFromPhase(phase)
  const concept = conceptFromPhase(phase)

  return (
    <main className="min-h-dvh bg-black text-amber-crt flex flex-col items-center px-6 py-10 sm:py-14">
      <div className="w-full max-w-3xl space-y-8">
        <header className="flex flex-wrap items-center justify-between gap-3 text-xs sm:text-sm">
          <a
            {...linkProps('/')}
            className="text-amber-crt/60 hover:text-signal transition-colors"
            style={{ WebkitTapHighlightColor: 'transparent' }}
          >
            ← 主页
          </a>
          <div className="flex items-center gap-3 text-amber-crt/70">
            <span
              aria-hidden
              className={`inline-block size-2 rounded-full ${statusDotClass(phase)}`}
            />
            <span>{statusLine(phase)}</span>
          </div>
        </header>

        {tokens && <TokenList result={tokens} />}

        {phase.kind === 'translating' && (
          <ProgressBar
            label="正在构思游戏 · TRANSLATING"
            caption="Claude 在抽取一组风格卡（艺术 × 机制 × 情绪），并产出候选概念，挑最有差异的那个。通常 30 秒–2 分钟。"
            elapsedS={phase.elapsedS}
            estimateS={90}
          />
        )}

        {concept && <ConceptCard translation={concept} />}

        {phase.kind === 'generating' && (
          <div className="space-y-3">
            <ProgressBar
              label="正在生成游戏 · BUILDING"
              caption={`Claude Code 正在按照上面的概念 + 视觉配方写一个独立的 HTML 游戏文件。通常 1–3 分钟，被限流时可能更长。${phase.jobId ? `任务编号 ${phase.jobId}。` : ''}`}
              elapsedS={phase.elapsedS}
              estimateS={120}
              onCancel={cancel}
            />
            <EventStream
              events={phase.events}
              lastEventAt={phase.lastEventAt}
              connection={phase.connection}
            />
          </div>
        )}

        {phase.kind === 'playable' && (
          <section className="border border-signal/40 bg-signal/5 p-5 space-y-4">
            <h2 className="font-display text-2xl sm:text-3xl text-signal">🎮 你的游戏做好了</h2>
            <p className="text-sm text-amber-crt/70">
              这就是你这声狗叫变成的游戏。点开始玩，或把链接分享给朋友。
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => navigate(`/game/${phase.game.game_id}`)}
                className="px-6 py-3 border-2 border-signal text-signal hover:bg-signal/10 font-display text-base sm:text-lg"
              >
                ▶ 开始玩
              </button>
              <button
                type="button"
                onClick={reset}
                className="px-4 py-3 border border-amber-crt/40 text-amber-crt/80 hover:bg-amber-crt/10 font-mono text-sm"
              >
                🔁 再做一个
              </button>
            </div>
          </section>
        )}

        {phase.kind === 'error' && (
          <section
            role="alert"
            className="border border-red-500/50 bg-red-500/5 p-5 text-sm text-red-400 space-y-3"
          >
            <div>
              <strong className="font-display text-base text-red-400">出错了 · ERROR </strong>
              {phase.message}
            </div>
            <button
              type="button"
              onClick={reset}
              className="px-4 py-2 border border-red-400/60 text-red-300 hover:bg-red-500/10 font-mono text-xs"
            >
              🔁 重试
            </button>
          </section>
        )}

        <footer className="text-xs text-amber-crt/40 pt-8">
          <a
            {...linkProps('/')}
            className="text-amber-crt/60 hover:text-signal"
            style={{ WebkitTapHighlightColor: 'transparent' }}
          >
            ← 回到主页
          </a>
        </footer>
      </div>
    </main>
  )
}

export default App
