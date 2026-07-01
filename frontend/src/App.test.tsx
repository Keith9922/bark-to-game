import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App (v2 — bilingual UX)', () => {
  it('renders the wordmark', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/bark.*to.*game/i)
  })

  it('reports the bilingual idle status', () => {
    render(<App />)
    const status = screen.getByText(/状态：等待录音/)
    expect(status).toBeInTheDocument()
    expect(status).toHaveTextContent(/READY/)
  })

  it('shows the Chinese record button', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: /按住模仿狗叫|开始录音/ })).toBeInTheDocument()
  })

  it('explains the flow in Chinese', () => {
    render(<App />)
    expect(screen.getByText(/对着话筒/)).toBeInTheDocument()
  })

  it('mentions the session switcher tip in footer', () => {
    render(<App />)
    expect(screen.getByText(/右上角「话题」/)).toBeInTheDocument()
  })
})
