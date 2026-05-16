import { useCallback, useRef, useState } from 'react'

const MIN_RECORD_MS = 250

type Phase = 'idle' | 'recording'

interface Props {
  disabled?: boolean
  onRecorded: (audio: Blob, durationMs: number) => void
  onError: (message: string) => void
  onRecordingStart?: () => void
}

export default function RecordButton({ disabled, onRecorded, onError, onRecordingStart }: Props) {
  const [phase, setPhase] = useState<Phase>('idle')
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const startedAtRef = useRef<number>(0)

  const start = useCallback(async () => {
    if (phase !== 'idle' || disabled) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.start()
      recorderRef.current = recorder
      startedAtRef.current = performance.now()
      setPhase('recording')
      onRecordingStart?.()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'microphone access failed')
    }
  }, [disabled, onError, onRecordingStart, phase])

  const stop = useCallback(() => {
    const recorder = recorderRef.current
    if (!recorder || phase !== 'recording') return

    const elapsed = performance.now() - startedAtRef.current
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
      recorder.stream.getTracks().forEach((track) => track.stop())
      recorderRef.current = null
      setPhase('idle')

      if (elapsed < MIN_RECORD_MS) {
        onError(`too short (${Math.round(elapsed)} ms) — hold for at least ${MIN_RECORD_MS} ms`)
        return
      }
      onRecorded(blob, Math.round(elapsed))
    }
    recorder.stop()
  }, [onError, onRecorded, phase])

  const recording = phase === 'recording'

  return (
    <button
      type="button"
      aria-label={recording ? 'release to analyse' : 'hold to bark'}
      aria-pressed={recording}
      disabled={disabled}
      onPointerDown={start}
      onPointerUp={stop}
      onPointerLeave={recording ? stop : undefined}
      onPointerCancel={stop}
      className={[
        'relative size-44 sm:size-52 rounded-full border-2 select-none touch-none',
        'flex items-center justify-center text-center',
        'font-display tracking-tight transition-colors duration-150',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-crt focus-visible:ring-offset-4 focus-visible:ring-offset-black',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        recording
          ? 'border-signal bg-signal/10 text-signal'
          : 'border-amber-crt text-amber-crt hover:bg-amber-crt/10 active:bg-amber-crt/20',
      ].join(' ')}
    >
      {recording ? (
        <span className="flex flex-col items-center gap-3">
          <span className="size-3 rounded-full bg-signal motion-safe:animate-pulse" aria-hidden />
          <span className="text-2xl">RELEASE</span>
        </span>
      ) : (
        <span className="text-2xl leading-tight">
          HOLD
          <br />
          TO BARK
        </span>
      )}
    </button>
  )
}
