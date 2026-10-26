import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { getHealth, getSources } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  getHealth: vi.fn(),
  getSources: vi.fn(),
}))

describe('overview shell', () => {
  beforeEach(() => {
    vi.mocked(getHealth).mockResolvedValue({ status: 'ok', project: 'synthetic', sources: 1 })
    vi.mocked(getSources).mockResolvedValue({ sources: [] })
  })

  it('shows the overview title once', async () => {
    render(<App />)
    expect(await screen.findAllByRole('heading', { name: 'Seu espaço de trabalho' })).toHaveLength(1)
    expect(screen.getByRole('navigation', { name: 'Navegação móvel' }).querySelectorAll('a')).toHaveLength(5)
  })
})
