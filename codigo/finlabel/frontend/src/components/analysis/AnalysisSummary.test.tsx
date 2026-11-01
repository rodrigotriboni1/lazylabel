import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AnalysisSummary } from './AnalysisSummary'
import type { AnalysisResponse } from '@/application/ports/FinLabelClient'

const result: AnalysisResponse = {
  run_id: 'run-12345678', total_rows: 4, valid_row_count: 10,
  rows: [
    { month: '2026-01', category: 'A', value: 0.2 },
    { month: '2026-01', category: 'B', value: 0.8 },
    { month: '2026-02', category: 'A', value: 0.35 },
    { month: '2026-02', category: 'B', value: 0.65 },
  ], highlights: [],
  plan: { version: 1, metric: { operation: 'share_of_total', column: 'amount' }, dimensions: ['category'], time_axis: { column: 'month', grain: 'month' }, filters: [], chart: 'line' },
  formula_metadata: { valid_row_count: 10 }, invalid_value_counts: { amount: 2 },
}

describe('AnalysisSummary', () => {
  it('summarizes valid rows, period range, leader, percentage point change, and data issues', () => {
    render(<AnalysisSummary result={result} />)
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('2026-01 – 2026-02')).toBeInTheDocument()
    expect(screen.getByText('B · 65%')).toBeInTheDocument()
    expect(screen.getByText('-15 p.p.')).toBeInTheDocument()
    expect(screen.getByText('Valores excluídos')).toBeInTheDocument()
    expect(screen.getByText('amount: 2')).toBeInTheDocument()
  })

  it('does not invent relative change when the first metric value is zero', () => {
    render(<AnalysisSummary result={{ ...result, rows: [
      { month: '2026-01', category: 'A', value: 0 },
      { month: '2026-02', category: 'A', value: 4 },
    ], plan: { ...result.plan, metric: { operation: 'sum', column: 'amount' } } }} />)
    expect(screen.getByText('+4')).toBeInTheDocument()
    expect(screen.getByText('B · 65%')).toBeInTheDocument()
  })
})
