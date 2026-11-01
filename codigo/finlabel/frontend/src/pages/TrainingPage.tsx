import { useCallback, useEffect, useState } from 'react'
import { Activity, ArrowRight, Check, CircleAlert, RefreshCw, RotateCcw, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { AutonomyOverview } from '@/application/ports/FinLabelClient'
import { useFinLabelClient } from '@/application/FinLabelClientContext'

const steps = [
  { id: 'check', title: 'Verificar dados', detail: 'Integridade, qualidade e proveniência' },
  { id: 'split', title: 'Dividir', detail: 'Treino · calibração · holdout congelado' },
  { id: 'train', title: 'Treinar', detail: 'Lote local com exemplos confiáveis' },
  { id: 'evaluate', title: 'Avaliar', detail: 'Métricas recomputadas no holdout' },
  { id: 'decide', title: 'Decidir', detail: 'Aplicar gates definidos para a tarefa' },
  { id: 'promote', title: 'Promover / rejeitar', detail: 'Decisão automática registrada' },
  { id: 'rollback', title: 'Monitorar / reverter', detail: 'Rollback automático com evidência' },
] as const
type StepId = typeof steps[number]['id']

function currentStep(overview: AutonomyOverview | null): StepId {
  const cycle = overview?.training_cycles[0]
  if (!cycle) return 'check'
  if (cycle.state === 'blocked') return 'check'
  if (cycle.state === 'rejected') return 'promote'
  return 'rollback'
}

function TrainingWorkflow({ current }: { current: StepId }) {
  return <Card className="border-[#dce8df] bg-white shadow-sm">
    <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><Activity size={17} className="text-[#32845b]"/>Ciclo autônomo de treinamento</CardTitle>
      <CardDescription>Treino em lote; só há promoção quando o holdout congelado e todos os gates passam.</CardDescription></CardHeader>
    <CardContent>
      <ol aria-label="Workflow de treinamento autônomo" className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-7">
        {steps.map((step, index) => {
          const active = step.id === current
          const currentIndex = steps.findIndex((item) => item.id === current)
          const completed = index < currentIndex
          return <li key={step.id} aria-current={active ? 'step' : undefined} className="relative min-w-0">
            <div className={`h-full rounded-lg border p-3 ${active ? 'border-[#248252] bg-[#eaf5ed] ring-2 ring-[#248252]/20' : completed ? 'border-[#cde4d3] bg-[#f7faf7]' : 'border-[#e6ece7] bg-[#fafcf9]'}`}>
              <div className="flex items-center gap-2"><span className={`grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold ${active ? 'bg-[#176c48] text-white' : completed ? 'bg-[#d9eddf] text-[#176c48]' : 'bg-white text-[#718077]'}`}>{completed ? <Check size={13}/> : index + 1}</span>
                <span className={`text-xs font-semibold leading-tight ${active ? 'text-[#176c48]' : 'text-[#34493a]'}`}>{step.title}</span></div>
              <p className="mt-2 text-[11px] leading-snug text-[#718077]">{step.detail}</p>
              {active && <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-[#176c48]"><span className="size-1.5 rounded-full bg-[#25845a]"/>Estado atual</span>}
            </div>
            {index < steps.length - 1 && <ArrowRight aria-hidden="true" size={13} className="absolute -right-2 top-1/2 z-10 hidden -translate-y-1/2 text-[#9aa79e] lg:block"/>}
          </li>
        })}
      </ol>
      <p className="mt-4 text-xs leading-relaxed text-[#718077]">Verificar dados → dividir → treinar → avaliar → decidir → promover ou rejeitar → monitorar e reverter automaticamente se a saúde piorar.</p>
    </CardContent>
  </Card>
}

export default function TrainingPage() {
  const client = useFinLabelClient()
  const [overview, setOverview] = useState<AutonomyOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const load = useCallback(() => client.getAutonomyOverview()
    .then(setOverview, (cause) => setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o histórico local.'))
    .finally(() => setLoading(false)), [client])
  useEffect(() => { void load() }, [load])
  const refresh = () => { setError(null); void load() }

  const activeStep = currentStep(overview)
  const activeModels = overview?.active_models.filter((item) => item.model_ref) ?? []
  const cycles = overview?.training_cycles ?? []
  const events = [...(overview?.model_events ?? [])].reverse()
  return <div className="space-y-7">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 text-sm font-medium text-[#47805f]">TREINAMENTO / CICLO LOCAL</p><h1 className="text-3xl font-semibold tracking-tight">Treino com promoção segura</h1><p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#718077]">Rótulos confiáveis alimentam ciclos em lote. Avaliação congelada decide promoção; dados insuficientes, políticas ausentes ou falhas mantêm o modelo atual.</p></div><Button variant="outline" className="gap-2" onClick={refresh}><RefreshCw size={15}/>Atualizar</Button></div>
    {error && <div role="alert" className="rounded-lg border border-[#f0d5d1] bg-white p-4 text-sm text-[#963f35]">{error}</div>}
    <TrainingWorkflow current={activeStep}/>
    {cycles[0]?.evaluation && <Card className="border-[#dce8df] bg-white"><CardHeader><CardTitle className="text-base">Avaliação congelada mais recente</CardTitle><CardDescription>{cycles[0].evaluation.holdout_count.toLocaleString('pt-BR')} registros · candidato e modelo ativo comparados no mesmo holdout</CardDescription></CardHeader><CardContent><div className="grid gap-3 sm:grid-cols-4">{(['accuracy', 'macro_f1', 'coverage', 'calibration_error'] as const).map((metric) => <div key={metric} className="rounded-lg bg-[#f7faf7] p-3"><p className="text-xs text-[#718077]">{{ accuracy: 'Acurácia', macro_f1: 'Macro F1', coverage: 'Cobertura', calibration_error: 'Erro de calibração' }[metric]}</p><p className="mt-1 text-lg font-semibold">{formatMetric(cycles[0].evaluation?.candidate_metrics[metric])}</p><p className="mt-1 text-[11px] text-[#718077]">Modelo atual: {formatMetric(cycles[0].evaluation?.incumbent_metrics[metric])}</p></div>)}</div></CardContent></Card>}
    <div className="grid gap-5 lg:grid-cols-2">
      <Card className="border-[#e1e8e2] bg-white"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><ShieldCheck size={17} className="text-[#32845b]"/>Modelo ativo</CardTitle><CardDescription>Referência aplicada pelo ciclo local de inferência.</CardDescription></CardHeader><CardContent>
        {loading ? <p className="text-sm text-[#718077]">Carregando estado…</p> : activeModels.length ? <div className="space-y-2">{activeModels.map((model) => <div key={model.task_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-[#f7faf7] p-3"><div><p className="text-sm font-medium">{model.task_id}</p><p className="mt-1 break-all text-xs text-[#718077]">{model.model_ref}</p></div><Badge className="bg-[#e7f3e9] text-[#286444] hover:bg-[#e7f3e9]">Ativo</Badge></div>)}</div> : <p className="rounded-lg border border-dashed border-[#dce5de] p-4 text-sm text-[#718077]">Nenhum adapter promovido. O modelo base continua em uso quando a política permite inferência.</p>}
      </CardContent></Card>
      <Card className="border-[#e1e8e2] bg-white"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><CircleAlert size={17} className="text-[#83733b]"/>Estado dos gates</CardTitle><CardDescription>Ausência ou falha de evidência bloqueia treino ou promoção.</CardDescription></CardHeader><CardContent>
        {cycles[0] ? <div className="rounded-lg bg-[#f7faf7] p-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium">Último ciclo · {cycles[0].task_id}</p><Badge variant="outline">{cycles[0].state}</Badge></div>{cycles[0].reason_codes.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-[#718077]">{cycles[0].reason_codes.map((reason) => <li key={reason}>{reason}</li>)}</ul>}<p className="mt-2 text-xs text-[#718077]">Promoção: {cycles[0].promotion_action ?? 'nenhuma'}</p></div> : <p className="text-sm text-[#718077]">Aguardando a primeira execução do ciclo autônomo.</p>}
      </CardContent></Card>
    </div>
    <section aria-labelledby="cycle-history-title"><h2 id="cycle-history-title" className="mb-3 text-lg font-semibold">Histórico de ciclos e decisões</h2>
      {cycles.length === 0 && events.length === 0 ? <p className="rounded-lg border border-dashed border-[#dce5de] bg-white p-5 text-sm text-[#718077]">Ainda não há ciclos ou decisões registrados.</p> : <div className="space-y-3">{cycles.map((cycle) => <Card key={cycle.cycle_id} className="border-[#e1e8e2] bg-white"><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4"><div><p className="text-sm font-medium">Ciclo · {cycle.task_id}</p><p className="mt-1 text-xs text-[#718077]">{cycle.created_at ? new Date(cycle.created_at).toLocaleString('pt-BR') : cycle.cycle_id} · candidato {cycle.candidate_id ?? 'não criado'} · avaliação {cycle.evaluation_id ?? 'indisponível'}</p></div><Badge variant="outline">{cycle.state} · {cycle.promotion_action ?? 'sem promoção'}</Badge></CardContent></Card>)}
        {events.map((event) => <Card key={event.event_id} className="border-[#e1e8e2] bg-white"><CardContent className="flex flex-wrap items-center justify-between gap-3 p-4"><div className="flex items-start gap-3"><RotateCcw size={16} className="mt-0.5 text-[#83733b]"/><div><p className="text-sm font-medium">{event.action === 'rollback' ? 'Rollback automático' : event.action === 'promote' ? 'Modelo promovido' : 'Candidato rejeitado'} · {event.task_id}</p><p className="mt-1 text-xs text-[#718077]">{new Date(event.created_at).toLocaleString('pt-BR')} {event.rollback_from ? `· restaurado: ${event.rollback_from}` : ''}</p>{event.reason_codes.length > 0 && <p className="mt-1 text-xs text-[#718077]">{event.reason_codes.join(' · ')}</p>}</div></div><Badge variant="outline">{event.action}</Badge></CardContent></Card>)}
      </div>}
    </section>
  </div>
}

function formatMetric(value: number | undefined) {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—'
}
