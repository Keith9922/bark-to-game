/**
 * useGenerationJob — the single owner of the record → analyze → translate →
 * generate → poll lifecycle.
 *
 * Why this exists: the pipeline used to live inline in App.tsx as a 100-line
 * fire-and-forget async function with no abort, no session pinning, an
 * unbounded poll loop, and a SECOND independent SSE connection in EventStream.
 * That let a session switch / unmount resurface stale state, let one transient
 * 502 kill a still-running job, and let the SSE say "done" up to 5 s before the
 * page transitioned.
 *
 * Design:
 * - A pure `reducer` models every phase transition (unit-tested).
 * - The hook owns ONE AbortController per run, aborted on unmount and on
 *   session change, so an in-flight chain can never write into a fresh state.
 * - `sessionId` is pinned at run start (captured in the run closure).
 * - Progress has a SINGLE source of truth: a hardened poll loop is the
 *   authoritative finaliser; the SSE stream drives live progress AND triggers
 *   an immediate finalise on its terminal frame (no 5 s lag). Only one of them
 *   transitions (guarded by `settled`).
 * - The poll loop tolerates transient getJob errors (bounded retry) and has an
 *   overall wall-clock ceiling that surfaces a distinct "stuck" state.
 * - The active job id is persisted so a refresh mid-generation can re-attach.
 */

import { useCallback, useEffect, useReducer, useRef } from 'react'
import type { PlayableGame } from '../components/GameFrame'
import { phaseFromAnalyzeResponse, type EarlyPhase } from './analyzePhase'
import {
  cancelJob,
  getJob,
  openJobStream,
  postAnalyze,
  postGenerate,
  postTranslate,
  type AnalyzeResponse,
  type JobEvent,
  type JobStatus,
  type JobView,
  type TranslateResponse,
} from './api'

const POLL_INTERVAL_MS = 4000
const MAX_POLL_ERRORS = 4
const OVERALL_TIMEOUT_MS = 10 * 60 * 1000
const MAX_EVENT_LINES = 8
const ACTIVE_JOB_KEY = 'bark-to-game/active-job'

const STUCK_MESSAGE =
  '生成时间过长，可能卡住了。可以重试，或去作品集看看有没有生成成功。 (Generation is taking too long — retry, or check the works.)'
const CONNECTION_LOST_MESSAGE =
  '与后端的连接反复中断，请重试。 (Lost connection to the backend — please retry.)'

export type GenPhase =
  | { kind: 'idle' }
  | { kind: 'analyzing'; startedAt: number; elapsedS: number }
  | { kind: 'no_sound' }
  | { kind: 'not_a_bark'; detectedClass: string; rejectedCount: number }
  | { kind: 'translating'; tokens: AnalyzeResponse; startedAt: number; elapsedS: number }
  | {
      kind: 'generating'
      tokens: AnalyzeResponse | null
      concept: TranslateResponse | null
      jobId: string | null
      jobStatus: 'pending' | 'running'
      elapsedS: number
      events: JobEvent[]
      lastEventAt: number | null
      connection: 'live' | 'reconnecting'
    }
  | {
      kind: 'playable'
      tokens: AnalyzeResponse | null
      concept: TranslateResponse | null
      game: PlayableGame
    }
  | {
      kind: 'error'
      message: string
      recoverable: boolean
      tokens?: AnalyzeResponse | null
      concept?: TranslateResponse | null
    }

export type GenAction =
  | { type: 'RECORDED'; at: number }
  | { type: 'REJECTED'; phase: EarlyPhase }
  | { type: 'ANALYZED'; tokens: AnalyzeResponse; at: number }
  | { type: 'TRANSLATED'; tokens: AnalyzeResponse; concept: TranslateResponse; at: number }
  | { type: 'REATTACHING'; jobId: string }
  | { type: 'GENERATE_ACCEPTED'; jobId: string; jobStatus: JobStatus }
  | { type: 'TICK'; elapsedS: number }
  | { type: 'PROGRESS'; elapsedS?: number; jobStatus?: JobStatus }
  | { type: 'SSE_EVENT'; event: JobEvent; at: number }
  | { type: 'CONNECTION'; state: 'live' | 'reconnecting' }
  | {
      type: 'DONE'
      game: PlayableGame
      tokens: AnalyzeResponse | null
      concept: TranslateResponse | null
    }
  | {
      type: 'FAILED'
      message: string
      recoverable: boolean
      tokens?: AnalyzeResponse | null
      concept?: TranslateResponse | null
    }
  | { type: 'CANCELLED' }
  | { type: 'RESET' }

function normalizeStatus(status: JobStatus): 'pending' | 'running' {
  return status === 'running' ? 'running' : 'pending'
}

export function reducer(state: GenPhase, action: GenAction): GenPhase {
  switch (action.type) {
    case 'RECORDED':
      return { kind: 'analyzing', startedAt: action.at, elapsedS: 0 }
    case 'REJECTED':
      return action.phase
    case 'ANALYZED':
      return { kind: 'translating', tokens: action.tokens, startedAt: action.at, elapsedS: 0 }
    case 'TRANSLATED':
      return {
        kind: 'generating',
        tokens: action.tokens,
        concept: action.concept,
        jobId: null,
        jobStatus: 'pending',
        elapsedS: 0,
        events: [],
        lastEventAt: null,
        connection: 'live',
      }
    case 'REATTACHING':
      return {
        kind: 'generating',
        tokens: null,
        concept: null,
        jobId: action.jobId,
        jobStatus: 'running',
        elapsedS: 0,
        events: [],
        lastEventAt: null,
        connection: 'live',
      }
    case 'GENERATE_ACCEPTED':
      if (state.kind !== 'generating') return state
      return { ...state, jobId: action.jobId, jobStatus: normalizeStatus(action.jobStatus) }
    case 'TICK':
      if (state.kind !== 'analyzing' && state.kind !== 'translating') return state
      return { ...state, elapsedS: action.elapsedS }
    case 'PROGRESS':
      if (state.kind !== 'generating') return state
      return {
        ...state,
        elapsedS: action.elapsedS ?? state.elapsedS,
        jobStatus: action.jobStatus ? normalizeStatus(action.jobStatus) : state.jobStatus,
        connection: 'live',
      }
    case 'SSE_EVENT': {
      if (state.kind !== 'generating') return state
      const events = [...state.events, action.event].slice(-MAX_EVENT_LINES)
      return { ...state, events, lastEventAt: action.at, connection: 'live' }
    }
    case 'CONNECTION':
      if (state.kind !== 'generating') return state
      return { ...state, connection: action.state }
    case 'DONE':
      return { kind: 'playable', tokens: action.tokens, concept: action.concept, game: action.game }
    case 'FAILED':
      return {
        kind: 'error',
        message: action.message,
        recoverable: action.recoverable,
        tokens: action.tokens,
        concept: action.concept,
      }
    case 'CANCELLED':
    case 'RESET':
      return { kind: 'idle' }
    default:
      return state
  }
}

interface ActiveJob {
  jobId: string
  sessionId: string
}

function persistActiveJob(job: ActiveJob): void {
  try {
    localStorage.setItem(ACTIVE_JOB_KEY, JSON.stringify(job))
  } catch {
    /* localStorage unavailable — reconnect just won't work, no crash */
  }
}

function readActiveJob(): ActiveJob | null {
  try {
    const raw = localStorage.getItem(ACTIVE_JOB_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as ActiveJob
    return parsed.jobId && parsed.sessionId ? parsed : null
  } catch {
    return null
  }
}

function clearActiveJob(): void {
  try {
    localStorage.removeItem(ACTIVE_JOB_KEY)
  } catch {
    /* ignore */
  }
}

function isTerminal(status: JobStatus): boolean {
  return status === 'done' || status === 'failed' || status === 'cancelled'
}

function describeError(stage: 'analyze' | 'translate' | 'generate', err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err)
  if (stage === 'analyze') return `分析失败：${msg}`
  if (stage === 'translate') return `游戏概念生成失败：${msg}`
  return `游戏生成失败：${msg}`
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

const sleep = (ms: number, signal: AbortSignal): Promise<void> =>
  new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException('aborted', 'AbortError'))
    const id = setTimeout(resolve, ms)
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(id)
        reject(new DOMException('aborted', 'AbortError'))
      },
      { once: true },
    )
  })

export interface GenerationJob {
  phase: GenPhase
  start: (blob: Blob) => void
  cancel: () => void
  reset: () => void
  /** Surface an external error (e.g. a mic-permission failure from Recorder). */
  fail: (message: string) => void
}

export function useGenerationJob(sessionId: string): GenerationJob {
  const [phase, dispatch] = useReducer(reducer, { kind: 'idle' })
  const abortRef = useRef<AbortController | null>(null)
  const cancelRequestedRef = useRef(false)
  const jobIdRef = useRef<string | null>(null)

  // Abort any in-flight run on unmount OR when the session changes — a run
  // started under session A must not write state into session B.
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [sessionId])

  // Watch a running job: single SSE + hardened poll, first terminal wins.
  const watchJob = useCallback(
    async (
      jobId: string,
      tokens: AnalyzeResponse | null,
      concept: TranslateResponse | null,
      signal: AbortSignal,
    ): Promise<void> => {
      let settled = false

      const applyTerminal = (job: JobView): void => {
        if (settled) return
        settled = true
        clearActiveJob()
        if (job.status === 'done' && job.game_id && job.play_url) {
          dispatch({
            type: 'DONE',
            game: { game_id: job.game_id, summary: job.summary ?? '', play_url: job.play_url },
            tokens,
            concept,
          })
        } else if (job.status === 'cancelled') {
          dispatch({ type: 'CANCELLED' })
        } else {
          dispatch({
            type: 'FAILED',
            message: `游戏生成失败：${job.error ?? '未知错误'}`,
            recoverable: true,
            tokens,
            concept,
          })
        }
      }

      const finalizeNow = async (): Promise<void> => {
        if (settled || signal.aborted) return
        try {
          const job = await getJob(jobId, signal)
          if (isTerminal(job.status)) applyTerminal(job)
        } catch {
          /* let the poll loop retry — SSE terminal is just an accelerator */
        }
      }

      const closeSse = openJobStream(jobId, {
        onEvent: (event) => {
          if (signal.aborted || settled) return
          dispatch({ type: 'SSE_EVENT', event, at: Date.now() })
          const elapsed = typeof event.data.elapsed_s === 'number' ? event.data.elapsed_s : undefined
          if (elapsed !== undefined) dispatch({ type: 'PROGRESS', elapsedS: elapsed })
          if (isTerminal(event.type as JobStatus)) void finalizeNow()
        },
        onError: () => {
          if (!signal.aborted && !settled) dispatch({ type: 'CONNECTION', state: 'reconnecting' })
        },
      })

      const startedAt = performance.now()
      let consecutiveErrors = 0
      try {
        while (!settled && !signal.aborted) {
          if (performance.now() - startedAt > OVERALL_TIMEOUT_MS) {
            settled = true
            clearActiveJob()
            dispatch({
              type: 'FAILED',
              message: STUCK_MESSAGE,
              recoverable: true,
              tokens,
              concept,
            })
            break
          }
          await sleep(POLL_INTERVAL_MS, signal)
          if (settled || signal.aborted) break
          try {
            const job = await getJob(jobId, signal)
            consecutiveErrors = 0
            dispatch({ type: 'PROGRESS', elapsedS: job.elapsed_s, jobStatus: job.status })
            if (isTerminal(job.status)) applyTerminal(job)
          } catch (err) {
            if (isAbort(err) || signal.aborted) break
            consecutiveErrors += 1
            if (consecutiveErrors >= MAX_POLL_ERRORS) {
              settled = true
              clearActiveJob()
              dispatch({
                type: 'FAILED',
                message: CONNECTION_LOST_MESSAGE,
                recoverable: true,
                tokens,
                concept,
              })
              break
            }
            dispatch({ type: 'CONNECTION', state: 'reconnecting' })
          }
        }
      } finally {
        closeSse()
      }
    },
    [],
  )

  const start = useCallback(
    (blob: Blob) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      cancelRequestedRef.current = false
      jobIdRef.current = null
      const signal = controller.signal
      const sid = sessionId // pin the session for the whole run

      void (async () => {
        dispatch({ type: 'RECORDED', at: performance.now() })
        let tokens: AnalyzeResponse
        try {
          tokens = await postAnalyze(blob, signal)
        } catch (err) {
          if (isAbort(err) || signal.aborted) return
          dispatch({ type: 'FAILED', message: describeError('analyze', err), recoverable: true })
          return
        }
        if (signal.aborted) return

        const early = phaseFromAnalyzeResponse(tokens)
        if (early) {
          dispatch({ type: 'REJECTED', phase: early })
          return
        }

        dispatch({ type: 'ANALYZED', tokens, at: performance.now() })
        let concept: TranslateResponse
        try {
          concept = await postTranslate(tokens, sid, signal)
        } catch (err) {
          if (isAbort(err) || signal.aborted) return
          dispatch({
            type: 'FAILED',
            message: describeError('translate', err),
            recoverable: true,
            tokens,
          })
          return
        }
        if (signal.aborted) return

        dispatch({ type: 'TRANSLATED', tokens, concept, at: performance.now() })
        try {
          const accepted = await postGenerate(tokens, concept, sid, signal)
          if (signal.aborted) return
          if (cancelRequestedRef.current) {
            void cancelJob(accepted.job_id).catch(() => undefined)
            controller.abort()
            dispatch({ type: 'CANCELLED' })
            return
          }
          jobIdRef.current = accepted.job_id
          persistActiveJob({ jobId: accepted.job_id, sessionId: sid })
          dispatch({
            type: 'GENERATE_ACCEPTED',
            jobId: accepted.job_id,
            jobStatus: accepted.status,
          })
          await watchJob(accepted.job_id, tokens, concept, signal)
        } catch (err) {
          if (isAbort(err) || signal.aborted) return
          dispatch({
            type: 'FAILED',
            message: describeError('generate', err),
            recoverable: true,
            tokens,
            concept,
          })
        }
      })()
    },
    [sessionId, watchJob],
  )

  const cancel = useCallback(() => {
    cancelRequestedRef.current = true
    const jobId = jobIdRef.current
    if (jobId) void cancelJob(jobId).catch(() => undefined)
    clearActiveJob()
    abortRef.current?.abort()
    dispatch({ type: 'CANCELLED' })
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    cancelRequestedRef.current = false
    jobIdRef.current = null
    clearActiveJob()
    dispatch({ type: 'RESET' })
  }, [])

  const fail = useCallback((message: string) => {
    abortRef.current?.abort()
    dispatch({ type: 'FAILED', message, recoverable: true })
  }, [])

  // Client-side elapsed ticking for analyze + translate (backend supplies
  // elapsed for the generating phase via poll/SSE).
  const tickStartedAt =
    phase.kind === 'analyzing' || phase.kind === 'translating' ? phase.startedAt : null
  useEffect(() => {
    if (tickStartedAt === null) return
    const id = window.setInterval(() => {
      dispatch({ type: 'TICK', elapsedS: (performance.now() - tickStartedAt) / 1000 })
    }, 500)
    return () => window.clearInterval(id)
  }, [tickStartedAt])

  // Re-attach to an in-flight job left by a refresh / accidental navigation,
  // but only if it belongs to the current session.
  useEffect(() => {
    const active = readActiveJob()
    if (!active || active.sessionId !== sessionId) return
    const controller = new AbortController()
    abortRef.current = controller
    jobIdRef.current = active.jobId
    dispatch({ type: 'REATTACHING', jobId: active.jobId })
    void watchJob(active.jobId, null, null, controller.signal)
    // Intentionally run once on mount for the current session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { phase, start, cancel, reset, fail }
}
