import { useMemo } from 'react'
import { CartesianGrid, Legend, Line, LineChart, Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { AnalysisResponse } from '@/application/ports/LazyLabelClient'
import { AnalysisSummary } from '@/components/analysis/AnalysisSummary'
import { CategoryPeriodHeatmap } from '@/components/analysis/CategoryPeriodHeatmap'

const operationNames: Record<string, string> = { count_rows: 'Contagem de linhas', sum: 'Soma', average: 'Média', distinct_count: 'Valores distintos', share_of_total: 'Participação no total' }
const timeGrainNames: Record<string, string> = { day: 'dia', week: 'semana', month: 'mês', quarter: 'trimestre', year: 'ano' }
const readable = (value: unknown) => value === null || value === undefined ? '—' : String(value)

/** Exact results, chart and table of one analysis run; moved unchanged from AnalysisPage. */
export function AnalysisResult({ result }: { result: AnalysisResponse }) {
  const axis = result?.plan.time_axis?.column ?? result?.plan.dimensions[0] ?? 'Agregado'
  const chartModel = useMemo(() => {
    if (!result) return { data: [] as Record<string, unknown>[], series: [] as { key: string; label: string }[] }
    const xField = result.plan.time_axis?.column ?? result.plan.dimensions[0]
    const seriesFields = result.plan.dimensions.filter((field) => field !== xField)
    const seriesByIdentity = new Map<string, { key: string; label: string }>()
    const points = new Map<string, Record<string, unknown>>()
    for (const row of result.rows) {
      const xValue = xField ? row[xField] : 'Total'
      const xIdentity = JSON.stringify(xValue)
      let point = points.get(xIdentity)
      if (!point) { point = { [axis]: xValue }; points.set(xIdentity, point) }
      const values = seriesFields.map((field) => row[field] ?? null)
      const identity = JSON.stringify(values)
      let series = seriesByIdentity.get(identity)
      if (!series) {
        const key = `series_${seriesByIdentity.size}`
        const baseLabel = seriesFields.length ? seriesFields.map((field, index) => `${field}=${readable(values[index])}`).join(' · ') : 'Valor'
        const duplicateCount = [...seriesByIdentity.values()].filter((entry) => entry.label === baseLabel).length
        const label = duplicateCount ? `${baseLabel} (${duplicateCount + 1})` : baseLabel
        series = { key, label }
        seriesByIdentity.set(identity, series)
      }
      // Each API row identifies one x bucket plus every remaining grouping dimension.
      // The identity map prevents a later dimension from overwriting an earlier value.
      point[series.key] = row.value === null ? null : Number(row.value)
      point[`__exact_${series.key}`] = row.value
    }
    return { data: [...points.values()], series: [...seriesByIdentity.values()] }
  }, [result, axis])
  const chartData = chartModel.data
  const chartSeries = chartModel.series
  const periodValues = result?.plan.time_axis ? result.rows.map((row) => readable(row[result.plan.time_axis!.column])) : []
  const periodLabel = periodValues.length ? (periodValues.length === 1 ? periodValues[0] : `${periodValues[0]} a ${periodValues[periodValues.length - 1]}`) : 'sem eixo temporal'
  const exact = (value: unknown) => readable(value)
  const denominatorDescription = result?.plan.metric.operation !== 'share_of_total' ? 'não aplicável' : (() => {
    const declaredFields = result.formula_metadata.denominator_group_fields
    const fields = Array.isArray(declaredFields) ? declaredFields.map(String) : [...(result.plan.metric.denominator_scope ?? []), ...(result.plan.time_axis ? [result.plan.time_axis.column] : [])]
    if (result.plan.time_axis) {
      const scopedFields = fields.filter((field) => field !== result.plan.time_axis?.column)
      const grain = timeGrainNames[result.plan.time_axis.grain] ?? result.plan.time_axis.grain
      return `por ${grain} (${result.plan.time_axis.column})${scopedFields.length ? `, dentro de cada combinação de ${scopedFields.join(', ')}` : ', somado sobre todos os grupos desse período'}`
    }
    return fields.length ? `por combinação de ${fields.join(', ')}` : 'total geral do conjunto filtrado'
  })()
  return <>
      <div className="space-y-4">
      <AnalysisSummary result={result} />
      <CategoryPeriodHeatmap result={result} />
      </div>
      <Card className="border-border bg-card"><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle className="text-lg">{operationNames[result.plan.metric.operation]}{result.plan.metric.column ? ` · ${result.plan.metric.column}` : ''}</CardTitle><CardDescription>Resultado determinístico · execução {result.run_id.slice(0, 8)}</CardDescription></div><Badge variant="secondary" className="bg-accent text-foreground">{result.total_rows} grupos</Badge></div></CardHeader><CardContent>
        {result.rows.length === 0 ? <p className="rounded-lg bg-muted p-5 text-center text-sm text-muted-foreground">A análise foi concluída sem grupos com valores válidos. Não há gráfico para exibir.</p> : <>
        <div className="h-[300px] w-full" role="img" aria-label={`Gráfico de ${operationNames[result.plan.metric.operation]} por ${axis}`}>
          <ResponsiveContainer width="100%" height="100%">{result.plan.chart === 'line' ? <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="#e8ede9"/><XAxis dataKey={axis} tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 11 }}/><Tooltip formatter={(value, name, item) => { const key = chartSeries.find((series) => series.label === String(name))?.key; return [exact(item.payload[`__exact_${key ?? String(name)}`] ?? value), operationNames[result.plan.metric.operation]] }}/><Legend/>{chartSeries.map(({ key, label }, i) => <Line key={key} type="monotone" dataKey={key} name={label} stroke={['#238456','#5885c5','#c17a3d','#8b67a8'][i % 4]} strokeWidth={2.5} dot={{ r: 3 }}/>)}</LineChart> : <BarChart data={chartData} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="#e8ede9"/><XAxis dataKey={axis} tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 11 }}/><Tooltip formatter={(value, name, item) => { const key = chartSeries.find((series) => series.label === String(name))?.key; return [exact(item.payload[`__exact_${key ?? String(name)}`] ?? value), operationNames[result.plan.metric.operation]] }}/><Legend/>{chartSeries.map(({ key, label }, i) => <Bar key={key} dataKey={key} name={label} stackId={result.plan.chart === 'stacked_bar' ? 'total' : undefined} fill={['#238456','#5885c5','#c17a3d','#8b67a8'][i % 4]} radius={[4,4,0,0]}/>)}</BarChart>}</ResponsiveContainer>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2"><div className="rounded-lg bg-muted p-3 text-sm"><span className="text-xs text-muted-foreground">Definição</span><p className="mt-1 font-medium">{operationNames[result.plan.metric.operation]}{result.plan.metric.column ? ` de ${result.plan.metric.column}` : ''}{result.plan.dimensions.length ? ` por ${result.plan.dimensions.join(', ')}` : ''}{result.plan.time_axis ? `, por ${timeGrainNames[result.plan.time_axis.grain] ?? result.plan.time_axis.grain} em ${result.plan.time_axis.column}` : ''}</p><p className="mt-1 text-xs text-muted-foreground">Período: {periodLabel} · Filtros: {result.plan.filters.length ? JSON.stringify(result.plan.filters) : 'nenhum'}</p></div><div className="rounded-lg bg-muted p-3 text-sm"><span className="text-xs text-muted-foreground">Linhas válidas / denominador</span><p className="mt-1 font-medium">{readable(result.formula_metadata.valid_row_count)} linhas válidas</p><p className="mt-1 text-xs text-muted-foreground">{denominatorDescription}</p></div></div>
        {Object.keys(result.invalid_value_counts).length > 0 && <p className="mt-3 text-sm text-muted-foreground">Valores excluídos: {Object.entries(result.invalid_value_counts).map(([field, count]) => `${field}: ${count}`).join(' · ')}</p>}
        {result.highlights.length > 0 && <div className="mt-4 rounded-lg border border-border p-4"><p className="mb-2 text-sm font-semibold">Observações referenciadas</p>{result.highlights.map((text, i) => <p key={i} className="mb-1 text-sm text-muted-foreground">{text}</p>)}<p className="mt-2 text-xs text-muted-foreground">Os valores numéricos verificáveis estão na tabela de resultados.</p></div>}
        {result.total_rows > result.rows.length && <p className="mb-2 mt-4 rounded-md bg-muted p-3 text-xs text-muted-foreground">A API retornou {result.rows.length} de {result.total_rows} grupos nesta resposta. O gráfico e a tabela mostram apenas os grupos recebidos.</p>}
        <div className="mt-5 overflow-x-auto rounded-lg border border-border"><table className="w-full min-w-[440px] text-left text-sm"><caption className="px-3 py-2 text-left text-xs text-muted-foreground">Valores exatos da API determinística · {result.rows.length} grupos mostrados</caption><thead className="bg-muted text-xs text-muted-foreground"><tr>{[...Object.keys(result.rows[0]).filter((key) => key !== 'value'), 'Valor exato'].map((key) => <th key={key} className="px-3 py-2 font-medium">{key === 'value' ? 'Valor exato' : key}</th>)}</tr></thead><tbody>{result.rows.map((row, index) => <tr key={index} className="border-t border-border">{Object.entries(row).filter(([key]) => key !== 'value').map(([key, value]) => <td key={key} className="px-3 py-2">{readable(value)}</td>)}<td className="px-3 py-2 font-mono">{exact(row.value)}</td></tr>)}</tbody></table></div>
        </>}
      </CardContent></Card>
  </>
}
