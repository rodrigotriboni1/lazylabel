import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import AskPage from './AskPage'
import { LazyLabelClientProvider } from '@/application/LazyLabelClientProvider'
import { LazyLabelMemoryClient } from '@/adapters/in-memory/LazyLabelMemoryClient'

const source = { name: 'carteira', kind: 'csv', columns: [] }
const plan = { version: 1, metric: { operation: 'count_rows' }, dimensions: ['cat'], filters: [], chart: 'bar' as const }
const result = { run_id: 'f'.repeat(32), rows: [{ cat: 'A', value: '7' }], total_rows: 1, valid_row_count: 7, highlights: [], plan, formula_metadata: {}, invalid_value_counts: {} }
const screenText = [
  '{"op":"add","path":"/root","value":"main"}',
  '{"op":"add","path":"/elements/main","value":{"type":"Card","props":{"title":"Contagem por categoria","description":null,"maxWidth":null,"centered":null,"className":null},"children":["m"]}}',
  '{"op":"add","path":"/elements/m","value":{"type":"Metric","props":{"label":"A","value":"7","hint":null},"children":[]}}',
].join('\n')

const show = (generateUi: unknown) => render(<LazyLabelClientProvider client={new LazyLabelMemoryClient({ responses: {
  getSources: { sources: [source] }, proposeAnalysis: { plan, requires_confirmation: true }, runAnalysis: result, generateUi } as never })}><AskPage /></LazyLabelClientProvider>)

describe('AskPage', () => {
  afterEach(cleanup)

  it('computes exact rows first, then renders the screen the model laid out', async () => {
    show({ text: screenText })
    fireEvent.change(await screen.findByRole('textbox', { name: 'Pergunta' }), { target: { value: 'Quantos por categoria?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gerar tela' }))
    const generated = await screen.findByRole('region', { name: 'Tela gerada pela IA' })
    expect(generated).toHaveTextContent('Contagem por categoria')
    expect(generated).toHaveTextContent('7')
    expect(screen.getByRole('link', { name: /análise ffffffff/ })).toHaveAttribute('href', `/analysis/${'f'.repeat(32)}`)
  })

  it('refuses a screen that uses components outside the display-only catalog', async () => {
    show({ text: '{"op":"add","path":"/root","value":"x"}\n{"op":"add","path":"/elements/x","value":{"type":"Button","props":{"label":"Apagar"},"children":[]}}' })
    fireEvent.change(await screen.findByRole('textbox', { name: 'Pergunta' }), { target: { value: 'Algo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gerar tela' }))
    expect(await screen.findByText(/tela inválida/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apagar' })).not.toBeInTheDocument()
  })
})
