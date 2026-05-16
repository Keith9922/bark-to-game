/**
 * Backend API client + browser audio → WAV conversion.
 *
 * MediaRecorder default output (WebM/Opus on Chromium, mp4 on Safari) is not
 * universally readable by libsndfile/soundfile on the backend. We decode the
 * blob via WebAudio and re-encode as 16-bit PCM WAV before upload — the
 * backend then resamples to 16 kHz as needed.
 */

const BACKEND_URL = 'http://localhost:8000'

export interface TokenSegment {
  start_ms: number
  end_ms: number
  type: string
  pitch: string
  duration: string
  intensity: string
  contour: string
  confidence: number
  source: 'yamnet' | 'heuristic'
}

export interface SessionSummary {
  rhythm: string
  mood: string
  entropy: number
}

export interface AnalyzeResponse {
  audio_hash: string
  duration_ms: number
  sample_count: number
  tokens: TokenSegment[]
  summary: SessionSummary
}

function writeAscii(view: DataView, offset: number, ascii: string): void {
  for (let i = 0; i < ascii.length; i++) {
    view.setUint8(offset + i, ascii.charCodeAt(i))
  }
}

function mixToMono(audio: AudioBuffer): Float32Array {
  if (audio.numberOfChannels === 1) {
    return audio.getChannelData(0)
  }
  const mixed = new Float32Array(audio.length)
  for (let c = 0; c < audio.numberOfChannels; c++) {
    const data = audio.getChannelData(c)
    for (let i = 0; i < data.length; i++) {
      mixed[i] += data[i] / audio.numberOfChannels
    }
  }
  return mixed
}

function bufferToWavBlob(audio: AudioBuffer): Blob {
  const sampleRate = audio.sampleRate
  const channel = mixToMono(audio)

  const bytesPerSample = 2
  const dataBytes = channel.length * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataBytes)
  const view = new DataView(buffer)

  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataBytes, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true) // PCM chunk size
  view.setUint16(20, 1, true) // PCM format
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * bytesPerSample, true) // byte rate
  view.setUint16(32, bytesPerSample, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  writeAscii(view, 36, 'data')
  view.setUint32(40, dataBytes, true)

  let offset = 44
  for (let i = 0; i < channel.length; i++) {
    const sample = Math.max(-1, Math.min(1, channel[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    offset += 2
  }

  return new Blob([buffer], { type: 'audio/wav' })
}

export async function blobToWav(input: Blob): Promise<Blob> {
  const arrayBuffer = await input.arrayBuffer()
  const ctx = new AudioContext()
  try {
    const decoded = await ctx.decodeAudioData(arrayBuffer)
    return bufferToWavBlob(decoded)
  } finally {
    await ctx.close()
  }
}

export async function postAnalyze(audio: Blob): Promise<AnalyzeResponse> {
  const wav = await blobToWav(audio)
  const form = new FormData()
  form.append('audio', wav, 'recording.wav')

  const response = await fetch(`${BACKEND_URL}/api/audio/analyze`, {
    method: 'POST',
    body: form,
  })

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText)
    throw new Error(`analyze ${response.status}: ${detail}`)
  }

  return response.json() as Promise<AnalyzeResponse>
}

export interface Concept {
  title: string
  tagline: string
  player: string
  core_mechanic: string
  win_condition: string
  fail_condition: string
  visual_summary: string
  audio_summary: string
}

export interface StyleCardRef {
  name: string
  description: string
}

export interface TranslateResponse {
  chosen: Concept
  chosen_probability: number
  chosen_score: number
  candidate_count: number
  style_triplet: { art: StyleCardRef; mechanic: StyleCardRef; mood: StyleCardRef }
  visual_recipe: string
  avoided_summaries: string[]
}

export async function postTranslate(
  analyzeResult: AnalyzeResponse,
  sessionId: string = 'default',
): Promise<TranslateResponse> {
  const response = await fetch(`${BACKEND_URL}/api/concept/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tokens: analyzeResult.tokens,
      summary: analyzeResult.summary,
      audio_hash: analyzeResult.audio_hash,
      session_id: sessionId,
    }),
  })

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText)
    throw new Error(`translate ${response.status}: ${detail}`)
  }

  return response.json() as Promise<TranslateResponse>
}

export type JobStatus = 'pending' | 'running' | 'done' | 'failed'

export interface GenerateAccepted {
  job_id: string
  status: JobStatus
  status_url: string
}

export interface JobView {
  job_id: string
  status: JobStatus
  elapsed_s: number
  game_id?: string | null
  summary?: string | null
  play_url?: string | null
  error?: string | null
}

export async function postGenerate(
  analyzeResult: AnalyzeResponse,
  translation: TranslateResponse,
  sessionId: string = 'default',
): Promise<GenerateAccepted> {
  const response = await fetch(`${BACKEND_URL}/api/game/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      concept: translation.chosen,
      style_triplet: translation.style_triplet,
      visual_recipe: translation.visual_recipe,
      audio_hash: analyzeResult.audio_hash,
      session_id: sessionId,
    }),
  })

  if (response.status !== 202) {
    const detail = await response.text().catch(() => response.statusText)
    throw new Error(`generate ${response.status}: ${detail}`)
  }

  return response.json() as Promise<GenerateAccepted>
}

export async function getJob(jobId: string): Promise<JobView> {
  const response = await fetch(`${BACKEND_URL}/api/game/job/${jobId}`)
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText)
    throw new Error(`job ${response.status}: ${detail}`)
  }
  return response.json() as Promise<JobView>
}

export interface PollOptions {
  intervalMs?: number
  signal?: AbortSignal
  onProgress?: (job: JobView) => void
}

export async function pollJobUntilDone(jobId: string, opts: PollOptions = {}): Promise<JobView> {
  const interval = opts.intervalMs ?? 5000
  while (true) {
    if (opts.signal?.aborted) throw new DOMException('poll aborted', 'AbortError')
    const job = await getJob(jobId)
    opts.onProgress?.(job)
    if (job.status === 'done' || job.status === 'failed') return job
    await new Promise((r) => setTimeout(r, interval))
  }
}

export function playUrlFor(playPath: string): string {
  return `${BACKEND_URL}${playPath}`
}

export interface SessionMeta {
  id: string
  name: string
  created_at: number
}

export async function listSessions(): Promise<SessionMeta[]> {
  const response = await fetch(`${BACKEND_URL}/api/sessions`)
  if (!response.ok) {
    throw new Error(`list sessions ${response.status}`)
  }
  const data = (await response.json()) as { sessions: SessionMeta[] }
  return data.sessions
}

export async function createSession(name?: string): Promise<SessionMeta> {
  const response = await fetch(`${BACKEND_URL}/api/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name ?? null }),
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText)
    throw new Error(`create session ${response.status}: ${detail}`)
  }
  return response.json() as Promise<SessionMeta>
}
