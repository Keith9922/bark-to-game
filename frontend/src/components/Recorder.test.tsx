import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Recorder from './Recorder'

/* eslint-disable @typescript-eslint/no-explicit-any */

describe('Recorder mic-error disambiguation (fallback click mode)', () => {
  let savedPointer: unknown
  let savedMedia: unknown

  beforeEach(() => {
    // Force the click fallback so the test doesn't depend on pointer capture.
    savedPointer = (window as any).PointerEvent
    delete (window as any).PointerEvent
    savedMedia = (navigator as any).mediaDevices
  })

  afterEach(() => {
    cleanup()
    ;(window as any).PointerEvent = savedPointer
    ;(navigator as any).mediaDevices = savedMedia
    vi.restoreAllMocks()
  })

  it('reports a clear permission-denied message on NotAllowedError', async () => {
    const onError = vi.fn()
    ;(navigator as any).mediaDevices = {
      getUserMedia: vi.fn().mockRejectedValue(new DOMException('denied', 'NotAllowedError')),
    }
    render(<Recorder onRecorded={() => {}} onError={onError} />)
    fireEvent.click(screen.getByRole('button', { name: /开始录音/ }))
    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(onError.mock.calls[0][0]).toMatch(/权限/)
  })

  it('reports a no-device message on NotFoundError', async () => {
    const onError = vi.fn()
    ;(navigator as any).mediaDevices = {
      getUserMedia: vi.fn().mockRejectedValue(new DOMException('none', 'NotFoundError')),
    }
    render(<Recorder onRecorded={() => {}} onError={onError} />)
    fireEvent.click(screen.getByRole('button', { name: /开始录音/ }))
    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(onError.mock.calls[0][0]).toMatch(/没有找到麦克风设备|设备/)
  })
})
