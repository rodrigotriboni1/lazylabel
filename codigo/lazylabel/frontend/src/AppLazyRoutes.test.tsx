import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import App from './App'
import { LazyLabelMemoryClient } from '@/adapters/in-memory/LazyLabelMemoryClient'

describe('lazy routes', () => {
  afterEach(() => {
    window.history.pushState({}, '', '/')
    cleanup()
  })

  it('loads the monitor page on /monitor', async () => {
    window.history.pushState({}, '', '/monitor')
    render(<App client={new LazyLabelMemoryClient()} />)
    expect(await screen.findByRole('heading', { name: 'Monitoramento' })).toBeInTheDocument()
  })
})
