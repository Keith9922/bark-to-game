import { render, screen, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import App from './App'

afterEach(() => {
  cleanup()
  window.history.pushState({}, '', '/')
})
beforeEach(() => window.history.pushState({}, '', '/'))

describe('App routing (shell)', () => {
  it('renders the home view at /', () => {
    window.history.pushState({}, '', '/')
    render(<App />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/bark.*to.*game/i)
    expect(screen.getByRole('button', { name: /按住模仿狗叫|开始录音/ })).toBeInTheDocument()
  })

  it('renders the shareable game page at /game/:id', () => {
    window.history.pushState({}, '', '/game/deadbeef01')
    render(<App />)
    expect(screen.getByTitle(/bark-to-game deadbeef01/)).toBeInTheDocument()
    expect(screen.getByText(/做一个你自己的/)).toBeInTheDocument()
  })
})
