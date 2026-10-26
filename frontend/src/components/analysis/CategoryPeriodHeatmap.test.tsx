import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CategoryPeriodHeatmap } from './CategoryPeriodHeatmap'
import type { AnalysisResponse } from '@/lib/api'

const result: AnalysisResponse = {
  run_id: 'run', total_rows: 3, valid_row_count: 3,
  rows: [
    { month: 'Jan', category: 'A', value: 2 },
    { month: 'Feb', category: 'A', value: 3 },
    { month: 'Feb', category: 'B', value: 5 },
  ], highlights: [],
  plan: { version: 1, metric: { operation: 'sum', column: 'amount' }, dimensions: ['category'], time_axis: { column: 'month', grain: 'month' }, filters: [], chart: 'line' },
  formula_metadata: {}, invalid_value_counts: {},
}

describe('CategoryPeriodHeatmap', () => {
  it('renders exact values in an accessible table and represents absent cells as missing', () => {
    render(<CategoryPeriodHeatmap result={result} />)
    expect(screen.getByRole('table', { name: /matriz categoria por período/i })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: /A, Feb: 3/ })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: /B, Jan: ausente/ })).toHaveTextContent('—')
  })

  it('does not render if there is no explicit time axis and category dimension', () => {
    const { container } = render(<CategoryPeriodHeatmap result={{ ...result, plan: { ...result.plan, time_axis: null } }} />)
    expect(container).toBeEmptyDOMElement()
  })
})
