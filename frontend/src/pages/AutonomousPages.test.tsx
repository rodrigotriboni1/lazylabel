import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LabelingPage from './LabelingPage'
import TrainingPage from './TrainingPage'
import { FinLabelClientProvider } from '@/application/FinLabelClientProvider'
import { ApiError, type AutonomyOverview } from '@/application/ports/FinLabelClient'
import { FinLabelMemoryClient } from '@/adapters/in-memory/FinLabelMemoryClient'

const overview: AutonomyOverview = {
  sources: [{ name: 'portfolio', kind: 'csv', columns: [{ name: 'balance', inferred_type: 'decimal', mapped_type: null }] }],
  tasks: [{ task_id: 'risk', input_columns: ['balance'], labels: ['low', 'high'], model_ref: 'local/model', policy_configured: false }],
  runs: [], active_models: [], training_cycles: [], model_events: [],
}
const show = (page: React.ReactNode, client = new FinLabelMemoryClient()) => render(<FinLabelClientProvider client={client}>{page}</FinLabelClientProvider>)

describe('autonomous pages using the in-memory client', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks() })

  it('runs the full local cycle and presents applied and quarantined aggregates', async () => {
    class RecordingClient extends FinLabelMemoryClient {
      readonly cycleCalls: Parameters<FinLabelMemoryClient['runAutonomousCycle']>[] = []
      constructor(options: ConstructorParameters<typeof FinLabelMemoryClient>[0]) {
        super(options)
        const runInMemory = this.runAutonomousCycle
        this.runAutonomousCycle = (...args) => {
          this.cycleCalls.push(args)
          return runInMemory(...args)
        }
      }
    }
    const key = '00000000-0000-4000-8000-000000000001'
    const nextKey = '00000000-0000-4000-8000-000000000002'
    const uuid = vi.spyOn(crypto, 'randomUUID').mockReturnValue(key)
    const client = new RecordingClient({ responses: { getAutonomyOverview: { ...overview,
      sources: [...overview.sources, { ...overview.sources[0], name: 'ledger' }],
      tasks: [...overview.tasks, { ...overview.tasks[0], task_id: 'sector' }],
    }, runAutonomousCycle: {
      run_id: '1234567890abcdef1234567890abcdef', task_id: 'sector', source: 'ledger',
      started_at: '2026-10-25T12:00:00Z', finished_at: '2026-10-25T12:00:01Z',
      labeling: { run_id: 'a'.repeat(32), model_ref: 'local/model', applied_count: 1, quarantined_count: 2,
        outcome_count: 3, reason_counts: { uncalibrated: 2 } },
      training: { state: 'blocked', reason_codes: ['trusted_labels_missing'], candidate_id: null,
        evaluation_id: null, promotion_action: null, active_model_ref: null },
    } } })
    show(<LabelingPage />, client)
    expect(await screen.findByText(/Sem política calibrada/)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox', { name: 'Fonte de dados' }), { target: { value: 'ledger' } })
    fireEvent.change(screen.getByRole('combobox', { name: 'Tarefa de rotulagem' }), { target: { value: 'sector' } })
    // Unrelated refresh/rerenders may request new UUIDs, but must keep the selected cycle's key.
    uuid.mockReturnValue(nextKey)
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Tarefa de rotulagem' })).toHaveValue('sector'))
    fireEvent.click(screen.getByRole('button', { name: /Executar ciclo autônomo/ }))
    expect(await screen.findByText('Ciclo concluído')).toBeInTheDocument()
    expect(client.cycleCalls).toEqual([['ledger', 'sector', key]])
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('blocked')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aceitar' })).not.toBeInTheDocument()
  })

  it('shows loading before the autonomous workspace is available', async () => {
    let release: (value: AutonomyOverview) => void = () => undefined
    class DelayedClient extends FinLabelMemoryClient {
      override getAutonomyOverview = () => new Promise<AutonomyOverview>((resolve) => { release = resolve })
    }
    const client = new DelayedClient()
    show(<LabelingPage />, client)
    expect(screen.getByText('Carregando configuração local…')).toBeInTheDocument()
    await act(async () => { release(await new FinLabelMemoryClient().getAutonomyOverview()) })
    expect(await screen.findByText(/Configure uma fonte CSV\/SQLite/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Executar ciclo autônomo/ })).toBeDisabled()
  })

  it('shows client errors without presenting them as an empty workspace', async () => {
    show(<LabelingPage />, new FinLabelMemoryClient({ error: new ApiError('Painel local indisponível', 503, {}) }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Painel local indisponível')
    expect(screen.queryByText(/Configure uma fonte CSV\/SQLite/)).not.toBeInTheDocument()
  })

  it('keeps the seven training stages accessible and describes automatic gates in an empty workspace', async () => {
    show(<TrainingPage />)
    const workflow = await screen.findByRole('list', { name: 'Workflow de treinamento autônomo' })
    await waitFor(() => expect(screen.getByText(/Nenhum adapter promovido/)).toBeInTheDocument())
    expect(workflow.querySelectorAll('li')).toHaveLength(7)
    expect(workflow.querySelector('[aria-current="step"]')).toHaveTextContent('Verificar dados')
    expect(screen.getByText('Promover / rejeitar')).toBeInTheDocument()
    expect(screen.getByText(/holdout congelado e todos os gates passam/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ativar|Rejeitar candidato/ })).not.toBeInTheDocument()
  })

  it('displays returned promotion evidence, metrics, and rollback history', async () => {
    show(<TrainingPage />, new FinLabelMemoryClient({ responses: { getAutonomyOverview: { ...overview,
      active_models: [{ task_id: 'risk', model_ref: 'local/promoted', candidate_id: 'candidate-1' }],
      training_cycles: [{ cycle_id: 'cycle-1', task_id: 'risk', state: 'promoted', reason_codes: [], candidate_id: 'candidate-1',
        evaluation_id: 'eval-1', promotion_action: 'promote', active_model_ref: 'local/promoted', created_at: null,
        evaluation: { holdout_count: 12, candidate_metrics: { accuracy: 0.9 }, incumbent_metrics: { accuracy: 0.8 }, same_frozen_holdout: true } }],
      model_events: [{ event_id: 'event-1', task_id: 'risk', action: 'rollback', reason_codes: ['health_degraded'],
        active_model_ref: 'local/promoted', rollback_from: 'local/previous', created_at: '2026-10-25T12:00:00Z' }],
    } } }))
    expect(await screen.findByText('local/promoted')).toBeInTheDocument()
    expect(screen.getByText('90.0%')).toBeInTheDocument()
    expect(screen.getByText('Modelo atual: 80.0%')).toBeInTheDocument()
    expect(screen.getByText('Rollback automático · risk')).toBeInTheDocument()
    expect(screen.getByText('health_degraded')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Workflow de treinamento autônomo' }).querySelector('[aria-current="step"]')).toHaveTextContent('Monitorar / reverter')
  })

  it('reports training overview errors and retains the workflow diagram', async () => {
    show(<TrainingPage />, new FinLabelMemoryClient({ error: new ApiError('Histórico local indisponível', 503, {}) }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Histórico local indisponível')
    expect(screen.getByRole('list', { name: 'Workflow de treinamento autônomo' })).toBeInTheDocument()
  })
})
