import { useEffect, useMemo, useState } from 'react'
import { Activity, AlertCircle, BarChart3, CircleHelp, LoaderCircle, Sparkles } from 'lucide-react'
import { CartesianGrid, Legend, Line, LineChart, Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError, getAnalysisRun, getSources, proposeAnalysis, runAnalysis, type AnalysisPlan, type AnalysisResponse, type SourceInfo } from '@/lib/api'

const operationNames: Record<string, string> = { count_rows: 'Contagem de linhas', sum: 'Soma', average: 'Média', distinct_count: 'Valores distintos', share_of_total: 'Participação no total' }
const timeGrainNames: Record<string, string> = { day: 'dia', week: 'semana', month: 'mês', quarter: 'trimestre', year: 'ano' }
const readable = (value: unknown) => value === null || value === undefined ? '—' : String(value)

export default function AnalysisPage({ runId }: { runId?: string }) {
  const [sources, setSources] = useState<SourceInfo[]>([])
  const [source, setSource] = useState('')
  const [question, setQuestion] = useState('')
  const [planText, setPlanText] = useState(JSON.stringify({ version: 1, metric: { operation: 'count_rows', column: null, denominator_scope: null }, dimensions: [], time_axis: null, filters: [], chart: 'bar' }, null, 2))
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [clarifications, setClarifications] = useState<string[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSources().then(({ sources: items }) => { setSources(items); setSource(items[0]?.name ?? '') }).catch((e: Error) => setError(e.message))
    if (runId) {
      setBusy(true)
      getAnalysisRun(runId).then(setResult).catch((e: Error) => setError(e.message)).finally(() => setBusy(false))
    }
  }, [runId])
  const currentPlan = useMemo(() => {
    try { return JSON.parse(planText) as AnalysisPlan }
    catch { return null }
  }, [planText])
  const isShareDraft = currentPlan?.metric?.operation === 'share_of_total'

  async function suggest() {
    setBusy(true); setError(null); setClarifications([]); setNotice(null); setResult(null)
    try {
      const proposed = await proposeAnalysis(source, question)
      setPlanText(JSON.stringify(proposed.plan, null, 2))
      setNotice('Proposta recebida com todos os campos. Revise o plano completo e execute para calcular no servidor local.')
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && typeof e.body === 'object' && e.body !== null && 'questions' in e.body && Array.isArray(e.body.questions)) setClarifications(e.body.questions as string[])
      else setError(e instanceof Error ? e.message : 'Falha ao propor análise.')
    } finally { setBusy(false) }
  }

  async function calculate() {
    setBusy(true); setError(null); setResult(null); setClarifications([]); setNotice(null)
    try {
      const submittedPlan = JSON.parse(planText) as AnalysisPlan
      setResult(await runAnalysis(source, question || 'Análise definida pelo plano revisado', submittedPlan))
    } catch (e) { setError(e instanceof Error ? e.message : 'O plano está malformado ou a análise não pôde ser calculada.') }
    finally { setBusy(false) }
  }

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
  const canRun = Boolean(source) && Boolean(planText.trim())

  return <div className="space-y-6">
    <div><p className="mb-2 text-sm font-medium text-[#47805f]">FINLABEL / EXPLORAÇÃO</p><h1 className="text-3xl font-semibold tracking-tight">Análise de dados</h1><p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#718077]">Escolha a métrica e os campos. O servidor calcula a resposta; os gráficos apenas representam esses resultados.</p></div>
    <Card className="border-[#e0e8e1] bg-white"><CardHeader><CardTitle className="text-lg">Defina uma análise</CardTitle><CardDescription>Uma pergunta pode sugerir um plano; revise-o antes de calcular.</CardDescription></CardHeader><CardContent className="space-y-5">
      {sources.length === 0 ? <p className="rounded-lg bg-[#f8f5e9] p-4 text-sm text-[#665a32]">Nenhuma fonte local configurada. Adicione uma fonte pelo CLI para começar.</p> : <>
      <label className="grid gap-1.5 text-sm font-medium">Fonte<select className="h-10 rounded-md border border-[#dce5de] bg-white px-3" value={source} onChange={(e) => { setSource(e.target.value); setResult(null) }}>{sources.map((s) => <option key={s.name} value={s.name}>{s.name} · {s.kind}</option>)}</select></label>
      <label className="grid gap-1.5 text-sm font-medium">Pergunta (opcional)<textarea className="min-h-20 rounded-md border border-[#dce5de] p-3 font-normal" maxLength={2000} placeholder="Ex.: Qual o total por categoria ao longo dos meses?" value={question} onChange={(e) => setQuestion(e.target.value)} /></label>
      <label className="grid gap-1.5 text-sm font-medium">Plano completo (JSON)<textarea aria-label="Plano completo JSON" spellCheck={false} className="min-h-72 rounded-md border border-[#dce5de] bg-[#fbfcfb] p-3 font-mono text-xs font-normal leading-relaxed" value={planText} onChange={(e) => setPlanText(e.target.value)} /></label>
      <p className="text-xs leading-relaxed text-[#78857b]">O plano inteiro é a fonte da solicitação. Edite qualquer campo, incluindo dimensões, filtros, granularidade temporal e escopo do denominador; o painel envia este JSON sem reconstruí-lo. A API valida o plano antes do cálculo.</p>
      {isShareDraft && <div className="rounded-lg border border-[#dce5de] bg-[#f8fbf8] p-3 text-sm"><strong>Participação:</strong> o denominador segue o escopo e o eixo temporal declarados no JSON. Após o cálculo, a descrição abaixo vem dos metadados determinísticos retornados pela API.</div>}
      <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={!source || !question.trim() || busy} onClick={suggest} className="gap-2"><Sparkles size={15} />Sugerir plano</Button><Button disabled={!canRun || busy} onClick={calculate} className="gap-2">{busy ? <LoaderCircle className="animate-spin" size={15} /> : <BarChart3 size={15} />}Calcular análise</Button></div>
      </>}
      {notice && <p role="status" className="rounded-lg bg-[#edf6ef] p-3 text-sm text-[#276a46]">{notice}</p>}
      {clarifications.length > 0 && <div role="alert" className="rounded-lg border border-[#eadbb4] bg-[#fffaf0] p-4"><p className="mb-2 flex items-center gap-2 font-semibold"><CircleHelp size={17} />É necessário esclarecer a solicitação</p><ul className="list-disc space-y-1 pl-5 text-sm">{clarifications.map((item) => <li key={item}>{item}</li>)}</ul><p className="mt-3 text-sm">Edite o plano JSON completo para escolher explicitamente os campos e o denominador, então calcule novamente.</p></div>}
      {error && <div role="alert" className="flex items-start gap-2 rounded-lg border border-[#f0d5d1] bg-[#fff7f5] p-3 text-sm text-[#9b3c35]"><AlertCircle size={17} className="mt-0.5 shrink-0"/>{error}</div>}
    </CardContent></Card>

    {result && <>
      <Card className="border-[#e0e8e1] bg-white"><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle className="text-lg">{operationNames[result.plan.metric.operation]}{result.plan.metric.column ? ` · ${result.plan.metric.column}` : ''}</CardTitle><CardDescription>Resultado determinístico · execução {result.run_id.slice(0, 8)}</CardDescription></div><Badge variant="secondary" className="bg-[#edf6ef] text-[#26764c]">{result.total_rows} grupos</Badge></div></CardHeader><CardContent>
        {result.rows.length === 0 ? <p className="rounded-lg bg-[#f5f7f4] p-5 text-center text-sm text-[#718077]">A análise foi concluída sem grupos com valores válidos. Não há gráfico para exibir.</p> : <>
        <div className="h-[300px] w-full" role="img" aria-label={`Gráfico de ${operationNames[result.plan.metric.operation]} por ${axis}`}>
          <ResponsiveContainer width="100%" height="100%">{result.plan.chart === 'line' ? <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="#e8ede9"/><XAxis dataKey={axis} tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 11 }}/><Tooltip formatter={(value, name, item) => { const key = chartSeries.find((series) => series.label === String(name))?.key; return [exact(item.payload[`__exact_${key ?? String(name)}`] ?? value), operationNames[result.plan.metric.operation]] }}/><Legend/>{chartSeries.map(({ key, label }, i) => <Line key={key} type="monotone" dataKey={key} name={label} stroke={['#238456','#5885c5','#c17a3d','#8b67a8'][i % 4]} strokeWidth={2.5} dot={{ r: 3 }}/>)}</LineChart> : <BarChart data={chartData} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="#e8ede9"/><XAxis dataKey={axis} tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 11 }}/><Tooltip formatter={(value, name, item) => { const key = chartSeries.find((series) => series.label === String(name))?.key; return [exact(item.payload[`__exact_${key ?? String(name)}`] ?? value), operationNames[result.plan.metric.operation]] }}/><Legend/>{chartSeries.map(({ key, label }, i) => <Bar key={key} dataKey={key} name={label} stackId={result.plan.chart === 'stacked_bar' ? 'total' : undefined} fill={['#238456','#5885c5','#c17a3d','#8b67a8'][i % 4]} radius={[4,4,0,0]}/>)}</BarChart>}</ResponsiveContainer>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2"><div className="rounded-lg bg-[#f7faf7] p-3 text-sm"><span className="text-xs text-[#718077]">Definição</span><p className="mt-1 font-medium">{operationNames[result.plan.metric.operation]}{result.plan.metric.column ? ` de ${result.plan.metric.column}` : ''}{result.plan.dimensions.length ? ` por ${result.plan.dimensions.join(', ')}` : ''}{result.plan.time_axis ? `, por ${timeGrainNames[result.plan.time_axis.grain] ?? result.plan.time_axis.grain} em ${result.plan.time_axis.column}` : ''}</p><p className="mt-1 text-xs text-[#718077]">Período: {periodLabel} · Filtros: {result.plan.filters.length ? JSON.stringify(result.plan.filters) : 'nenhum'}</p></div><div className="rounded-lg bg-[#f7faf7] p-3 text-sm"><span className="text-xs text-[#718077]">Linhas válidas / denominador</span><p className="mt-1 font-medium">{readable(result.formula_metadata.valid_row_count)} linhas válidas</p><p className="mt-1 text-xs text-[#718077]">{denominatorDescription}</p></div></div>
        {Object.keys(result.invalid_value_counts).length > 0 && <p className="mt-3 text-sm text-[#775d29]">Valores excluídos: {Object.entries(result.invalid_value_counts).map(([field, count]) => `${field}: ${count}`).join(' · ')}</p>}
        {result.highlights.length > 0 && <div className="mt-4 rounded-lg border border-[#e0e8e1] p-4"><p className="mb-2 text-sm font-semibold">Observações referenciadas</p>{result.highlights.map((text, i) => <p key={i} className="mb-1 text-sm text-[#56635a]">{text}</p>)}<p className="mt-2 text-xs text-[#87938a]">Os valores numéricos verificáveis estão na tabela de resultados.</p></div>}
        {result.total_rows > result.rows.length && <p className="mb-2 mt-4 rounded-md bg-[#fffaf0] p-3 text-xs text-[#765d25]">A API retornou {result.rows.length} de {result.total_rows} grupos nesta resposta. O gráfico e a tabela mostram apenas os grupos recebidos.</p>}
        <div className="mt-5 overflow-x-auto rounded-lg border border-[#e5ebe6]"><table className="w-full min-w-[440px] text-left text-sm"><caption className="px-3 py-2 text-left text-xs text-[#718077]">Valores exatos da API determinística · {result.rows.length} grupos mostrados</caption><thead className="bg-[#f7faf7] text-xs text-[#637168]"><tr>{[...Object.keys(result.rows[0]).filter((key) => key !== 'value'), 'Valor exato'].map((key) => <th key={key} className="px-3 py-2 font-medium">{key === 'value' ? 'Valor exato' : key}</th>)}</tr></thead><tbody>{result.rows.map((row, index) => <tr key={index} className="border-t border-[#edf0ed]">{Object.entries(row).filter(([key]) => key !== 'value').map(([key, value]) => <td key={key} className="px-3 py-2">{readable(value)}</td>)}<td className="px-3 py-2 font-mono">{exact(row.value)}</td></tr>)}</tbody></table></div>
        </>}
      </CardContent></Card>
    </>}
    {!result && !busy && !error && sources.length > 0 && <div className="flex items-center gap-2 rounded-lg border border-dashed border-[#d7e1d8] p-4 text-sm text-[#718077]"><Activity size={16}/>Aguardando uma análise. Nenhuma série ou indicador foi inferido.</div>}
  </div>
}
