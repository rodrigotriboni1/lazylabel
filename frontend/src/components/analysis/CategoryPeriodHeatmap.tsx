import type { AnalysisResponse } from '@/lib/api'

const format = (value: unknown) => value === null || value === undefined ? 'ausente' : String(value)
const fieldSort = (a: unknown, b: unknown) => String(a).localeCompare(String(b), 'pt-BR', { numeric: true })
const periodSort = (a: unknown, b: unknown) => {
  const left = Date.parse(String(a)); const right = Date.parse(String(b))
  return Number.isFinite(left) && Number.isFinite(right) ? left - right : fieldSort(a, b)
}
const MAX_CELLS = 240

export function CategoryPeriodHeatmap({ result }: { result: AnalysisResponse }) {
  const period = result.plan.time_axis?.column
  const categoryFields = result.plan.dimensions.filter((field) => field !== period)
  if (!period || categoryFields.length !== 1) return null
  const category = categoryFields[0]
  const periods = [...new Set(result.rows.map((row) => row[period]).filter((value) => value !== null && value !== undefined))].sort(periodSort)
  const categories = [...new Set(result.rows.map((row) => row[category]).filter((value) => value !== null && value !== undefined))].sort(fieldSort)
  if (!periods.length || !categories.length) return <p className="rounded-lg bg-[#f7faf7] p-4 text-sm text-[#718077]">Não há categorias e períodos válidos para a matriz.</p>
  const cells = new Map<string, unknown>()
  for (const row of result.rows) cells.set(JSON.stringify([row[category], row[period]]), row.value)
  const visiblePeriods = periods.slice(0, Math.max(1, Math.floor(MAX_CELLS / categories.length)))
  const visibleCategories = categories.slice(0, MAX_CELLS)
  const numericValues = [...cells.values()].map((value) => typeof value === 'number' || (typeof value === 'string' && value.trim() !== '') ? Number(value) : Number.NaN).filter(Number.isFinite)
  const min = Math.min(...numericValues); const max = Math.max(...numericValues)
  const share = result.plan.metric.operation === 'share_of_total'
  const shown = (value: unknown) => {
    const parsed = typeof value === 'number' || (typeof value === 'string' && value.trim() !== '') ? Number(value) : Number.NaN
    return Number.isFinite(parsed) ? `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(share ? parsed * 100 : parsed)}${share ? '%' : ''}` : '—'
  }
  const clipped = periods.length > visiblePeriods.length || categories.length > visibleCategories.length

  return <section aria-labelledby="heatmap-title" className="rounded-xl border border-[#e5ebe6] bg-white p-4 sm:p-5">
    <div className="mb-4"><h2 id="heatmap-title" className="text-base font-semibold text-[#1d2a22]">Categoria por período</h2><p className="mt-1 text-xs text-[#718077]">Intensidade representa {result.plan.metric.operation}{result.plan.metric.column ? ` · ${result.plan.metric.column}` : ''}. Os valores exatos também aparecem na tabela.</p></div>
    <p className="mb-3 flex items-center gap-2 text-[11px] text-[#718077]" aria-label="Legenda de intensidade: verde mais claro indica métrica menor e verde mais escuro indica métrica maior"><span>Menor</span><span aria-hidden="true" className="inline-flex gap-1"><i className="size-3 rounded-sm bg-[#dcebe1]"/><i className="size-3 rounded-sm bg-[#a9cbb5]"/><i className="size-3 rounded-sm bg-[#70a984]"/></span><span>Maior · compare os valores exatos</span></p>
    <div className="overflow-x-auto">
      <table aria-label="Matriz categoria por período" className="w-full min-w-max border-separate border-spacing-1 text-left text-xs">
        <thead><tr><th scope="col" className="px-2 py-2 text-[#718077]">{category} / {period}</th>{visiblePeriods.map((value) => <th key={String(value)} scope="col" className="px-2 py-2 text-[#526057]">{format(value)}</th>)}</tr></thead>
        <tbody>{visibleCategories.map((categoryValue) => <tr key={String(categoryValue)}><th scope="row" className="max-w-40 truncate px-2 py-2 font-medium text-[#526057]" title={String(categoryValue)}>{format(categoryValue)}</th>{visiblePeriods.map((periodValue) => {
          const value = cells.get(JSON.stringify([categoryValue, periodValue]))
          const present = cells.has(JSON.stringify([categoryValue, periodValue])) && value !== null && value !== undefined
          const parsed = typeof value === 'number' || (typeof value === 'string' && value.trim() !== '') ? Number(value) : Number.NaN
          const ratio = Number.isFinite(parsed) && max !== min ? (parsed - min) / (max - min) : 0.5
          const alpha = present ? 0.08 + ratio * 0.32 : 0
          const text = present ? shown(value) : '—'
          return <td key={String(periodValue)} aria-label={`${format(categoryValue)}, ${format(periodValue)}: ${present ? text : 'ausente'}`} title={`${category} ${format(categoryValue)} · ${period} ${format(periodValue)} · ${result.plan.metric.operation}: ${present ? text : 'ausente'}`} className="min-w-20 rounded-md px-2 py-3 text-center tabular-nums" style={{ backgroundColor: present ? `rgba(35, 132, 86, ${alpha})` : '#f4f6f4' }}>{text}</td>
        })}</tr>)}</tbody>
      </table>
    </div>
    {clipped && <p className="mt-3 text-xs text-[#718077]">Matriz limitada a {MAX_CELLS} células nesta visualização. Consulte a tabela completa abaixo.</p>}
    <p className="sr-only">Valores numéricos e períodos estão identificados em cada célula; células sem resultado são marcadas como ausentes.</p>
  </section>
}
