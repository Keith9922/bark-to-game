import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App (Phase 0 placeholder)', () => {
  it('renders the project wordmark', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/bark.*to.*game/i)
  })

  it('reports scaffold status', () => {
    render(<App />)
    expect(screen.getByText(/PHASE_0_SCAFFOLD_OK/)).toBeInTheDocument()
  })

  it('lists the pending phases', () => {
    render(<App />)
    expect(screen.getByText(/phase 1 — audio capture/i)).toBeInTheDocument()
    expect(screen.getByText(/phase 2 — translation layer/i)).toBeInTheDocument()
    expect(screen.getByText(/phase 3 — generation \+ feedback/i)).toBeInTheDocument()
  })
})
