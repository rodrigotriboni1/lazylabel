import type { AnalysisResponse } from '@/application/ports/FinLabelClient'

const display = (value: unknown) => value === null || value === undefined ? '—' : String(value)
const numeric = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) return Number(value)
  return null
}
const number = (value: number) => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value)
const isShare = (result: AnalysisResponse) => result.plan.metric.operation === 'share_of_total'

function categoryField(result: AnalysisResponse) {
  const time = result.plan.time_axis?.column
  const fields = result.plan.dimensions.filter((field) => field !== time)
  return fields.length === 1 ? fields[0] : null
}

function periodOrder(result: AnalysisResponse, field: string) {
  const values = [...new Set(result.rows.map((row) => row[field]).filter((value) => value !== null && value !== undefined))]
  return values.sort((a, b) => {
    const left = String(a); const right = String(b)
    const aTime = Date.parse(left); const bTime = Date.parse(right)
    return Number.isFinite(aTime) && Number.isFinite(bTime) ? aTime - bTime : left.localeCompare(right, 'pt-BR', { numeric: true })
  })
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="min-w-0 rounded-xl border border-[#e5ebe6] bg-white p-4">
    <p className="text-xs font-medium text-[#718077]">{label}</p>
    <p className="mt-2 truncate text-xl font-semibold tracking-tight text-[#1d2a22]" title={value}>{value}</p>
    {detail && <p className="mt-1 truncate text-xs text-[#718077]">{detail}</p>}
  </div>
}

export function AnalysisSummary({ result }: { result: AnalysisResponse }) {
  const time = result.plan.time_axis?.column
  const category = categoryField(result)
  const periods = time ? periodOrder(result, time) : []
  const firstPeriod = periods[0]
  const lastPeriod = periods.at(-1)
  const firstPeriodRows = result.rows.filter((row) => row[time ?? ''] === firstPeriod)
  const lastPeriodRows = result.rows.filter((row) => row[time ?? ''] === lastPeriod)
  const leaders = category && time ? lastPeriodRows
    .map((row) => ({ category: row[category], value: numeric(row.value) }))
    .filter((row): row is { category: unknown; value: number } => row.value !== null)
    .sort((a, b) => b.value - a.value) : []
  const leader = leaders[0]
  const initial = leader ? firstPeriodRows.find((row) => row[category!] === leader.category) : undefined
  const initialValue = initial ? numeric(initial.value) : null
  const change = initialValue !== null && leader ? leader.value - initialValue : null
  const invalidCount = Object.values(result.invalid_value_counts).reduce((sum, count) => sum + count, 0)
  const qualityDetail = Object.entries(result.invalid_value_counts).map(([field, count]) => `${field}: ${count}`).join(' · ')
  const leaderValue = leader ? `${number(isShare(result) ? leader.value * 100 : leader.value)}${isShare(result) ? '%' : ''}` : '—'
  const changeText = change === null ? 'Sem base comparável' : isShare(result)
    ? `${change >= 0 ? '+' : ''}${number(change * 100)} p.p.`
    : `${change >= 0 ? '+' : ''}${number(change)}${initialValue !== null && initialValue !== 0 ? ` · ${number(change / Math.abs(initialValue) * 100)}%` : ''}`

  return <section aria-label="Indicadores da análise" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    <MetricCard label="Registros usados" value={result.valid_row_count === undefined ? '—' : number(result.valid_row_count)} detail="Linhas consideradas pelo cálculo" />
    {time && periods.length > 0 && <MetricCard label="Período" value={periods.length > 1 ? `${display(firstPeriod)} – ${display(lastPeriod)}` : display(firstPeriod)} detail={`${periods.length} ${periods.length === 1 ? 'período' : 'períodos'}`} />}
    {category && time && <MetricCard label="Categoria líder" value={leader ? `${display(leader.category)} · ${leaderValue}` : 'Sem valor válido'} detail={leader ? `Maior valor em ${display(lastPeriod)}` : undefined} />}
    {category && time && <MetricCard label="Variação da líder" value={changeText} detail={leader ? `${display(leader.category)} · primeiro ao último período` : undefined} />}
    {invalidCount > 0 && <MetricCard label="Valores excluídos" value={number(invalidCount)} detail={qualityDetail} />}
  </section>
}
