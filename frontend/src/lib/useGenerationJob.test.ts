import { describe, expect, it } from 'vitest'
import { reducer, type GenPhase } from './useGenerationJob'
import type { AnalyzeResponse, JobEvent, TranslateResponse } from './api'

const tokens = {
  audio_hash: 'h',
  duration_ms: 1,
  sample_count: 1,
  tokens: [],
  summary: { rhythm: 'x', mood: 'y', entropy: 0 },
  detection: 'bark',
  detected_class: '',
  rejected_segment_count: 0,
  degraded: false,
} as AnalyzeResponse

const concept = {
  chosen: {},
  chosen_probability: 1,
  chosen_score: 1,
  candidate_count: 3,
  style_triplet: {},
  visual_recipe: 'pixel_crt',
  game_params: {},
  avoided_summaries: [],
} as unknown as TranslateResponse

const game = { game_id: 'g1', summary: 's', play_url: '/api/game/g1/play' }
const ev = (type: JobEvent['type'], data: Record<string, unknown> = {}): JobEvent => ({
  type,
  ts: 1,
  data,
})

function generating(): GenPhase {
  return reducer(
    { kind: 'translating', tokens, startedAt: 0, elapsedS: 0 },
    { type: 'TRANSLATED', tokens, concept, at: 0 },
  )
}

describe('useGenerationJob reducer', () => {
  it('RECORDED → analyzing', () => {
    const s = reducer({ kind: 'idle' }, { type: 'RECORDED', at: 100 })
    expect(s.kind).toBe('analyzing')
    if (s.kind === 'analyzing') expect(s.startedAt).toBe(100)
  })

  it('ANALYZED → translating carrying tokens', () => {
    const s = reducer({ kind: 'analyzing', startedAt: 0, elapsedS: 0 }, { type: 'ANALYZED', tokens, at: 5 })
    expect(s.kind).toBe('translating')
    if (s.kind === 'translating') expect(s.tokens).toBe(tokens)
  })

  it('REJECTED → the supplied early phase', () => {
    expect(
      reducer({ kind: 'analyzing', startedAt: 0, elapsedS: 0 }, { type: 'REJECTED', phase: { kind: 'no_sound' } }),
    ).toEqual({ kind: 'no_sound' })
    const nb = reducer(
      { kind: 'analyzing', startedAt: 0, elapsedS: 0 },
      { type: 'REJECTED', phase: { kind: 'not_a_bark', detectedClass: 'Speech', rejectedCount: 2 } },
    )
    expect(nb).toMatchObject({ kind: 'not_a_bark', detectedClass: 'Speech', rejectedCount: 2 })
  })

  it('TRANSLATED → generating with null jobId', () => {
    const s = generating()
    expect(s.kind).toBe('generating')
    if (s.kind === 'generating') {
      expect(s.jobId).toBeNull()
      expect(s.concept).toBe(concept)
      expect(s.connection).toBe('live')
      expect(s.events).toEqual([])
    }
  })

  it('GENERATE_ACCEPTED sets jobId + normalizes status', () => {
    const s = reducer(generating(), { type: 'GENERATE_ACCEPTED', jobId: 'j1', jobStatus: 'running' })
    if (s.kind === 'generating') {
      expect(s.jobId).toBe('j1')
      expect(s.jobStatus).toBe('running')
    }
    const p = reducer(generating(), { type: 'GENERATE_ACCEPTED', jobId: 'j2', jobStatus: 'done' })
    if (p.kind === 'generating') expect(p.jobStatus).toBe('pending') // only running|pending
  })

  it('PROGRESS updates generating; ignored otherwise', () => {
    const s = reducer(generating(), { type: 'PROGRESS', elapsedS: 12, jobStatus: 'running' })
    if (s.kind === 'generating') {
      expect(s.elapsedS).toBe(12)
      expect(s.jobStatus).toBe('running')
    }
    expect(reducer({ kind: 'idle' }, { type: 'PROGRESS', elapsedS: 5 })).toEqual({ kind: 'idle' })
  })

  it('SSE_EVENT appends and caps at 8, tracks lastEventAt', () => {
    let s = generating()
    for (let i = 0; i < 12; i++) {
      s = reducer(s, { type: 'SSE_EVENT', event: ev('message', { preview: `p${i}` }), at: i })
    }
    if (s.kind === 'generating') {
      expect(s.events.length).toBe(8)
      expect(s.lastEventAt).toBe(11)
    }
  })

  it('CONNECTION toggles the reconnecting flag', () => {
    const s = reducer(generating(), { type: 'CONNECTION', state: 'reconnecting' })
    if (s.kind === 'generating') expect(s.connection).toBe('reconnecting')
  })

  it('TICK updates analyzing/translating; leaves generating untouched', () => {
    const a = reducer({ kind: 'analyzing', startedAt: 0, elapsedS: 0 }, { type: 'TICK', elapsedS: 3 })
    if (a.kind === 'analyzing') expect(a.elapsedS).toBe(3)
    const g = generating()
    expect(reducer(g, { type: 'TICK', elapsedS: 9 })).toBe(g) // same reference — no change
  })

  it('DONE → playable with the game', () => {
    const s = reducer({ kind: 'idle' }, { type: 'DONE', game, tokens, concept })
    expect(s.kind).toBe('playable')
    if (s.kind === 'playable') expect(s.game.game_id).toBe('g1')
  })

  it('FAILED → recoverable error', () => {
    const s = reducer({ kind: 'idle' }, { type: 'FAILED', message: 'boom', recoverable: true })
    expect(s).toMatchObject({ kind: 'error', message: 'boom', recoverable: true })
  })

  it('CANCELLED and RESET → idle', () => {
    expect(reducer({ kind: 'analyzing', startedAt: 0, elapsedS: 0 }, { type: 'CANCELLED' })).toEqual({
      kind: 'idle',
    })
    expect(reducer(generating(), { type: 'RESET' })).toEqual({ kind: 'idle' })
  })

  it('REATTACHING → generating with null tokens/concept', () => {
    const s = reducer({ kind: 'idle' }, { type: 'REATTACHING', jobId: 'j9' })
    expect(s.kind).toBe('generating')
    if (s.kind === 'generating') {
      expect(s.jobId).toBe('j9')
      expect(s.tokens).toBeNull()
      expect(s.concept).toBeNull()
    }
  })
})
