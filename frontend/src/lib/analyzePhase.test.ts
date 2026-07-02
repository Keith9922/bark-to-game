import { describe, expect, it } from 'vitest'
import { phaseFromAnalyzeResponse } from './analyzePhase'
import type { AnalyzeResponse } from './api'

function makeResponse(overrides: Partial<AnalyzeResponse>): AnalyzeResponse {
  return {
    audio_hash: 'h',
    duration_ms: 1000,
    sample_count: 16000,
    tokens: [],
    summary: { rhythm: 'SILENT', mood: 'CALM', entropy: 0 },
    detection: 'silent',
    detected_class: '',
    rejected_segment_count: 0,
    degraded: false,
    ...overrides,
  }
}

describe('phaseFromAnalyzeResponse', () => {
  it('routes silent audio to no_sound', () => {
    const phase = phaseFromAnalyzeResponse(makeResponse({ detection: 'silent' }))
    expect(phase).toEqual({ kind: 'no_sound' })
  })

  it('routes non-bark audio to not_a_bark — even when tokens are empty', () => {
    // Regression for the user-visible "录音里没有可识别的音节" bug: backend
    // returns tokens=[] AND detection='not_a_bark', old code matched the
    // silent branch first and showed the wrong (and confusing) message.
    const phase = phaseFromAnalyzeResponse(
      makeResponse({
        detection: 'not_a_bark',
        detected_class: 'Speech',
        rejected_segment_count: 2,
        tokens: [],
      }),
    )
    expect(phase).toEqual({
      kind: 'not_a_bark',
      detectedClass: 'Speech',
      rejectedCount: 2,
    })
  })

  it('returns null for a real bark so the caller proceeds to translate', () => {
    const phase = phaseFromAnalyzeResponse(
      makeResponse({
        detection: 'bark',
        tokens: [
          {
            start_ms: 0,
            end_ms: 200,
            type: 'BARK',
            pitch: 'MID',
            duration: 'SHORT',
            intensity: 'LOUD',
            contour: 'FLAT',
            confidence: 0.5,
            source: 'yamnet',
          },
        ],
      }),
    )
    expect(phase).toBeNull()
  })

  it('falls back to no_sound if detection is bark but tokens are empty', () => {
    // Defensive: should not happen given the strict backend, but if it ever
    // does we'd rather say "no sound" than crash in translate.
    const phase = phaseFromAnalyzeResponse(
      makeResponse({ detection: 'bark', tokens: [] }),
    )
    expect(phase).toEqual({ kind: 'no_sound' })
  })
})
