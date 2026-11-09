import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import OverviewPage from './OverviewPage'
import MonitorPage from './MonitorPage'
import AnalysisPage from './AnalysisPage'
import { LazyLabelClientProvider } from '@/application/LazyLabelClientProvider'
import { LazyLabelMemoryClient } from '@/adapters/in-memory/LazyLabelMemoryClient'
import { ApiError, type AnalysisPlan, type AnalysisResponse, type LazyLabelClient, type SourceInfo } from '@/application/ports/LazyLabelClient'

const source: SourceInfo = { name: 'portfolio', kind: 'csv', columns: [{ name: 'amount', inferred_type: 'decimal', mapped_type: null, missing_count: 0, non_missing_count: 10 }] }
const plan: AnalysisPlan = { version: 1, metric: { operation: 'share_of_total', column: 'amount' }, dimensions: ['category'], time_axis: { column: 'month', grain: 'month' }, filters: [], chart: 'line' }
const result: AnalysisResponse = { run_id: 'run-12345678', total_rows: 2, valid_row_count: 10,
  rows: [{ category: 'A', month: '2026-01', value: '0.4' }, { category: 'A', month: '2026-02', value: '0.6' }],
  highlights: ['Resumo retornado pelo servidor'], plan, formula_metadata: { valid_row_count: 10 }, invalid_value_counts: {} }
const show = (page: React.ReactNode, client: LazyLabelClient = new LazyLabelMemoryClient()) => render(<LazyLabelClientProvider client={client}>{page}</LazyLabelClientProvider>)
afterEach(cleanup)

describe('workspace pages using the in-memory client', () => {
  it('shows overview loading then only the source metadata supplied by the client', async () => {
    let release: (value: { sources: typeof source[] }) => void = () => undefined
    class DelayedClient extends LazyLabelMemoryClient {
      override getSources = () => new Promise<{ sources: typeof source[] }>((resolve) => { release = resolve })
    }
    show(<OverviewPage />, new DelayedClient())
    expect(screen.getByText('Carregando fontes…')).toBeInTheDocument()
    await act(async () => { release(await new LazyLabelMemoryClient({ responses: { getSources: { sources: [source] } } }).getSources()) })
    expect(await screen.findByText('portfolio')).toBeInTheDocument()
    expect(screen.getByText('amount · decimal')).toBeInTheDocument()
  })

  it('shows the empty overview and source error separately', async () => {
    const page = show(<OverviewPage />)
    expect(await screen.findByText(/Nenhuma fonte configurada/)).toBeInTheDocument()
    page.unmount()
    show(<OverviewPage />, new LazyLabelMemoryClient({ error: new ApiError('Fonte indisponível', 503, {}) }))
    expect(await screen.findByText('Fonte indisponível')).toBeInTheDocument()
    expect(screen.queryByText(/Nenhuma fonte configurada/)).not.toBeInTheDocument()
  })

  it('renders structural findings and can refresh them using the selected source', async () => {
    show(<MonitorPage />, new LazyLabelMemoryClient({ responses: { getSources: { sources: [source] }, getFindings: { findings: [{
      code: 'missing_column', severity: 'error', column: 'category', expected: 'category', observed: null, message: 'Coluna category ausente',
    }] } } }))
    expect(await screen.findByText('Coluna category ausente')).toBeInTheDocument()
    expect(screen.getByText('1 achados')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    expect(await screen.findByText('Coluna category ausente')).toBeInTheDocument()
  })

  it('shows the empty monitor and errors without fabricating a healthy result', async () => {
    const page = show(<MonitorPage />)
    expect(await screen.findByText(/Nenhuma fonte local configurada para monitorar/)).toBeInTheDocument()
    page.unmount()
    show(<MonitorPage />, new LazyLabelMemoryClient({ error: new ApiError('Esquema indisponível', 409, {}) }))
    expect(await screen.findByText('Esquema indisponível')).toBeInTheDocument()
    expect(screen.queryByText(/Nenhuma divergência estrutural encontrada/)).not.toBeInTheDocument()
  })

  it('proposes a plan, calculates it, and renders returned KPIs, exact values and heatmap', async () => {
    show(<AnalysisPage />, new LazyLabelMemoryClient({ responses: { getSources: { sources: [source] },
      proposeAnalysis: { plan, requires_confirmation: true }, runAnalysis: result } }))
    await screen.findByRole('combobox', { name: 'Fonte' })
    fireEvent.change(screen.getByRole('textbox', { name: 'Pergunta (opcional)' }), { target: { value: 'Participação por mês?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sugerir plano' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Proposta recebida')
    expect(screen.getByRole('textbox', { name: 'Plano completo JSON' })).toHaveValue(JSON.stringify(plan, null, 2))
    expect(screen.queryByRole('region', { name: 'Indicadores da análise' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Calcular análise' }))
    const metrics = await screen.findByRole('region', { name: 'Indicadores da análise' })
    expect(within(metrics).getByText('10')).toBeInTheDocument()
    expect(within(metrics).getByText('A · 60%')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'A, 2026-02: 60%' })).toBeInTheDocument()
    expect(screen.getByText('0.6')).toBeInTheDocument()
    expect(screen.getByText('Resumo retornado pelo servidor')).toBeInTheDocument()
  })

  it('loads an existing analysis run directly and preserves the empty-results state', async () => {
    show(<AnalysisPage runId="saved-run" />, new LazyLabelMemoryClient({ responses: { getAnalysisRun: { ...result, rows: [], total_rows: 0 } } }))
    expect(await screen.findByText(/A análise foi concluída sem grupos com valores válidos/)).toBeInTheDocument()
  })

  it('shows analysis errors supplied by the client', async () => {
    show(<AnalysisPage />, new LazyLabelMemoryClient({ error: new ApiError('Análise indisponível', 503, {}) }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Análise indisponível')
  })
})
