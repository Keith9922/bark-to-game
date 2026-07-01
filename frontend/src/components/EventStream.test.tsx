import { render, screen, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import EventStream from './EventStream'
import type { JobEvent } from '../lib/api'

afterEach(cleanup)

const ev = (type: JobEvent['type'], data: Record<string, unknown> = {}, ts = 0): JobEvent => ({
  type,
  ts,
  data,
})

describe('EventStream (presentational)', () => {
  it('shows the empty-state hint when there are no display-worthy events', () => {
    render(<EventStream events={[]} lastEventAt={null} />)
    expect(screen.getByText(/等待 Claude 的第一条响应/)).toBeInTheDocument()
  })

  it('renders a write event with the basename of the file path', () => {
    render(
      <EventStream
        events={[ev('write', { file_path: '/tmp/games/abc/game.html' })]}
        lastEventAt={Date.now()}
      />,
    )
    expect(screen.getByText(/✍️ 写入 game\.html/)).toBeInTheDocument()
  })

  it('renders a rate_limit (rejected) event with countdown detail', () => {
    const nowS = Math.floor(Date.now() / 1000)
    render(
      <EventStream
        events={[ev('rate_limit', { status: 'rejected', resets_at: nowS + 125 }, nowS)]}
        lastEventAt={Date.now()}
      />,
    )
    expect(screen.getByText(/Claude Max 配额已满/)).toBeInTheDocument()
    expect(screen.getByText(/约 2 分 \d{1,2} 秒 后重置/)).toBeInTheDocument()
  })

  it('skips heartbeat frames so the visible list stays clean', () => {
    render(<EventStream events={[ev('heartbeat', { elapsed_s: 5 })]} lastEventAt={Date.now()} />)
    expect(screen.getByText(/等待 Claude 的第一条响应/)).toBeInTheDocument()
  })

  it('renders a message event with the assistant preview', () => {
    render(
      <EventStream
        events={[ev('message', { preview: 'I will start with the title screen.' })]}
        lastEventAt={Date.now()}
      />,
    )
    expect(screen.getByText(/Claude:.*title screen/)).toBeInTheDocument()
  })

  it('surfaces the reconnecting state', () => {
    render(<EventStream events={[]} lastEventAt={Date.now()} connection="reconnecting" />)
    expect(screen.getByText(/连接中断，重连中/)).toBeInTheDocument()
  })
})
