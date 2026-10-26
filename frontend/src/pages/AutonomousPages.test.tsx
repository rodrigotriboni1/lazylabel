import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LabelingPage from './LabelingPage'
import TrainingPage from './TrainingPage'
import { getAutonomyOverview, runAutonomousCycle } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  getAutonomyOverview: vi.fn(),
  runAutonomousCycle: vi.fn(),
}))

const overview = {
  sources: [{ name: 'portfolio', kind: 'csv', columns: [{ name: 'balance', inferred_type: 'decimal', mapped_type: null }] }],
  tasks: [{ task_id: 'risk', input_columns: ['balance'], labels: ['low', 'high'], model_ref: 'local/model', policy_configured: false }],
  runs: [], active_models: [], training_cycles: [], model_events: [],
}

describe('autonomous pages', () => {
  afterEach(cleanup)

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getAutonomyOverview).mockResolvedValue(overview)
  })

  it('runs the full local cycle and presents applied and quarantined aggregates', async () => {
    vi.mocked(runAutonomousCycle).mockResolvedValue({
      run_id: '1234567890abcdef1234567890abcdef', task_id: 'risk', source: 'portfolio',
      started_at: '2026-10-25T12:00:00Z', finished_at: '2026-10-25T12:00:01Z',
      labeling: { run_id: 'a'.repeat(32), model_ref: 'local/model', applied_count: 1, quarantined_count: 2,
        outcome_count: 3, reason_counts: { uncalibrated: 2 } },
      training: { state: 'blocked', reason_codes: ['trusted_labels_missing'], candidate_id: null,
        evaluation_id: null, promotion_action: null, active_model_ref: null },
    })
    render(<LabelingPage />)
    expect(await screen.findByText(/Sem política calibrada/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Executar ciclo autônomo/ }))
    expect(await screen.findByText('Ciclo concluído')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(runAutonomousCycle).toHaveBeenCalledWith('portfolio', 'risk', expect.any(String))
    expect(screen.queryByRole('button', { name: 'Aceitar' })).not.toBeInTheDocument()
  })

  it('shows loading before the autonomous workspace is available', async () => {
    let resolveOverview: (value: typeof overview) => void = () => undefined
    vi.mocked(getAutonomyOverview).mockReturnValue(new Promise((resolve) => { resolveOverview = resolve }))
    render(<LabelingPage />)
    expect(screen.getByText('Carregando configuração local…')).toBeInTheDocument()
    resolveOverview({ ...overview, sources: [], tasks: [] })
    expect(await screen.findByText(/Configure uma fonte CSV\/SQLite/)).toBeInTheDocument()
  })

  it('shows API errors without presenting them as an empty workspace', async () => {
    vi.mocked(getAutonomyOverview).mockRejectedValue(new Error('Painel local indisponível'))
    render(<LabelingPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Painel local indisponível')
  })

  it('keeps the seven training stages accessible and describes automatic gates', async () => {
    render(<TrainingPage />)
    const workflow = await screen.findByRole('list', { name: 'Workflow de treinamento autônomo' })
    await waitFor(() => expect(workflow.querySelectorAll('li')).toHaveLength(7))
    expect(screen.getByText('Promover / rejeitar')).toBeInTheDocument()
    expect(screen.getByText(/holdout congelado e todos os gates passam/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ativar|Rejeitar candidato/ })).not.toBeInTheDocument()
  })

  it('reports training overview errors and retains the workflow diagram', async () => {
    vi.mocked(getAutonomyOverview).mockRejectedValue(new Error('Histórico local indisponível'))
    render(<TrainingPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Histórico local indisponível')
    expect(screen.getByRole('list', { name: 'Workflow de treinamento autônomo' })).toBeInTheDocument()
  })
})
