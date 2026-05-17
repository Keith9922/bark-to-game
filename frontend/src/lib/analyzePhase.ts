import type { AnalyzeResponse } from './api'

export type EarlyPhase =
  | { kind: 'no_sound' }
  | { kind: 'not_a_bark'; detectedClass: string; rejectedCount: number }

/**
 * Decide which short-circuit phase (if any) to enter after `/analyze` returns.
 *
 * Order matters: `not_a_bark` must be checked **before** the silent /
 * empty-tokens branch, because the backend currently returns `tokens=[]` for
 * both. The old code matched silent first and incorrectly told the user
 * "we didn't hear anything" when YAMNet had actually rejected their speech.
 *
 * Returns null when the caller should continue to translate + generate.
 */
export function phaseFromAnalyzeResponse(tokens: AnalyzeResponse): EarlyPhase | null {
  if (tokens.detection === 'not_a_bark') {
    return {
      kind: 'not_a_bark',
      detectedClass: tokens.detected_class,
      rejectedCount: tokens.rejected_segment_count,
    }
  }
  if (tokens.detection === 'silent' || tokens.tokens.length === 0) {
    return { kind: 'no_sound' }
  }
  return null
}
