import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import TrainingPage from './TrainingPage'
import { FinLabelClientProvider } from '@/application/FinLabelClientProvider'
import { FinLabelMemoryClient } from '@/adapters/in-memory/FinLabelMemoryClient'

class FlakyClient extends FinLabelMemoryClient {
  private calls = 0
  override getAutonomyOverview = () => ++this.calls === 1 ? Promise.reject(new Error('Painel local indisponível')) : new FinLabelMemoryClient().getAutonomyOverview()
}

describe('TrainingPage refresh', () => {
  afterEach(cleanup)

  it('clears a shown error and reloads the overview on Atualizar', async () => {
    render(<FinLabelClientProvider client={new FlakyClient()}><TrainingPage /></FinLabelClientProvider>)
    expect(await screen.findByRole('alert')).toHaveTextContent('Painel local indisponível')
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(await screen.findByText('Ainda não há ciclos ou decisões registrados.')).toBeInTheDocument()
  })
})
