import { act, render, screen, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import EventStream from './EventStream'
import type { JobEvent } from '../lib/api'

let dispatch: ((event: JobEvent) => void) | null = null
let closed = false

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    openJobStream: vi.fn((_jobId: string, handlers: { onEvent: (e: JobEvent) => void }) => {
      dispatch = handlers.onEvent
      closed = false
      return () => {
        closed = true
        dispatch = null
      }
    }),
  }
})

afterEach(() => {
  cleanup()
  dispatch = null
  closed = false
})

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
})

function send(event: JobEvent) {
  expect(dispatch).not.toBeNull()
  act(() => {
    dispatch!(event)
  })
}

describe('EventStream', () => {
  it('shows the empty-state hint before any event arrives', () => {
    render(<EventStream jobId="j1" />)
    expect(screen.getByText(/等待 Claude 的第一条响应/)).toBeInTheDocument()
  })

  it('renders a write event with the basename of the file path', () => {
    render(<EventStream jobId="j2" />)
    send({ type: 'write', ts: 0, data: { file_path: '/tmp/games/abc/game.html' } })
    expect(screen.getByText(/✍️ 写入 game\.html/)).toBeInTheDocument()
  })

  it('renders a rate_limit (rejected) event with countdown detail', () => {
    render(<EventStream jobId="j3" />)
    const nowS = Math.floor(Date.now() / 1000)
    send({
      type: 'rate_limit',
      ts: nowS,
      data: { status: 'rejected', resets_at: nowS + 125 },
    })
    expect(screen.getByText(/Claude Max 配额已满/)).toBeInTheDocument()
    // 1-2 s drift between resets_at calculation and render is fine; just
    // assert we're in the right minute range.
    expect(screen.getByText(/约 2 分 \d{1,2} 秒 后重置/)).toBeInTheDocument()
  })

  it('skips heartbeat frames so the visible list stays clean', () => {
    render(<EventStream jobId="j4" />)
    send({ type: 'heartbeat', ts: 0, data: { elapsed_s: 5 } })
    expect(screen.getByText(/等待 Claude 的第一条响应/)).toBeInTheDocument()
  })

  it('renders a message event with the assistant preview', () => {
    render(<EventStream jobId="j5" />)
    send({
      type: 'message',
      ts: 0,
      data: { kind: 'AssistantMessage', preview: 'I will start with the title screen.' },
    })
    expect(screen.getByText(/Claude:.*title screen/)).toBeInTheDocument()
  })

  it('closes the EventSource when unmounted', () => {
    const { unmount } = render(<EventStream jobId="j6" />)
    expect(closed).toBe(false)
    unmount()
    expect(closed).toBe(true)
  })
})
