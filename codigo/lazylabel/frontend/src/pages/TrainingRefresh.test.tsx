import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import TrainingPage from './TrainingPage'
import { LazyLabelClientProvider } from '@/application/LazyLabelClientProvider'
import { LazyLabelMemoryClient } from '@/adapters/in-memory/LazyLabelMemoryClient'

class FlakyClient extends LazyLabelMemoryClient {
  calls = 0
  override getAutonomyOverview = () => ++this.calls === 1 ? Promise.reject(new Error('Painel local indisponível')) : new LazyLabelMemoryClient().getAutonomyOverview()
}

describe('TrainingPage refresh', () => {
  afterEach(cleanup)

  it('clears a shown error and reloads the overview on Atualizar', async () => {
    const client = new FlakyClient()
    render(<LazyLabelClientProvider client={client}><TrainingPage /></LazyLabelClientProvider>)
    expect(await screen.findByRole('alert')).toHaveTextContent('Painel local indisponível')
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    await waitFor(() => expect(client.calls).toBe(2))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(await screen.findByText('Ainda não há ciclos ou decisões registrados.')).toBeInTheDocument()
  })
})
