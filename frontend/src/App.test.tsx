import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App (Phase 4 — sessions)', () => {
  it('renders the wordmark', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/bark.*to.*game/i)
  })

  it('reports idle status', () => {
    render(<App />)
    expect(screen.getByText(/SYS_STATUS · READY/)).toBeInTheDocument()
  })

  it('shows the hold-to-bark button', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: /hold to bark/i })).toBeInTheDocument()
  })

  it('mentions Claude Code in the intro paragraph', () => {
    render(<App />)
    expect(screen.getByText(/Claude Code writes a playable/i)).toBeInTheDocument()
  })

  it('shows the session switcher with a default label', () => {
    render(<App />)
    const button = screen.getByRole('button', { name: /session:/i })
    expect(button).toBeInTheDocument()
    expect(button).toHaveTextContent(/default/i)
  })
})
