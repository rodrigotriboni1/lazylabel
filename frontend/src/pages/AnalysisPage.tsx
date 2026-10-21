import { useEffect, useState } from 'react'
import { Activity, AlertCircle, BarChart3, CircleHelp, LoaderCircle, Sparkles } from 'lucide-react'
import { CartesianGrid, Legend, Line, LineChart, Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError, getSources, proposeAnalysis, runAnalysis, type AnalysisPlan, type AnalysisResponse, type SourceInfo } from '@/lib/api'

const operationNames: Record<string, string> = { count_rows: 'Contagem de linhas', sum: 'Soma', average: 'Média', distinct_count: 'Valores distintos', share_of_total: 'Participação no total' }
const readable = (value: unknown) => value === null || value === undefined ? '—' : String(value)

export default function AnalysisPage() {
  const [sources, setSources] = useState<SourceInfo[]>([])
  const [source, setSource] = useState('')
  const [question, setQuestion] = useState('')
  const [metric, setMetric] = useState('count_rows')
  const [metricColumn, setMetricColumn] = useState('')
  const [dimension, setDimension] = useState('')
  const [seriesDimension, setSeriesDimension] = useState('')
  const [timeColumn, setTimeColumn] = useState('')
  const [confirmTotalDenominator, setConfirmTotalDenominator] = useState(false)
  const [chart, setChart] = useState<AnalysisPlan['chart']>('bar')
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [clarifications, setClarifications] = useState<string[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { getSources().then(({ sources: items }) => { setSources(items); setSource(items[0]?.name ?? '') }).catch((e: Error) => setError(e.message)) }, [])
  const selected = sources.find((item) => item.name === source)
  const columns = selected?.columns ?? []
  const isShare = metric === 'share_of_total'

  async function suggest() {
    setBusy(true); setError(null); setClarifications([]); setNotice(null); setResult(null)
    try {
      const proposed = await proposeAnalysis(source, question)
      setMetric(proposed.plan.metric.operation); setMetricColumn(proposed.plan.metric.column ?? '')
      setDimension(proposed.plan.dimensions[0] ?? ''); setChart(proposed.plan.chart)
      setSeriesDimension(proposed.plan.dimensions[1] ?? '')
      setTimeColumn(proposed.plan.time_axis?.column ?? '')
      setConfirmTotalDenominator(proposed.plan.metric.denominator_scope?.length === 0)
      setNotice('Proposta recebida. Confira cada campo e execute para calcular no servidor local.')
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && typeof e.body === 'object' && e.body !== null && 'questions' in e.body && Array.isArray(e.body.questions)) setClarifications(e.body.questions as string[])
      else setError(e instanceof Error ? e.message : 'Falha ao propor análise.')
    } finally { setBusy(false) }
  }

  async function calculate() {
    setBusy(true); setError(null); setResult(null); setClarifications([]); setNotice(null)
    const plan: AnalysisPlan = { version: 1, metric: { operation: metric, column: metric === 'count_rows' ? null : metricColumn || null, denominator_scope: isShare ? [] : null }, dimensions: [dimension, seriesDimension].filter(Boolean), time_axis: timeColumn ? { column: timeColumn, grain: 'month' } : null, filters: [], chart: timeColumn ? 'line' : chart }
    try { setResult(await runAnalysis(source, question || 'Análise definida pelos campos selecionados', plan)) }
    catch (e) { setError(e instanceof Error ? e.message : 'A análise não pôde ser calculada.') }
    finally { setBusy(false) }
  }

  const axis = result?.plan.time_axis?.column ?? result?.plan.dimensions[0] ?? 'Agregado'
  const seriesValues = result && result.plan.dimensions.length > (result.plan.time_axis ? 0 : 1)
    ? [...new Set(result.rows.map((row) => String(row[result.plan.dimensions[result.plan.time_axis ? 0 : 1]] ?? 'Sem valor')))] : []
  const seriesField = result?.plan.dimensions[result.plan.time_axis ? 0 : 1]
  const chartData = result?.rows.reduce<Record<string, unknown>[]>((items, row) => {
    const x = result.plan.time_axis ? row[result.plan.time_axis.column] : result.plan.dimensions.length ? row[result.plan.dimensions[0]] : 'Total'
    let point = items.find((item) => String(item[axis]) === String(x))
    if (!point) { point = { [axis]: x }; items.push(point) }
    const key = seriesField ? String(row[seriesField] ?? 'Sem valor') : '__plot'
    point[key] = Number(row.value); point[`__exact_${key}`] = row.value
    return items
  }, []) ?? []
  const seriesNames = seriesValues.length ? seriesValues : ['__plot']
  const periodValues = result?.plan.time_axis ? result.rows.map((row) => readable(row[result.plan.time_axis!.column])) : []
  const periodLabel = periodValues.length ? (periodValues.length === 1 ? periodValues[0] : `${periodValues[0]} a ${periodValues[periodValues.length - 1]}`) : 'sem eixo temporal'
  const exact = (value: unknown) => readable(value)
  const canRun = Boolean(source) && (!['sum', 'average', 'share_of_total', 'distinct_count'].includes(metric) || Boolean(metricColumn)) && (!isShare || (Boolean(dimension) && confirmTotalDenominator))

  return <div className="space-y-6">
    <div><p className="mb-2 text-sm font-medium text-[#47805f]">FINLABEL / EXPLORAÇÃO</p><h1 className="text-3xl font-semibold tracking-tight">Análise de dados</h1><p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#718077]">Escolha a métrica e os campos. O servidor calcula a resposta; os gráficos apenas representam esses resultados.</p></div>
    <Card className="border-[#e0e8e1] bg-white"><CardHeader><CardTitle className="text-lg">Defina uma análise</CardTitle><CardDescription>Uma pergunta pode sugerir um plano; revise-o antes de calcular.</CardDescription></CardHeader><CardContent className="space-y-5">
      {sources.length === 0 ? <p className="rounded-lg bg-[#f8f5e9] p-4 text-sm text-[#665a32]">Nenhuma fonte local configurada. Adicione uma fonte pelo CLI para começar.</p> : <>
      <label className="grid gap-1.5 text-sm font-medium">Fonte<select className="h-10 rounded-md border border-[#dce5de] bg-white px-3" value={source} onChange={(e) => { setSource(e.target.value); setResult(null) }}>{sources.map((s) => <option key={s.name} value={s.name}>{s.name} · {s.kind}</option>)}</select></label>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="grid gap-1.5 text-sm font-medium">Métrica<select className="h-10 rounded-md border border-[#dce5de] bg-white px-3" value={metric} onChange={(e) => setMetric(e.target.value)}>{Object.entries(operationNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {metric !== 'count_rows' && <label className="grid gap-1.5 text-sm font-medium">Campo da métrica<select className="h-10 rounded-md border border-[#dce5de] bg-white px-3" value={metricColumn} onChange={(e) => setMetricColumn(e.target.value)}><option value="">Selecione um campo</option>{columns.map((c) => <option key={c.name} value={c.name}>{c.name} · {c.mapped_type ?? c.inferred_type}{['sum','average','share_of_total'].includes(metric) && !c.mapped_type ? ' · precisa de mapeamento' : ''}</option>)}</select></label>}
        <label className="grid gap-1.5 text-sm font-medium">Agrupar por (opcional)<select className="h-10 rounded-md border border-[#dce5de] bg-white px-3" value={dimension} onChange={(e) => { setDimension(e.target.value); if (seriesDimension === e.target.value) setSeriesDimension('') }}><option value="">Sem agrupamento</option>{columns.filter((c) => c.name !== seriesDimension).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}</select></label>
        {dimension && <label className="grid gap-1.5 text-sm font-medium">Separar séries por (opcional)<select className="h-10 rounded-md border border-[#dce5de] bg-white px-3" value={seriesDimension} onChange={(e) => setSeriesDimension(e.target.value)}><option value="">Sem séries adicionais</option>{columns.filter((c) => c.name !== dimension).map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}</select></label>}
        <label className="grid gap-1.5 text-sm font-medium">Eixo temporal (opcional)<select className="h-10 rounded-md border border-[#dce5de] bg-white px-3" value={timeColumn} onChange={(e) => setTimeColumn(e.target.value)}><option value="">Sem série temporal</option>{columns.filter((c) => ['date','datetime','timestamp','date-time'].includes((c.mapped_type ?? '').toLowerCase())).map((c) => <option key={c.name} value={c.name}>{c.name} · {c.mapped_type}</option>)}</select><span className="text-xs font-normal text-[#78857b]">Tendência só é oferecida para campo com mapeamento explícito de data.</span></label>
        {!timeColumn && <label className="grid gap-1.5 text-sm font-medium">Gráfico<select className="h-10 rounded-md border border-[#dce5de] bg-white px-3" value={chart} onChange={(e) => setChart(e.target.value as AnalysisPlan['chart'])}><option value="bar">Barras</option>{seriesDimension && <option value="stacked_bar">Barras empilhadas</option>}</select></label>}
        {isShare && <label className="flex items-start gap-2 rounded-md border border-[#dce5de] p-3 text-sm"><input type="checkbox" className="mt-1" checked={confirmTotalDenominator} onChange={(e) => setConfirmTotalDenominator(e.target.checked)} /><span><strong>Confirmo denominador no total geral</strong><span className="mt-1 block text-xs font-normal text-[#78857b]">A API suporta participação com o total calculado sobre todo o conjunto filtrado. O painel só executa depois desta escolha explícita.</span></span></label>}
      </div>
      <label className="grid gap-1.5 text-sm font-medium">Pergunta (opcional)<textarea className="min-h-20 rounded-md border border-[#dce5de] p-3 font-normal" maxLength={2000} placeholder="Ex.: Qual o total por categoria ao longo dos meses?" value={question} onChange={(e) => setQuestion(e.target.value)} /></label>
      {isShare && <div className="rounded-lg border border-[#dce5de] bg-[#f8fbf8] p-3 text-sm"><strong>Como a participação é calculada:</strong> soma do campo métrico em cada grupo ÷ soma no total geral do conjunto filtrado. A API permite escopos de denominador baseados nas dimensões do plano; este formulário oferece a opção explícita de total geral.</div>}
      <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={!source || !question.trim() || busy} onClick={suggest} className="gap-2"><Sparkles size={15} />Sugerir plano</Button><Button disabled={!canRun || busy} onClick={calculate} className="gap-2">{busy ? <LoaderCircle className="animate-spin" size={15} /> : <BarChart3 size={15} />}Calcular análise</Button></div>
      </>}
      {notice && <p role="status" className="rounded-lg bg-[#edf6ef] p-3 text-sm text-[#276a46]">{notice}</p>}
      {clarifications.length > 0 && <div role="alert" className="rounded-lg border border-[#eadbb4] bg-[#fffaf0] p-4"><p className="mb-2 flex items-center gap-2 font-semibold"><CircleHelp size={17} />É necessário esclarecer a solicitação</p><ul className="list-disc space-y-1 pl-5 text-sm">{clarifications.map((item) => <li key={item}>{item}</li>)}</ul><p className="mt-3 text-sm">Escolha explicitamente a métrica, o campo e o denominador nos controles acima e calcule novamente.</p></div>}
      {error && <div role="alert" className="flex items-start gap-2 rounded-lg border border-[#f0d5d1] bg-[#fff7f5] p-3 text-sm text-[#9b3c35]"><AlertCircle size={17} className="mt-0.5 shrink-0"/>{error}</div>}
    </CardContent></Card>

    {result && <>
      <Card className="border-[#e0e8e1] bg-white"><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle className="text-lg">{operationNames[result.plan.metric.operation]}{result.plan.metric.column ? ` · ${result.plan.metric.column}` : ''}</CardTitle><CardDescription>Resultado determinístico · execução {result.run_id.slice(0, 8)}</CardDescription></div><Badge variant="secondary" className="bg-[#edf6ef] text-[#26764c]">{result.total_rows} grupos</Badge></div></CardHeader><CardContent>
        {result.rows.length === 0 ? <p className="rounded-lg bg-[#f5f7f4] p-5 text-center text-sm text-[#718077]">A análise foi concluída sem grupos com valores válidos. Não há gráfico para exibir.</p> : <>
        <div className="h-[300px] w-full" role="img" aria-label={`Gráfico de ${operationNames[result.plan.metric.operation]} por ${axis}`}>
          <ResponsiveContainer width="100%" height="100%">{result.plan.chart === 'line' ? <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="#e8ede9"/><XAxis dataKey={axis} tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 11 }}/><Tooltip formatter={(value, name, item) => [exact(item.payload[`__exact_${String(name)}`] ?? value), operationNames[result.plan.metric.operation]]}/><Legend/>{seriesNames.map((name, i) => <Line key={name} type="monotone" dataKey={name} name={name === '__plot' ? 'Valor' : name} stroke={['#238456','#5885c5','#c17a3d','#8b67a8'][i % 4]} strokeWidth={2.5} dot={{ r: 3 }}/>)}</LineChart> : <BarChart data={chartData} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="#e8ede9"/><XAxis dataKey={axis} tick={{ fontSize: 11 }}/><YAxis tick={{ fontSize: 11 }}/><Tooltip formatter={(value, name, item) => [exact(item.payload[`__exact_${String(name)}`] ?? value), operationNames[result.plan.metric.operation]]}/><Legend/>{seriesNames.map((name, i) => <Bar key={name} dataKey={name} name={name === '__plot' ? 'Valor' : name} stackId={result.plan.chart === 'stacked_bar' ? 'total' : undefined} fill={['#238456','#5885c5','#c17a3d','#8b67a8'][i % 4]} radius={[4,4,0,0]}/>)}</BarChart>}</ResponsiveContainer>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2"><div className="rounded-lg bg-[#f7faf7] p-3 text-sm"><span className="text-xs text-[#718077]">Definição</span><p className="mt-1 font-medium">{operationNames[result.plan.metric.operation]}{result.plan.metric.column ? ` de ${result.plan.metric.column}` : ''}{result.plan.dimensions.length ? ` por ${result.plan.dimensions.join(', ')}` : ''}{result.plan.time_axis ? `, por ${result.plan.time_axis.grain} em ${result.plan.time_axis.column}` : ''}</p><p className="mt-1 text-xs text-[#718077]">Período: {periodLabel} · Filtros: {result.plan.filters.length ? JSON.stringify(result.plan.filters) : 'nenhum'}</p></div><div className="rounded-lg bg-[#f7faf7] p-3 text-sm"><span className="text-xs text-[#718077]">Linhas válidas / denominador</span><p className="mt-1 font-medium">{readable(result.formula_metadata.valid_row_count)} linhas válidas · {result.plan.metric.operation === 'share_of_total' ? (result.plan.metric.denominator_scope?.length ? result.plan.metric.denominator_scope.join(', ') : 'total geral') : 'não aplicável'}</p></div></div>
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
