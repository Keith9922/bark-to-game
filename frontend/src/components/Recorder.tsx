import { useEffect, useRef, useState } from 'react'
import Waveform from './Waveform'

const MIN_DURATION_MS = 300

type RecorderPhase = 'idle' | 'recording' | 'stopping'

interface Props {
  disabled?: boolean
  onRecorded: (blob: Blob, durationMs: number) => void
  onCancel?: () => void
  onError: (message: string) => void
}

export default function Recorder({ disabled, onRecorded, onCancel, onError }: Props) {
  const [phase, setPhase] = useState<RecorderPhase>('idle')
  const [durationMs, setDurationMs] = useState(0)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const startedAtRef = useRef(0)
  const cancelRequestedRef = useRef(false)

  // Tick the visible duration counter while recording.
  useEffect(() => {
    if (phase !== 'recording') return
    const id = window.setInterval(() => {
      setDurationMs(performance.now() - startedAtRef.current)
    }, 100)
    return () => window.clearInterval(id)
  }, [phase])

  const start = async () => {
    if (phase !== 'idle' || disabled) return
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(mediaStream)
      chunksRef.current = []
      cancelRequestedRef.current = false
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        })
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
        if (elapsed < MIN_DURATION_MS) {
          onError(`录音太短啦（${Math.round(elapsed)} 毫秒），请至少录 1 秒钟`)
          return
        }
        onRecorded(blob, Math.round(elapsed))
      }
      recorder.start()
      recorderRef.current = recorder
      setStream(mediaStream)
      startedAtRef.current = performance.now()
      setPhase('recording')
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      onError(`无法打开麦克风：${msg}（浏览器可能需要先授予录音权限）`)
    }
  }

  const stop = (cancelled: boolean) => {
    if (phase !== 'recording' || !recorderRef.current) return
    cancelRequestedRef.current = cancelled
    setPhase('stopping')
    recorderRef.current.stop()
  }

  if (phase === 'idle') {
    return (
      <div className="flex flex-col items-center gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={start}
          aria-label="开始录音"
          className={[
            'px-10 py-5 sm:px-12 sm:py-6 border-2 border-amber-crt text-amber-crt',
            'font-display text-2xl sm:text-3xl tracking-tight',
            'hover:bg-amber-crt/10 active:bg-amber-crt/20',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-crt focus-visible:ring-offset-4 focus-visible:ring-offset-black',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'transition-colors duration-150',
          ].join(' ')}
        >
          🎙️ 开始录音
        </button>
        <span className="text-xs text-amber-crt/50 font-mono">
          START · click and then bark into the mic
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
          onClick={() => stop(false)}
          className="px-6 py-3 border-2 border-signal text-signal hover:bg-signal/10 font-display text-lg"
        >
          ⏹ 结束录音 · STOP
        </button>
        <button
          type="button"
          onClick={() => stop(true)}
          className="px-5 py-3 border border-amber-crt/40 text-amber-crt/70 hover:bg-amber-crt/10 font-mono text-sm"
        >
          ✕ 取消
        </button>
      </div>
    </div>
  )
}
