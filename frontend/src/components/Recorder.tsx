import { useEffect, useRef, useState } from 'react'
import Waveform from './Waveform'

const MIN_DURATION_MS = 300

// idle → arming (awaiting getUserMedia) → recording → stopping → idle
type RecorderPhase = 'idle' | 'arming' | 'recording' | 'stopping'

interface Props {
  disabled?: boolean
  onRecorded: (blob: Blob) => void
  onCancel?: () => void
  onError: (message: string) => void
}

function micErrorMessage(err: unknown): string {
  const name = err instanceof DOMException ? err.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return '麦克风权限被拒绝。请在浏览器地址栏点开权限、允许录音后重试。 (Microphone permission denied — allow it and retry.)'
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return '没有找到麦克风设备。请插入或启用麦克风后重试。 (No microphone found.)'
  }
  const msg = err instanceof Error ? err.message : String(err)
  return `无法打开麦克风：${msg}`
}

/**
 * Hold-to-bark recorder. Press and hold (pointer or keyboard) to record;
 * release to finish. The held button element stays mounted across the whole
 * gesture so its pointer capture survives — releasing anywhere still stops.
 * Falls back to click-to-toggle when PointerEvent is unavailable.
 */
export default function Recorder({ disabled, onRecorded, onCancel, onError }: Props) {
  const [phase, setPhase] = useState<RecorderPhase>('idle')
  const [durationMs, setDurationMs] = useState(0)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const startedAtRef = useRef(0)
  const pressingRef = useRef(false)
  const cancelRequestedRef = useRef(false)

  useEffect(() => {
    if (phase !== 'recording') return
    const id = window.setInterval(() => {
      setDurationMs(performance.now() - startedAtRef.current)
    }, 100)
    return () => window.clearInterval(id)
  }, [phase])

  const beginCapture = async () => {
    if (phase !== 'idle' || disabled) return
    setPhase('arming')
    let mediaStream: MediaStream
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      pressingRef.current = false
      setPhase('idle')
      onError(micErrorMessage(err))
      return
    }
    // Released before the stream was ready (a quick tap, or let go during the
    // permission prompt) — discard silently, no recording.
    if (!pressingRef.current) {
      mediaStream.getTracks().forEach((t) => t.stop())
      setPhase('idle')
      return
    }
    const recorder = new MediaRecorder(mediaStream)
    chunksRef.current = []
    cancelRequestedRef.current = false
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data)
    }
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
      const elapsed = performance.now() - startedAtRef.current
      mediaStream.getTracks().forEach((t) => t.stop())
      recorderRef.current = null
      setStream(null)
      setPhase('idle')
      setDurationMs(0)
      if (cancelRequestedRef.current) {
        onCancel?.()
        return
      }
      // Data-based empty check — a gesture that produced no audio chunks
      // (some mobile Safari builds on a too-quick tap) must not upload a
      // 0-sample WAV that fails analysis with a confusing error.
      if (chunksRef.current.length === 0 || blob.size === 0) {
        onError('没有录到声音，请对着话筒再试一次。 (No audio captured — try again.)')
        return
      }
      if (elapsed < MIN_DURATION_MS) {
        onError(`录音太短啦（${Math.round(elapsed)} 毫秒），请按住多学一会儿`)
        return
      }
      onRecorded(blob)
    }
    recorder.start()
    recorderRef.current = recorder
    setStream(mediaStream)
    startedAtRef.current = performance.now()
    setPhase('recording')
  }

  const endCapture = (cancelled: boolean) => {
    pressingRef.current = false
    if (phase === 'recording' && recorderRef.current) {
      cancelRequestedRef.current = cancelled
      setPhase('stopping')
      recorderRef.current.stop()
    }
    // If still 'arming', beginCapture() will see pressingRef=false on resolve
    // and discard the not-yet-started stream.
  }

  const recording = phase === 'arming' || phase === 'recording'
  const supportsPointer = typeof window !== 'undefined' && 'PointerEvent' in window

  // ---- Hold-to-bark (pointer + keyboard) --------------------------------
  if (supportsPointer) {
    const onPointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
      if (phase !== 'idle' || disabled) return
      try {
        e.currentTarget.setPointerCapture(e.pointerId)
      } catch {
        /* capture unsupported — release-outside just won't be caught */
      }
      pressingRef.current = true
      void beginCapture()
    }
    const onKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
      if (e.repeat || (e.key !== ' ' && e.key !== 'Enter')) return
      if (phase !== 'idle' || disabled) return
      e.preventDefault()
      pressingRef.current = true
      void beginCapture()
    }
    const release = () => {
      if (recording || pressingRef.current) endCapture(false)
    }

    return (
      <div className="flex flex-col items-center gap-3 w-full max-w-md">
        <button
          type="button"
          disabled={disabled}
          onPointerDown={onPointerDown}
          onPointerUp={release}
          onPointerCancel={() => endCapture(true)}
          onKeyDown={onKeyDown}
          onKeyUp={(e) => {
            if (e.key === ' ' || e.key === 'Enter') release()
          }}
          aria-label={recording ? '松开结束录音' : '按住模仿狗叫'}
          className={[
            'px-10 py-5 sm:px-12 sm:py-6 border-2 font-display text-2xl sm:text-3xl tracking-tight select-none',
            recording
              ? 'border-signal text-signal bg-signal/10 motion-safe:animate-pulse'
              : 'border-amber-crt text-amber-crt hover:bg-amber-crt/10 active:bg-amber-crt/20',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-crt focus-visible:ring-offset-4 focus-visible:ring-offset-black',
            'disabled:opacity-40 disabled:cursor-not-allowed transition-colors duration-150',
          ].join(' ')}
          style={{ touchAction: 'none', WebkitTapHighlightColor: 'transparent' }}
        >
          {recording ? '🔴 松开结束' : '🎙️ 按住模仿狗叫'}
        </button>

        {recording ? (
          <div className="w-full space-y-2">
            <Waveform stream={stream} />
            <div className="text-center font-mono text-amber-crt/80 text-sm">
              录音中 · {(durationMs / 1000).toFixed(1)} 秒 · 松开即结束
            </div>
          </div>
        ) : (
          <span className="text-xs text-amber-crt/50 font-mono">
            按住不放，对着麦克风学狗叫，松手结束 · HOLD &amp; BARK
          </span>
        )}
      </div>
    )
  }

  // ---- Fallback: click-to-toggle (no PointerEvent support) --------------
  if (phase === 'idle') {
    return (
      <div className="flex flex-col items-center gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            pressingRef.current = true
            void beginCapture()
          }}
          aria-label="开始录音"
          className={[
            'px-10 py-5 sm:px-12 sm:py-6 border-2 border-amber-crt text-amber-crt',
            'font-display text-2xl sm:text-3xl tracking-tight',
            'hover:bg-amber-crt/10 active:bg-amber-crt/20',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-crt focus-visible:ring-offset-4 focus-visible:ring-offset-black',
            'disabled:opacity-40 disabled:cursor-not-allowed transition-colors duration-150',
          ].join(' ')}
        >
          🎙️ 开始录音
        </button>
        <span className="text-xs text-amber-crt/50 font-mono">
          START · 点一下开始，对着话筒学狗叫
        </span>
      </div>
    )
  }

  return (
    <div className="w-full max-w-md space-y-4 mx-auto">
      <Waveform stream={stream} />
      <div className="text-center font-mono text-amber-crt/80 text-sm">
        <span className="inline-block size-2 rounded-full bg-signal motion-safe:animate-pulse mr-2 align-middle" />
        录音中 · {(durationMs / 1000).toFixed(1)} 秒
      </div>
      <div className="flex justify-center gap-3 flex-wrap">
        <button
          type="button"
          onClick={() => endCapture(false)}
          className="px-6 py-3 border-2 border-signal text-signal hover:bg-signal/10 font-display text-lg"
        >
          ⏹ 结束录音 · STOP
        </button>
        <button
          type="button"
          onClick={() => endCapture(true)}
          className="px-5 py-3 border border-amber-crt/40 text-amber-crt/70 hover:bg-amber-crt/10 font-mono text-sm"
        >
          ✕ 取消
        </button>
      </div>
    </div>
  )
}
