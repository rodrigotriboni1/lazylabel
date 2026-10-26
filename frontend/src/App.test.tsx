import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { FinLabelMemoryClient } from '@/adapters/in-memory/FinLabelMemoryClient'
import { getSources } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  getSources: vi.fn(),
}))

describe('overview shell', () => {
  beforeEach(() => {
    vi.mocked(getSources).mockResolvedValue({ sources: [] })
  })

  it('shows the overview title once', async () => {
    render(<App client={new FinLabelMemoryClient()} />)
    expect(await screen.findAllByRole('heading', { name: 'Seu espaço de trabalho' })).toHaveLength(1)
    expect(await screen.findByText('Servidor local ativo')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Navegação móvel' }).querySelectorAll('a')).toHaveLength(5)
  })
})
