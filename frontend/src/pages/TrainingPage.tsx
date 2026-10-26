import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, AlertTriangle, ArrowRight, Check, CircleHelp, Database, Play, RefreshCw, RotateCcw, ShieldCheck, Split, WandSparkles } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  checkTrainingDataset, evaluateTrainingCandidate, getEvaluationJob, getTrainingJob, getTrainingOverview,
  getTrainingVersions, splitTrainingDataset, submitTraining, transitionTrainingVersion,
  type EvaluationJob, type TrainingEvaluation, type TrainingJob, type TrainingOverview, type TrainingQuality,
  type TrainingVersion,
} from '@/lib/api'

const steps = [
  { id: 'check', title: 'Verificar dados', detail: 'Integridade, proveniência e cobertura' },
  { id: 'split', title: 'Dividir', detail: 'Partições determinísticas' },
  { id: 'train', title: 'Treinar', detail: 'Somente a partição de treino' },
  { id: 'evaluate', title: 'Avaliar', detail: 'Holdout reservado' },
  { id: 'decide', title: 'Decidir', detail: 'Revisar métricas e alertas' },
  { id: 'activate', title: 'Ativar / rejeitar', detail: 'Ação humana explícita' },
  { id: 'rollback', title: 'Rollback', detail: 'Restaurar versão anterior' },
] as const
type StepId = typeof steps[number]['id']

function TrainingWorkflow({ current }: { current: StepId }) {
  return <Card className="border-[#dce8df] bg-white shadow-sm">
    <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><Activity size={17} className="text-[#32845b]"/>Fluxo supervisionado</CardTitle>
      <CardDescription>O estágio destacado reflete o estado conhecido pelo painel.</CardDescription></CardHeader>
    <CardContent>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-7" aria-hidden="true">
        {steps.map((step, index) => <div key={step.id} className="relative min-w-0">
          <div className={`h-full rounded-lg border p-3 ${step.id === current ? 'border-[#248252] bg-[#eaf5ed] ring-2 ring-[#248252]/20' : 'border-[#e6ece7] bg-[#fafcf9]'}`}>
            <div className="flex items-center gap-2"><span className={`grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold ${step.id === current ? 'bg-[#176c48] text-white' : 'bg-white text-[#718077]'}`}>{index + 1}</span>
              <span className={`text-xs font-semibold leading-tight ${step.id === current ? 'text-[#176c48]' : 'text-[#34493a]'}`}>{step.title}</span></div>
            <p className="mt-2 text-[11px] leading-snug text-[#718077]">{step.detail}</p>
            {step.id === current && <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-[#176c48]"><span className="size-1.5 rounded-full bg-[#25845a]"/>Agora</span>}
          </div>
          {index < steps.length - 1 && <ArrowRight aria-hidden="true" size={13} className="absolute -right-2 top-1/2 z-10 hidden -translate-y-1/2 text-[#9aa79e] lg:block"/>}
        </div>)}
      </div>
      <ol className="sr-only" aria-label="Sequência acessível do fluxo de treinamento">
        {steps.map((step) => <li key={step.id} aria-current={step.id === current ? 'step' : undefined}>{step.title}: {step.detail}{step.id === current ? ' (estágio atual)' : ''}</li>)}
      </ol>
      <p className="mt-3 text-xs text-[#718077]">Sequência: verificar qualidade → criar split → treinar apenas em train → avaliar em holdout → decidir → ativar ou rejeitar → rollback se necessário.</p>
    </CardContent>
  </Card>
}

function pct(value: number | null | undefined) { return value == null ? 'Indefinido' : `${(value * 100).toFixed(1)}%` }
function num(value: number | null | undefined) { return value == null ? '—' : value.toLocaleString('pt-BR') }

function MetricTable({ report }: { report: TrainingEvaluation }) {
  const labels = [...new Set(report.per_label.map((item) => item.label))]
  const models = [...new Set(report.per_label.map((item) => item.model))]
  return <div className="space-y-4">
    <div className="grid gap-3 sm:grid-cols-2">{models.map((model) => {
      const overall = report.overall[model] ?? {}
      return <div key={model} className="rounded-lg bg-[#f7faf7] p-3"><p className="text-xs font-semibold uppercase tracking-wide text-[#718077]">{model === 'base' ? 'Modelo base' : 'Candidato'}</p>
        <div className="mt-2 grid grid-cols-3 gap-2 text-sm"><span>Acurácia <b className="block">{pct(overall.accuracy)}</b></span><span>Macro F1 <b className="block">{pct(overall.macro_f1)}</b></span><span>Inválidos <b className="block">{num(overall.invalid_count)}</b></span></div></div>
    })}</div>
    <div className="overflow-x-auto rounded-lg border border-[#e6ece7]"><table className="w-full min-w-[600px] text-left text-xs"><caption className="sr-only">Precisão, recall, F1 e suporte por rótulo no holdout</caption><thead className="bg-[#f7faf7] text-[#718077]"><tr><th className="p-2">Rótulo / modelo</th><th className="p-2">Precisão</th><th className="p-2">Recall</th><th className="p-2">F1</th><th className="p-2">Suporte</th></tr></thead>
      <tbody>{labels.flatMap((label) => models.map((model) => {
        const row = report.per_label.find((item) => item.label === label && item.model === model)
        return <tr key={`${label}-${model}`} className="border-t border-[#edf1ed]"><th className="p-2 font-medium">{label} · {model}</th><td className="p-2">{pct(row?.precision)}</td><td className="p-2">{pct(row?.recall)}</td><td className="p-2">{pct(row?.f1)}</td><td className="p-2">{num(row?.support)}</td></tr>
      }))}</tbody></table></div>
    <details className="rounded-lg border border-[#e6ece7] p-3"><summary className="cursor-pointer text-xs font-medium">Contagens de confusão e erros</summary>
      <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-[11px] text-[#59675d]">{JSON.stringify({ confusion: report.confusion, invalid_or_error_count: report.error_count }, null, 2)}</pre></details>
    {report.warnings.length > 0 && <div className="rounded-lg border border-[#eddcb9] bg-[#fffaf0] p-3 text-xs text-[#795a22]"><b>Avisos da avaliação</b><ul className="mt-2 list-disc space-y-1 pl-5">{report.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
  </div>
}

export default function TrainingPage() {
  const [overview, setOverview] = useState<TrainingOverview | null>(null)
  const [datasetName, setDatasetName] = useState('')
  const [quality, setQuality] = useState<TrainingQuality | null>(null)
  const [bundle, setBundle] = useState<Awaited<ReturnType<typeof splitTrainingDataset>> | null>(null)
  const [strategy, setStrategy] = useState('stratified_random')
  const [holdout, setHoldout] = useState('0.2')
  const [seed, setSeed] = useState('42')
  const [splitColumn, setSplitColumn] = useState('')
  const [exploratoryConfirmed, setExploratoryConfirmed] = useState(false)
  const [trainConfirmed, setTrainConfirmed] = useState(false)
  const [job, setJob] = useState<TrainingJob | null>(null)
  const [jobId, setJobId] = useState('')
  const [evaluationJob, setEvaluationJob] = useState<EvaluationJob | null>(null)
  const [evaluationJobId, setEvaluationJobId] = useState('')
  const [evaluation, setEvaluation] = useState<TrainingEvaluation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [evaluating, setEvaluating] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const data = await getTrainingOverview()
      setOverview(data)
      setDatasetName((current) => data.datasets.some((item) => item.name === current) ? current : data.datasets[0]?.name ?? '')
      const latest = data.jobs[0] ?? null
      setJob(latest)
      setJobId(latest && (latest.state === 'queued' || latest.state === 'running') ? latest.job_id : '')
      const latestEvaluation = data.evaluation_jobs[0] ?? null
      setEvaluationJob(latestEvaluation)
      setEvaluationJobId(latestEvaluation && (latestEvaluation.state === 'queued' || latestEvaluation.state === 'running') ? latestEvaluation.job_id : '')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o ciclo de treinamento.') }
  }, [])
  const refreshVersions = useCallback(async () => {
    const result = await getTrainingVersions()
    setOverview((current) => current ? { ...current, versions: result.versions, active_version: result.active_version,
      active_diagnostic: result.active_diagnostic, registry_diagnostics: result.registry_diagnostics } : current)
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    if (!jobId) return
    let alive = true
    const poll = async () => {
      try {
        const current = await getTrainingJob(jobId)
        if (!alive) return
        setJob(current)
        if (current.state === 'succeeded' || current.state === 'failed') {
          setJobId('')
          if (current.state === 'succeeded') { setNotice(`Candidato ${current.version_id ?? ''} registrado e aguardando avaliação.`); await refreshVersions() }
          else setError(current.error ?? 'O trabalho de treinamento falhou; não foi marcado como concluído.')
        }
      } catch (cause) { if (alive) { setJobId(''); setError(cause instanceof Error ? cause.message : 'Falha ao consultar o trabalho local.') } }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 1500)
    return () => { alive = false; window.clearInterval(timer) }
  }, [jobId, refreshVersions])
  useEffect(() => {
    if (!evaluationJobId) return
    let alive = true
    const poll = async () => {
      try {
        const current = await getEvaluationJob(evaluationJobId)
        if (!alive) return
        setEvaluationJob(current)
        if (current.state === 'succeeded' || current.state === 'failed') {
          setEvaluationJobId('')
          if (current.state === 'succeeded') {
            await refreshVersions()
            const updated = await getTrainingOverview()
            const evaluated = updated.versions.find((version) => version.version_id === current.version_id)?.evaluation
            if (alive && evaluated) { setEvaluation(evaluated); setNotice('Avaliação do holdout concluída e registrada. Revise as métricas antes de decidir.') }
            else if (alive) setError('O job terminou, mas o relatório não apareceu no registro de versões.')
          } else setError(current.error ?? 'A avaliação falhou; o candidato continua sem avaliação registrada.')
        }
      } catch (cause) { if (alive) { setEvaluationJobId(''); setError(cause instanceof Error ? cause.message : 'Falha ao consultar o job de avaliação.') } }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 1200)
    return () => { alive = false; window.clearInterval(timer) }
  }, [evaluationJobId, refreshVersions])

  const selectedDataset = overview?.datasets.find((item) => item.name === datasetName)
  const selectedTask = overview?.tasks.find((item) => item.task_id === selectedDataset?.task_id)
  const blockers = quality?.blockers ?? []
  const warnings = [...(quality?.warnings ?? []), ...(bundle?.warnings ?? [])]
  const latestCandidate = useMemo(() => overview?.versions.find((item) => item.version_id === job?.version_id && item.integrity_valid)
    ?? [...(overview?.versions ?? [])].reverse().find((item) => item.integrity_valid && item.state === 'awaiting_evaluation'), [overview?.versions, job?.version_id])
  const currentStep: StepId = job?.state === 'queued' || job?.state === 'running' ? 'train'
    : evaluationJob?.state === 'queued' || evaluationJob?.state === 'running' ? 'evaluate'
    : latestCandidate?.state === 'awaiting_evaluation' ? 'evaluate'
    : latestCandidate?.state === 'awaiting_approval' ? 'decide'
    : bundle ? 'train' : quality?.ready ? 'split' : overview?.active_version ? 'rollback' : 'check'

  async function doCheck() {
    if (!datasetName) return
    setBusy(true); setError(null); setNotice(null); setBundle(null); setEvaluation(null)
    try { const result = await checkTrainingDataset(datasetName); setQuality(result); setNotice(result.ready ? 'Quality gate concluído. A fonte original não foi alterada.' : 'A verificação encontrou bloqueadores; corrija-os antes de criar o split.') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'A verificação de qualidade falhou.') }
    finally { setBusy(false) }
  }
  async function doSplit() {
    if (!datasetName) return
    setBusy(true); setError(null); setNotice(null); setEvaluation(null)
    try {
      const result = await splitTrainingDataset({ dataset_name: datasetName, strategy, holdout_fraction: Number(holdout), seed: Number(seed),
        ...(strategy === 'group' ? { group_column: splitColumn } : {}), ...(strategy === 'temporal' ? { time_column: splitColumn } : {}) })
      setBundle(result); setExploratoryConfirmed(false); setTrainConfirmed(false); setNotice('Partições criadas e manifesto verificado. Nenhum treino foi iniciado.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível preparar as partições.') }
    finally { setBusy(false) }
  }
  async function doTrain() {
    if (!bundle || !overview?.gate.model_id) return
    setBusy(true); setError(null); setNotice(null)
    try {
      const result = await submitTraining({ bundle_id: bundle.bundle_id, model_id: overview.gate.model_id,
        confirmed: trainConfirmed, exploratory_confirmed: warnings.length > 0 && exploratoryConfirmed,
        revision: selectedTask?.model_ref.includes('@') ? selectedTask.model_ref.split('@').slice(1).join('@') : null })
      setJobId(result.job_id); setJob({ job_id: result.job_id, state: result.state as TrainingJob['state'], progress: result.progress,
        error: null, model_id: overview.gate.model_id, dataset_sha256: selectedDataset?.sha256 ?? '', final_metrics: {}, bundle_id: bundle.bundle_id, version_id: null })
      setNotice('Treino local enfileirado com confirmação explícita. O painel acompanhará o status do servidor.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível iniciar o treino.') }
    finally { setBusy(false) }
  }
  async function doEvaluate(version: TrainingVersion) {
    const okay = window.confirm(`Avaliar o candidato ${version.version_id} localmente no holdout reservado? O modelo base e o adaptador serão executados neste dispositivo.`)
    if (!okay) return
    setEvaluating(version.version_id); setError(null); setNotice(null)
    try {
      const result = await evaluateTrainingCandidate(version.version_id)
      const status: EvaluationJob = { job_id: result.job_id, state: result.state, progress: result.progress,
        error: null, version_id: version.version_id }
      setEvaluationJob(status); setEvaluationJobId(result.job_id)
      setNotice('Avaliação local enfileirada. O painel mostrará o resultado somente após o job e o registro terminarem.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'A avaliação não foi enfileirada.') }
    finally { setEvaluating(null) }
  }
  async function transition(action: 'activate' | 'reject' | 'rollback' | 'recover', version: TrainingVersion) {
    const copy = action === 'activate' ? `Ativar ${version.version_id} como versão ativa?` : action === 'rollback' ? `Restaurar ${version.version_id} como versão ativa?` : action === 'recover' ? `Recuperar o ponteiro ativo usando a versão verificada ${version.version_id}?` : `Rejeitar o candidato ${version.version_id}?`
    if (!window.confirm(`${copy} A ação será registrada localmente.`)) return
    setError(null); setNotice(null)
    try { await transitionTrainingVersion({ action, version_id: version.version_id, confirmed: true,
      ...(action === 'reject' ? { reason: 'Rejeitado pelo usuário após revisão no painel local.' } : {}) });
      if (action === 'activate' || action === 'rollback' || action === 'recover') { setBundle(null); setQuality(null) }
      setNotice(action === 'activate' ? 'Versão ativada.' : action === 'rollback' ? 'Rollback registrado.' : action === 'recover' ? 'Ponteiro ativo recuperado para uma versão íntegra.' : 'Candidato rejeitado.'); await refreshVersions()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'A transição foi recusada; o estado não foi confirmado.') }
  }

  return <div className="space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 text-sm font-medium text-[#47805f]">CICLO SUPERVISIONADO / LOCAL</p><h1 className="text-3xl font-semibold tracking-tight">Treinamento e versões</h1><p className="mt-2 max-w-3xl text-sm leading-relaxed text-[#718077]">Prepare dados revisados, verifique a qualidade, crie partições, solicite o treino e avalie no holdout antes de qualquer ativação.</p></div>
      <Button variant="outline" className="gap-2" onClick={() => void refresh()}><RefreshCw size={15}/>Atualizar estado</Button></div>
    {error && <div role="alert" className="rounded-lg border border-[#f0d5d1] bg-white p-4 text-sm text-[#963f35]">{error}</div>}
    {notice && <div role="status" className="rounded-lg border border-[#d7e8db] bg-[#f4faf5] p-3 text-sm text-[#286444]">{notice}</div>}
    <TrainingWorkflow current={currentStep}/>

    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(300px,.72fr)]">
      <Card className="border-[#e1e8e2] shadow-sm"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Database size={17} className="text-[#32845b]"/>Dados, quality gate e split</CardTitle><CardDescription>A origem é somente leitura. O dataset precisa ser exportado de exemplos revisados pela CLI ou pela tela de revisão.</CardDescription></CardHeader>
        <CardContent className="space-y-5">
          <label className="block text-sm font-medium">Dataset local<select className="mt-2 w-full rounded-md border border-[#dce5de] bg-white px-3 py-2.5 text-sm" value={datasetName} onChange={(event) => { setDatasetName(event.target.value); setQuality(null); setBundle(null); setEvaluation(null) }}>
            <option value="">Selecione um dataset revisado</option>{overview?.datasets.map((item) => <option key={item.name} value={item.name}>{item.name} · {item.rows ?? 'manifesto inválido'} linhas</option>)}</select></label>
          {selectedDataset && <p className="-mt-3 text-xs text-[#718077]">Tarefa: {selectedDataset.task_id ?? 'não reconhecida'} · fonte: {selectedDataset.source ?? 'não reconhecida'} · SHA-256: <span className="font-mono">{selectedDataset.sha256?.slice(0,16) ?? 'indisponível'}</span></p>}
          <div className="flex flex-wrap items-center gap-3"><Button disabled={busy || !datasetName} onClick={() => void doCheck()} className="gap-2 bg-[#176c48] hover:bg-[#11583a]">{busy ? 'Verificando…' : 'Executar quality gate'}<ShieldCheck size={15}/></Button>
            {quality && <Badge variant="outline" className={quality.ready ? 'border-[#cde4d1] bg-[#eff8f0] text-[#286444]' : 'border-[#f0d5d1] bg-[#fff5f3] text-[#963f35]'}>{quality.ready ? 'Dataset pronto para split' : 'Bloqueado'}</Badge>}</div>
          {quality && <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-lg bg-[#f7faf7] p-3"><span className="text-xs text-[#718077]">Exemplos revisados</span><b className="mt-1 block text-lg">{num(quality.total)}</b></div><div className="rounded-lg bg-[#f7faf7] p-3"><span className="text-xs text-[#718077]">Snapshot da fonte</span><b className="mt-1 block text-sm">{quality.source_snapshot_matches ? 'Corresponde' : 'Divergente'}</b></div><div className="rounded-lg bg-[#f7faf7] p-3"><span className="text-xs text-[#718077]">Exemplos duplicados</span><b className="mt-1 block text-lg">{num(quality.duplicate_examples)}</b></div></div>}
          {quality && <div className="rounded-lg border border-[#e6ece7] p-3"><p className="mb-2 text-xs font-semibold">Cobertura por rótulo</p><div className="flex flex-wrap gap-2">{Object.entries(quality.label_counts).map(([label,count])=><Badge key={label} variant="outline">{label}: {count}</Badge>)}</div></div>}
          {blockers.length > 0 && <div role="alert" className="rounded-lg border border-[#f0d5d1] bg-[#fff8f7] p-3 text-xs text-[#963f35]"><b>Bloqueadores</b><ul className="mt-2 list-disc space-y-1 pl-5">{blockers.map((item,index)=><li key={index}>{item}</li>)}</ul></div>}
          {quality?.warnings.map((warning,index)=><p key={index} className="flex items-start gap-2 rounded-lg bg-[#fffaf0] p-3 text-xs text-[#795a22]"><AlertTriangle size={14} className="mt-0.5 shrink-0"/>{warning}</p>)}
          {quality?.ready && <div className="space-y-3 rounded-lg border border-[#e6ece7] p-4"><p className="text-sm font-semibold">Configurar partições</p>
            <div className="grid gap-3 sm:grid-cols-3"><label className="text-xs font-medium">Estratégia<select className="mt-1.5 w-full rounded-md border px-2 py-2 text-sm" value={strategy} onChange={(event)=>{setStrategy(event.target.value);setBundle(null)}}><option value="stratified_random">Estratificado aleatório</option><option value="temporal">Temporal</option><option value="group">Por grupo</option></select></label>
              <label className="text-xs font-medium">Holdout (fração)<input type="number" min="0.01" max="0.99" step="0.05" className="mt-1.5 w-full rounded-md border px-2 py-2 text-sm" value={holdout} onChange={(event)=>setHoldout(event.target.value)}/></label>
              <label className="text-xs font-medium">Semente<input type="number" min="0" step="1" className="mt-1.5 w-full rounded-md border px-2 py-2 text-sm" value={seed} onChange={(event)=>setSeed(event.target.value)}/></label></div>
            {strategy !== 'stratified_random' && <label className="block text-xs font-medium">Coluna de {strategy === 'temporal' ? 'tempo' : 'grupo'}<input className="mt-1.5 w-full rounded-md border px-2 py-2 text-sm" value={splitColumn} onChange={(event)=>setSplitColumn(event.target.value)} placeholder={strategy === 'temporal' ? 'data_movimento' : 'id_cliente'}/></label>}
            <Button disabled={busy || (strategy !== 'stratified_random' && !splitColumn.trim()) || !Number.isFinite(Number(holdout)) || !Number.isInteger(Number(seed))} variant="outline" className="gap-2" onClick={()=>void doSplit()}><Split size={15}/>{busy ? 'Preparando…' : 'Criar split local'}</Button>
          </div>}
          {bundle && <div className="rounded-lg border border-[#cfe4d4] bg-[#f5faf5] p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold text-[#286444]">Split {bundle.bundle_id} pronto</p><Check size={16} className="text-[#25845a]"/></div>
            <p className="mt-1 text-xs text-[#59675d]">{bundle.strategy} · seed {bundle.seed} · treino {num(bundle.train_count)} · holdout {num(bundle.holdout_count)}</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">{Object.entries(bundle.label_counts).map(([part,counts])=><div key={part} className="rounded bg-white p-2"><p className="text-xs font-semibold">{part === 'train' ? 'Treino' : 'Holdout'}</p><p className="mt-1 text-xs text-[#718077]">{Object.entries(counts).map(([label,count])=>`${label}: ${count}`).join(' · ')}</p></div>)}</div>
            {warnings.length > 0 && <label className="mt-3 flex items-start gap-2 text-xs text-[#795a22]"><input type="checkbox" checked={exploratoryConfirmed} onChange={(event)=>setExploratoryConfirmed(event.target.checked)} className="mt-0.5"/>Revisei os avisos e confirmo continuar de forma exploratória; os avisos não validam a qualidade do modelo.</label>}
            <label className="mt-3 flex items-start gap-2 text-xs text-[#59675d]"><input type="checkbox" checked={trainConfirmed} onChange={(event)=>setTrainConfirmed(event.target.checked)} className="mt-0.5"/>Confirmo iniciar treinamento local com <b>{overview?.gate.model_id ?? 'modelo não configurado'}</b>, usando exclusivamente a partição train.</label>
            <Button disabled={busy || jobId !== '' || !trainConfirmed || (warnings.length > 0 && !exploratoryConfirmed) || !overview?.gate.authorized || overview.gate.missing.length > 0} className="mt-3 gap-2 bg-[#176c48] hover:bg-[#11583a]" onClick={()=>void doTrain()}><Play size={14}/>{busy ? 'Enviando…' : 'Iniciar treinamento'}</Button>
            {(!overview?.gate.authorized || (overview.gate.missing.length ?? 0)>0) && <p className="mt-2 text-xs text-[#963f35]">Autorização do projeto incompleta. Configure pelo CLI: {overview?.gate.missing.join(', ') || 'training gate não autorizado'}.</p>}
            {bundle.warnings.map((warning,index)=><p key={index} className="mt-2 text-xs text-[#795a22]">Aviso do split: {warning}</p>)}
          </div>}
        </CardContent></Card>

      <div className="space-y-5"><Card className="border-[#e1e8e2] shadow-sm"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><WandSparkles size={17} className="text-[#32845b]"/>Estado e autorização</CardTitle><CardDescription>Treino e avaliação são operações locais explícitas; pesos não são baixados automaticamente pelo painel.</CardDescription></CardHeader><CardContent className="space-y-3 text-sm">
        <div className="flex justify-between gap-3"><span className="text-[#718077]">Modelo do gate</span><b className="break-all text-right">{overview?.gate.model_id ?? 'não configurado'}</b></div>
        <div className="flex justify-between gap-3"><span className="text-[#718077]">Autorização local</span><Badge variant="outline">{overview?.gate.authorized ? 'Autorizado' : 'Pendente'}</Badge></div>
        <div className="flex justify-between gap-3"><span className="text-[#718077]">Versão ativa</span><b className="font-mono text-xs">{overview?.active_version ?? 'Nenhuma'}</b></div>
        {overview?.gate.missing?.length ? <div className="rounded-lg bg-[#fff8f7] p-3 text-xs text-[#963f35]">Gate pendente: {overview.gate.missing.join(', ')}. O painel não altera a autorização de treino.</div> : null}
        {overview?.active_diagnostic && <div role="alert" className="rounded-lg border border-[#edcfaa] bg-[#fff9ef] p-3 text-xs text-[#795a22]"><b>Versão ativa indisponível</b><p className="mt-1">{overview.active_diagnostic}</p><p className="mt-1">O histórico foi preservado. Use Recuperar em uma versão anterior cuja integridade esteja verificada.</p></div>}
        {overview?.registry_diagnostics.length ? <details className="rounded-lg border border-[#e6ece7] p-3 text-xs"><summary className="cursor-pointer font-medium">Diagnósticos do histórico ({overview.registry_diagnostics.length})</summary><ul className="mt-2 list-disc space-y-1 pl-5">{overview.registry_diagnostics.map((item) => <li key={item.version_id}><code>{item.version_id}</code>: {item.error}</li>)}</ul></details> : null}
        <p className="flex gap-2 rounded-lg bg-[#f7faf7] p-3 text-xs leading-relaxed text-[#59675d]"><CircleHelp size={15} className="mt-0.5 shrink-0"/>Instale pesos e dependências compatíveis antes de pedir uma operação real. A avaliação executa modelo base e candidato e pode consumir memória/tempo local.</p>
      </CardContent></Card>
      {job && <Card className={`border shadow-sm ${job.state === 'failed' ? 'border-[#f0d5d1]' : 'border-[#dce8df]'}`}><CardHeader><CardTitle className="text-base">Trabalho {job.state === 'failed' ? 'com falha' : job.state === 'succeeded' ? 'concluído' : 'em andamento'}</CardTitle><CardDescription className="font-mono text-xs">{job.job_id}</CardDescription></CardHeader><CardContent><p className="text-sm">{job.progress}</p>{job.error && <p role="alert" className="mt-2 text-xs text-[#963f35]">{job.error}</p>}</CardContent></Card>}
      {evaluationJob && <Card className={`border shadow-sm ${evaluationJob.state === 'failed' ? 'border-[#f0d5d1]' : evaluationJob.state === 'succeeded' ? 'border-[#cde4d1]' : 'border-[#dce8df]'}`}><CardHeader><CardTitle className="text-base">Avaliação {evaluationJob.state === 'queued' ? 'na fila' : evaluationJob.state === 'running' ? 'em andamento' : evaluationJob.state === 'succeeded' ? 'concluída' : 'com falha'}</CardTitle><CardDescription className="font-mono text-xs">{evaluationJob.job_id} · {evaluationJob.version_id}</CardDescription></CardHeader><CardContent><p className="text-sm">{evaluationJob.progress}</p>{evaluationJob.error && <p role="alert" className="mt-2 text-xs text-[#963f35]">{evaluationJob.error}</p>}</CardContent></Card>}
      </div>
    </div>

    {evaluation && <Card className="border-[#dce8df] shadow-sm"><CardHeader><CardTitle className="text-base">Relatório do holdout</CardTitle><CardDescription>Comparação entre base e adaptador; números não são uma garantia de desempenho futuro.</CardDescription></CardHeader><CardContent><MetricTable report={evaluation}/></CardContent></Card>}

    <Card className="border-[#e1e8e2] shadow-sm"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><RotateCcw size={17} className="text-[#32845b]"/>Histórico de versões</CardTitle><CardDescription>Ativação, rejeição e rollback passam pelo registro local e pedem confirmação explícita.</CardDescription></CardHeader><CardContent className="space-y-3">
      {!overview?.versions.length && <p className="rounded-lg border border-dashed p-4 text-sm text-[#718077]">Nenhum candidato foi registrado ainda.</p>}
      {overview?.versions.map((version) => <article key={version.version_id} className="rounded-xl border border-[#e6ece7] p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-mono text-sm font-semibold">{version.version_id}</h3><Badge variant="outline" className={version.is_active && version.integrity_valid ? 'border-[#cde4d1] bg-[#eff8f0] text-[#286444]' : ''}>{!version.integrity_valid ? 'integridade inválida' : version.is_active ? 'ativa' : version.state}</Badge></div><p className="mt-1 text-xs text-[#718077]">{version.base_model_ref} · {version.created_at ? new Date(version.created_at).toLocaleString('pt-BR') : 'data indisponível'}</p><p className="mt-1 font-mono text-[10px] text-[#89958c]">dataset {version.dataset_sha256.slice(0,12) || '—'} · split {version.split_sha256.slice(0,12) || '—'}</p>{!version.integrity_valid && <p role="alert" className="mt-2 max-w-2xl text-xs text-[#963f35]">{version.integrity_error ?? 'Esta versão não passou pela verificação de integridade; operações estão desabilitadas.'}</p>}</div>
          <div className="flex flex-wrap gap-2">{version.integrity_valid && version.state === 'awaiting_evaluation' && <Button size="sm" disabled={evaluating !== null || evaluationJobId !== ''} onClick={()=>void doEvaluate(version)}>{evaluating === version.version_id ? 'Enfileirando…' : evaluationJobId ? 'Avaliação em andamento' : 'Avaliar no holdout'}</Button>}
            {version.integrity_valid && version.state === 'awaiting_approval' && <><Button size="sm" onClick={()=>void transition('activate',version)}>Ativar</Button><Button size="sm" variant="outline" onClick={()=>void transition('reject',version)}>Rejeitar</Button></>}
            {version.integrity_valid && version.state === 'superseded' && overview.active_diagnostic && <Button size="sm" variant="outline" className="gap-1" onClick={()=>void transition('recover',version)}><RotateCcw size={13}/>Recuperar versão ativa</Button>}
            {version.integrity_valid && version.state === 'superseded' && !overview.active_diagnostic && <Button size="sm" variant="outline" className="gap-1" onClick={()=>void transition('rollback',version)}><RotateCcw size={13}/>Rollback</Button>}</div></div>
          {version.evaluation && <div className="mt-4"><MetricTable report={version.evaluation}/></div>}
        </article>)}
    </CardContent></Card>
  </div>
}
