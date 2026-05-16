import { useEffect, useRef } from 'react'

interface Props {
  stream: MediaStream | null
}

/**
 * Live oscilloscope view of an incoming MediaStream.
 *
 * Pure client-side: a single AnalyserNode taps the recording stream, the
 * canvas draws byte-domain samples every frame. Tracks/contexts are released
 * when the stream prop is cleared, so the parent can fully detach the mic
 * by setting `stream={null}`.
 */
export default function Waveform({ stream }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!stream || !canvasRef.current) return
    const canvas = canvasRef.current
    const draw2d = canvas.getContext('2d')
    if (!draw2d) return

    const audioCtx = new AudioContext()
    const source = audioCtx.createMediaStreamSource(stream)
    const analyser = audioCtx.createAnalyser()
    analyser.fftSize = 1024
    source.connect(analyser)
    const buffer = new Uint8Array(analyser.fftSize)

    const dpr = window.devicePixelRatio || 1
    function resize() {
      const rect = canvas.getBoundingClientRect()
      canvas.width = Math.floor(rect.width * dpr)
      canvas.height = Math.floor(rect.height * dpr)
      draw2d!.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    let rafId = 0
    function render() {
      analyser.getByteTimeDomainData(buffer)
      const rect = canvas.getBoundingClientRect()
      const w = rect.width
      const h = rect.height

      draw2d!.fillStyle = '#000'
      draw2d!.fillRect(0, 0, w, h)

      // Mid-line guide for an idle (no-signal) baseline.
      draw2d!.strokeStyle = 'rgba(255,176,0,0.15)'
      draw2d!.lineWidth = 1
      draw2d!.beginPath()
      draw2d!.moveTo(0, h / 2)
      draw2d!.lineTo(w, h / 2)
      draw2d!.stroke()

      draw2d!.strokeStyle = '#FFB000'
      draw2d!.lineWidth = 2
      draw2d!.beginPath()
      const slice = w / buffer.length
      let x = 0
      for (let i = 0; i < buffer.length; i++) {
        const v = buffer[i] / 128.0 // 1.0 is silence
        const y = (v * h) / 2
        if (i === 0) draw2d!.moveTo(x, y)
        else draw2d!.lineTo(x, y)
        x += slice
      }
      draw2d!.stroke()

      rafId = requestAnimationFrame(render)
    }
    rafId = requestAnimationFrame(render)

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('resize', resize)
      source.disconnect()
      void audioCtx.close()
    }
  }, [stream])

  return (
    <div aria-label="recording waveform" className="w-full border border-amber-crt/30 bg-black">
      <canvas ref={canvasRef} className="block w-full h-24 sm:h-32" />
    </div>
  )
}
