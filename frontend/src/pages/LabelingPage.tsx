import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRight, CircleAlert, Database, Play, RefreshCw, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { AutonomyOverview, AutonomousRunResult } from '@/application/ports/FinLabelClient'
import { useFinLabelClient } from '@/application/FinLabelClientContext'

export default function LabelingPage() {
  const client = useFinLabelClient()
  const [overview, setOverview] = useState<AutonomyOverview | null>(null)
  const [source, setSource] = useState('')
  const [task, setTask] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AutonomousRunResult | null>(null)
  const idempotencyKey = useRef(crypto.randomUUID())

  const refresh = useCallback(async () => {
    try {
      const next = await client.getAutonomyOverview()
      setError(null)
      setOverview(next)
      setSource((current) => next.sources.some((item) => item.name === current) ? current : next.sources[0]?.name ?? '')
      setTask((current) => next.tasks.some((item) => item.task_id === current) ? current : next.tasks[0]?.task_id ?? '')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o estado local.') }
    finally { setLoading(false) }
  }, [client])
  useEffect(() => { void refresh() }, [refresh])

  const selectedTask = overview?.tasks.find((item) => item.task_id === task)
  async function run() {
    if (!source || !task) return
    setBusy(true); setError(null); setResult(null)
    try {
      const completed = await client.runAutonomousCycle(source, task, idempotencyKey.current)
      setResult(completed)
      idempotencyKey.current = crypto.randomUUID()
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'A execução local falhou.') }
    finally { setBusy(false) }
  }

  return <div className="space-y-7">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="mb-2 text-sm font-medium text-[#47805f]">ROTULAGEM / CICLO AUTÔNOMO</p><h1 className="text-3xl font-semibold tracking-tight">Rotular e aprender</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#718077]">O modelo sugere rótulos localmente. Regras aplicam casos válidos, enviam incertezas à quarentena e só iniciam treino com exemplos confiáveis.</p></div>
      <Button variant="outline" className="gap-2" onClick={() => void refresh()}><RefreshCw size={15}/>Atualizar</Button>
    </div>
    {error && <div role="alert" className="rounded-lg border border-[#f0d5d1] bg-white p-4 text-sm text-[#963f35]">{error}</div>}
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(280px,.9fr)]">
      <Card className="border-[#e1e8e2] shadow-sm"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Database size={17} className="text-[#32845b]"/>Configurar ciclo local</CardTitle><CardDescription>A origem permanece somente leitura; resultados agregados ficam no workspace.</CardDescription></CardHeader>
        <CardContent className="space-y-5">
          <label className="block text-sm font-medium">Fonte de dados<select aria-label="Fonte de dados" className="mt-2 w-full rounded-md border border-[#dce5de] bg-white px-3 py-2.5 text-sm" value={source} onChange={(event) => { setSource(event.target.value); idempotencyKey.current = crypto.randomUUID() }}><option value="">Selecione uma fonte</option>{overview?.sources.map((item) => <option key={item.name} value={item.name}>{item.name} · {item.kind}</option>)}</select></label>
          <label className="block text-sm font-medium">Tarefa de rotulagem<select aria-label="Tarefa de rotulagem" className="mt-2 w-full rounded-md border border-[#dce5de] bg-white px-3 py-2.5 text-sm" value={task} onChange={(event) => { setTask(event.target.value); idempotencyKey.current = crypto.randomUUID() }}><option value="">Selecione uma tarefa</option>{overview?.tasks.map((item) => <option key={item.task_id} value={item.task_id}>{item.task_id}</option>)}</select></label>
          {selectedTask ? <div className="space-y-3 rounded-lg bg-[#f7faf7] p-4"><div><p className="text-xs font-medium uppercase tracking-wide text-[#77837a]">Colunas que o modelo pode usar</p><div className="mt-2 flex flex-wrap gap-2">{selectedTask.input_columns.map((field) => <Badge key={field} variant="outline" className="bg-white">{field}</Badge>)}</div></div><div><p className="text-xs font-medium uppercase tracking-wide text-[#77837a]">Rótulos permitidos</p><div className="mt-2 flex flex-wrap gap-2">{selectedTask.labels.map((label) => <Badge key={label} className="bg-[#e7f3e9] text-[#286444] hover:bg-[#e7f3e9]">{label}</Badge>)}</div></div><p className="text-xs text-[#718077]">Modelo local: <span className="font-medium text-[#39483d]">{selectedTask.model_ref}</span></p>
            {!selectedTask.policy_configured && <p className="flex items-start gap-2 rounded-md border border-[#eddcb9] bg-[#fffaf0] p-3 text-xs leading-relaxed text-[#795a22]"><CircleAlert size={15} className="mt-0.5 shrink-0"/>Sem política calibrada, todos os casos ficam em quarentena e o treino não será promovido.</p>}</div> : loading ? <p role="status" className="rounded-lg border border-dashed p-4 text-sm text-[#718077]">Carregando configuração local…</p> : error ? null : <p className="rounded-lg border border-dashed p-4 text-sm text-[#718077]">Configure uma fonte CSV/SQLite e uma tarefa pelo CLI para iniciar.</p>}
          <Button disabled={busy || loading || !source || !selectedTask} onClick={() => void run()} className="gap-2 bg-[#176c48] hover:bg-[#11583a]">{busy ? 'Executando ciclo local…' : 'Executar ciclo autônomo'}{busy ? <RefreshCw size={15} className="animate-spin"/> : <Play size={15}/>}</Button>
        </CardContent></Card>
      <Card className="border-[#e1e8e2] shadow-sm"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><ShieldCheck size={17} className="text-[#32845b]"/>Política de execução</CardTitle><CardDescription>A biblioteca mantém cada etapa verificável e local.</CardDescription></CardHeader><CardContent><ol className="space-y-4">{[['01','Observar','Inspecionar esquema e qualidade com regras determinísticas.'],['02','Rotular','Usar apenas colunas selecionadas e validar saídas estruturadas.'],['03','Conter incerteza','Quarentenar automaticamente conflitos, inválidos e casos sem confiança calibrada.'],['04','Aprender com segurança','Treinar em lote só com dados confiáveis; promoção depende de holdout e gates.']].map(([number,title,body]) => <li className="flex gap-3" key={number}><span className="grid size-8 shrink-0 place-items-center rounded-full bg-[#eaf5ed] text-xs font-semibold text-[#176c48]">{number}</span><div><p className="text-sm font-medium">{title}</p><p className="mt-1 text-xs leading-relaxed text-[#718077]">{body}</p></div></li>)}</ol><a className="mt-6 flex items-center gap-2 border-t border-[#edf1ed] pt-4 text-xs font-medium text-[#176c48]" href="/training">Ver fluxo de treinamento <ArrowRight size={14}/></a></CardContent></Card>
    </div>
    {result && <Card role="status" className="border-[#cde4d3] bg-white"><CardHeader><CardTitle className="text-base">Ciclo concluído</CardTitle><CardDescription>Execução {result.run_id.slice(0, 12)} · {result.source} · tarefa {result.task_id}</CardDescription></CardHeader><CardContent><div className="grid gap-3 sm:grid-cols-3"><Metric label="Casos avaliados" value={result.labeling.outcome_count}/><Metric label="Aplicados" value={result.labeling.applied_count}/><Metric label="Em quarentena" value={result.labeling.quarantined_count}/></div><p className="mt-4 text-sm text-[#526158]">Treinamento: <b>{result.training.state}</b>{result.training.promotion_action ? ` · ${result.training.promotion_action}` : ''}</p>{Object.keys(result.labeling.reason_counts).length > 0 && <p className="mt-2 text-xs text-[#718077]">Motivos: {Object.entries(result.labeling.reason_counts).map(([reason,count]) => `${reason}: ${count}`).join(' · ')}</p>}<a className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-[#176c48]" href="/training">Acompanhar modelo e ciclo <ArrowRight size={14}/></a></CardContent></Card>}
    <section aria-labelledby="history-title"><div className="mb-3 flex items-end justify-between"><div><h2 id="history-title" className="text-lg font-semibold">Histórico local</h2><p className="mt-1 text-sm text-[#718077]">Execuções verificadas e decisões automáticas do modelo.</p></div></div>
      {overview?.runs.length ? <div className="space-y-3">{overview.runs.map((run) => <Card key={run.run_id} className="border-[#e1e8e2] bg-white"><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4"><div><p className="text-sm font-medium">{run.source} · {run.task_id}</p><p className="mt-1 text-xs text-[#718077]">{new Date(run.finished_at).toLocaleString('pt-BR')} · {run.labels.applied} aplicados · {run.labels.quarantined} quarentena</p></div><Badge variant="outline">Treino {run.training.state}</Badge></CardContent></Card>)}</div> : <p className="rounded-lg border border-dashed border-[#dce5de] bg-white p-5 text-sm text-[#718077]">Nenhum ciclo executado neste projeto.</p>}
    </section>
  </div>
}

function Metric({ label, value }: { label: string; value: number }) { return <div className="rounded-lg bg-[#f7faf7] p-3"><p className="text-xs text-[#718077]">{label}</p><p className="mt-1 text-xl font-semibold">{value.toLocaleString('pt-BR')}</p></div> }
