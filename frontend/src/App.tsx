import { useEffect, useRef, useState } from 'react'
import ConceptCard from './components/ConceptCard'
import EventStream from './components/EventStream'
import GameFrame, { type PlayableGame } from './components/GameFrame'
import HistoryPanel from './components/HistoryPanel'
import ProgressBar from './components/ProgressBar'
import Recorder from './components/Recorder'
import SessionSwitcher from './components/SessionSwitcher'
import TokenList from './components/TokenList'
import {
  cancelJob,
  pollJobUntilDone,
  postAnalyze,
  postGenerate,
  postTranslate,
  type AnalyzeResponse,
  type JobView,
  type TranslateResponse,
} from './lib/api'
import { useCurrentSessionId } from './lib/useSession'

type Phase =
  | { kind: 'idle' }
  | { kind: 'analyzing'; startedAt: number; elapsedS: number }
  | { kind: 'no_sound' }
  | { kind: 'translating'; tokens: AnalyzeResponse; startedAt: number; elapsedS: number }
  | {
      kind: 'generating'
      tokens: AnalyzeResponse
      concept: TranslateResponse
      jobId: string | null
      jobStatus: 'pending' | 'running'
      elapsedS: number
    }
  | {
      kind: 'playable'
      tokens: AnalyzeResponse
      concept: TranslateResponse
      game: PlayableGame
    }
  | {
      kind: 'error'
      message: string
      tokens?: AnalyzeResponse
      concept?: TranslateResponse
    }

const STATUS: Record<string, { cn: string; en: string }> = {
  idle: { cn: '等待录音', en: 'READY' },
  analyzing: { cn: '正在分析声音', en: 'ANALYZING' },
  no_sound: { cn: '没听到声音', en: 'NO SOUND' },
  translating: { cn: '正在构思游戏', en: 'TRANSLATING' },
  generating: { cn: '正在生成游戏', en: 'BUILDING' },
  playable: { cn: '游戏就绪', en: 'READY TO PLAY' },
  error: { cn: '出错了', en: 'ERROR' },
}

function statusLine(phase: Phase): string {
  const v = STATUS[phase.kind]
  return `状态：${v.cn} · ${v.en}`
}

function statusDotClass(phase: Phase): string {
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

function tokensFromPhase(phase: Phase): AnalyzeResponse | undefined {
  switch (phase.kind) {
    case 'translating':
    case 'generating':
    case 'playable':
    case 'error':
      return phase.tokens
    default:
      return undefined
  }
}

function conceptFromPhase(phase: Phase): TranslateResponse | undefined {
  switch (phase.kind) {
    case 'generating':
    case 'playable':
    case 'error':
      return phase.concept
    default:
      return undefined
  }
}

function App() {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [sessionId] = useCurrentSessionId()
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  const generationCancelledRef = useRef(false)

  // Tick the client-side elapsed counter for analyze + translate phases.
  const tickStartedAt =
    phase.kind === 'analyzing' || phase.kind === 'translating' ? phase.startedAt : null
  useEffect(() => {
    if (tickStartedAt === null) return
    const id = window.setInterval(() => {
      setPhase((curr) => {
        if (curr.kind !== 'analyzing' && curr.kind !== 'translating') return curr
        return { ...curr, elapsedS: (performance.now() - tickStartedAt) / 1000 }
      })
    }, 500)
    return () => window.clearInterval(id)
  }, [tickStartedAt])

  const reset = () => setPhase({ kind: 'idle' })

  const handleRecorded = async (blob: Blob) => {
    generationCancelledRef.current = false
    setPhase({ kind: 'analyzing', startedAt: performance.now(), elapsedS: 0 })

    let tokens: AnalyzeResponse
    try {
      tokens = await postAnalyze(blob)
    } catch (err) {
      setPhase({
        kind: 'error',
        message: `分析失败：${err instanceof Error ? err.message : String(err)}`,
      })
      return
    }

    if (tokens.tokens.length === 0) {
      setPhase({ kind: 'no_sound' })
      return
    }

    setPhase({ kind: 'translating', tokens, startedAt: performance.now(), elapsedS: 0 })
    let concept: TranslateResponse
    try {
      concept = await postTranslate(tokens, sessionId)
    } catch (err) {
      setPhase({
        kind: 'error',
        message: `游戏概念生成失败：${err instanceof Error ? err.message : String(err)}`,
        tokens,
      })
      return
    }

    setPhase({
      kind: 'generating',
      tokens,
      concept,
      jobId: null,
      elapsedS: 0,
      jobStatus: 'pending',
    })

    try {
      const accepted = await postGenerate(tokens, concept, sessionId)
      if (generationCancelledRef.current) {
        await cancelJob(accepted.job_id).catch(() => undefined)
        reset()
        return
      }
      setPhase({
        kind: 'generating',
        tokens,
        concept,
        jobId: accepted.job_id,
        elapsedS: 0,
        jobStatus: accepted.status === 'running' ? 'running' : 'pending',
      })

      const onProgress = (job: JobView) => {
        setPhase((current) =>
          current.kind === 'generating' && current.jobId === job.job_id
            ? {
                ...current,
                elapsedS: job.elapsed_s,
                jobStatus: job.status === 'running' ? 'running' : 'pending',
              }
            : current,
        )
      }

      const final = await pollJobUntilDone(accepted.job_id, {
        intervalMs: 5000,
        onProgress,
      })

      if (final.status === 'done' && final.game_id && final.play_url) {
        setPhase({
          kind: 'playable',
          tokens,
          concept,
          game: {
            game_id: final.game_id,
            summary: final.summary ?? '',
            play_url: final.play_url,
          },
        })
        setHistoryRefreshKey((k) => k + 1)
      } else if (final.status === 'cancelled') {
        reset()
      } else {
        setPhase({
          kind: 'error',
          message: `游戏生成失败：${final.error ?? '未知错误'}`,
          tokens,
          concept,
        })
      }
    } catch (err) {
      setPhase({
        kind: 'error',
        message: `游戏生成失败：${err instanceof Error ? err.message : String(err)}`,
        tokens,
        concept,
      })
    }
  }

  const handleCancelGeneration = async () => {
    if (phase.kind !== 'generating') return
    generationCancelledRef.current = true
    if (phase.jobId) {
      try {
        await cancelJob(phase.jobId)
      } catch {
        /* the poll loop will surface the failure */
      }
    }
  }

  const tokens = tokensFromPhase(phase)
  const concept = conceptFromPhase(phase)
  const recorderDisabled =
    phase.kind === 'analyzing' || phase.kind === 'translating' || phase.kind === 'generating'

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
            <SessionSwitcher disabled={recorderDisabled} onSessionChange={reset} />
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
              写出可玩的 HTML5 游戏。每一步都会在下方依次出现。
            </p>
          </div>
        </header>

        <div className="flex justify-center py-4">
          <Recorder
            disabled={recorderDisabled}
            onRecorded={handleRecorded}
            onCancel={() => reset()}
            onError={(message) => setPhase({ kind: 'error', message })}
          />
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
              <li>系统没拿到麦克风权限</li>
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

        {tokens && <TokenList result={tokens} />}

        {phase.kind === 'translating' && (
          <ProgressBar
            label="正在构思游戏 · TRANSLATING"
            caption="Claude 在抽取一组风格卡（艺术 × 机制 × 情绪），并产出 5 个候选概念，挑最有差异的那个。通常 30 秒–2 分钟。"
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
              onCancel={handleCancelGeneration}
            />
            {phase.jobId && <EventStream jobId={phase.jobId} />}
          </div>
        )}

        {phase.kind === 'playable' && <GameFrame game={phase.game} onRestart={reset} />}

        <HistoryPanel sessionId={sessionId} refreshKey={historyRefreshKey} />

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

export default App
