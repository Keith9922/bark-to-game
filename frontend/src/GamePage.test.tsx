import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GamePage from './GamePage'

afterEach(cleanup)

describe('GamePage', () => {
  it('renders the game iframe by id', () => {
    render(<GamePage gameId="abc123" onMakeYourOwn={() => {}} />)
    const iframe = screen.getByTitle(/bark-to-game abc123/)
    expect(iframe).toBeInTheDocument()
    expect(iframe.getAttribute('src')).toContain('/api/game/abc123/play')
  })

  it('rejects an invalid (path-traversal-ish) id', () => {
    render(<GamePage gameId="../etc" onMakeYourOwn={() => {}} />)
    expect(screen.getByText(/游戏不存在/)).toBeInTheDocument()
  })

  it('invokes onMakeYourOwn when the CTA is clicked', () => {
    const fn = vi.fn()
    render(<GamePage gameId="g1" onMakeYourOwn={fn} />)
    fireEvent.click(screen.getByText(/做一个你自己的/))
    expect(fn).toHaveBeenCalledOnce()
  })

  it('shows a share affordance', () => {
    render(<GamePage gameId="g1" onMakeYourOwn={() => {}} />)
    expect(screen.getByText(/分享/)).toBeInTheDocument()
  })
})
