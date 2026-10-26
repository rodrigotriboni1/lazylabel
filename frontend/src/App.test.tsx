import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import App from './App'
import { FinLabelMemoryClient } from '@/adapters/in-memory/FinLabelMemoryClient'

describe('overview shell', () => {
  afterEach(cleanup)

  it('shows the overview title once', async () => {
    render(<App client={new FinLabelMemoryClient()} />)
    expect(await screen.findAllByRole('heading', { name: 'Seu espaço de trabalho' })).toHaveLength(1)
    expect(await screen.findByText('Servidor local ativo')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Navegação móvel' }).querySelectorAll('a')).toHaveLength(5)
  })
})
