import { useEffect, useMemo } from 'react'
import type { AutonomyOverview } from '@/application/ports/LazyLabelClient'
import { useLazyLabelClient } from '@/application/LazyLabelClientContext'
import { SpecView } from '@/ui/SpecView'
import { usePageStore, type Spec } from '@/ui/store'
import spec from '@/specs/training.json'

const metricNames = { accuracy: 'Acurácia', macro_f1: 'Macro F1', coverage: 'Cobertura', calibration_error: 'Erro de calibração' } as const
const percent = (v: number | undefined) => typeof v === 'number' && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : '—'
const when = (iso: string | null, fallback: string) => iso ? new Date(iso).toLocaleString('pt-BR') : fallback

// Index into the seven workflow steps: blocked → verify data, rejected → promote/reject, else → monitor.
function currentStep(o: AutonomyOverview) {
  const cycle = o.training_cycles[0]
  if (!cycle || cycle.state === 'blocked') return 0
  return cycle.state === 'rejected' ? 5 : 6
}

function view(o: AutonomyOverview) {
  const cycle = o.training_cycles[0]
  const active = o.active_models.filter((m) => m.model_ref)
  const events = [...o.model_events].reverse()
  const actionName = (a: string) => a === 'rollback' ? 'Rollback automático' : a === 'promote' ? 'Modelo promovido' : 'Candidato rejeitado'
  return {
    '/step': currentStep(o),
    '/hasEvaluation': Boolean(cycle?.evaluation),
    '/evaluation': cycle?.evaluation ? {
      summary: `${cycle.evaluation.holdout_count.toLocaleString('pt-BR')} registros · candidato e modelo atual no mesmo holdout`,
      metrics: (Object.keys(metricNames) as (keyof typeof metricNames)[]).map((k) => ({ label: metricNames[k],
        value: percent(cycle.evaluation?.candidate_metrics[k]), hint: `Modelo atual: ${percent(cycle.evaluation?.incumbent_metrics[k])}` })),
    } : { summary: '', metrics: [] },
    '/noActive': active.length === 0,
    '/activeModels': active.map((m) => ({ task: m.task_id, ref: m.model_ref })),
    '/noCycle': !cycle, '/hasCycle': Boolean(cycle),
    '/cycle': cycle ? { task: `Último ciclo · ${cycle.task_id}`, state: cycle.state, reasons: cycle.reason_codes,
      hasReasons: cycle.reason_codes.length > 0, promotion: `Promoção: ${cycle.promotion_action ?? 'nenhuma'}` } : {},
    '/noHistory': o.training_cycles.length === 0 && events.length === 0,
    '/history': [
      ...o.training_cycles.map((c) => ({ id: c.cycle_id, title: `Ciclo · ${c.task_id}`, badge: `${c.state} · ${c.promotion_action ?? 'sem promoção'}`,
        detail: `${when(c.created_at, c.cycle_id)} · candidato ${c.candidate_id ?? 'não criado'} · avaliação ${c.evaluation_id ?? 'indisponível'}`, reasons: [] })),
      ...events.map((e) => ({ id: e.event_id, title: `${actionName(e.action)} · ${e.task_id}`, badge: e.action,
        detail: when(e.created_at, '') + (e.rollback_from ? ` · restaurado: ${e.rollback_from}` : ''), reasons: e.reason_codes })),
    ],
  }
}

export default function TrainingPage() {
  const client = useLazyLabelClient()
  const store = usePageStore({ loading: true, error: null, step: 0, hasEvaluation: false, evaluation: { summary: '', metrics: [] },
    noActive: false, activeModels: [], noCycle: false, hasCycle: false, cycle: {}, noHistory: false, history: [] })
  const refresh = useMemo(() => () => {
    store.update({ '/error': null })
    return client.getAutonomyOverview().then((o) => store.update(view(o)))
      .catch((cause) => store.update({ '/error': cause instanceof Error ? cause.message : 'Não foi possível carregar o histórico local.' }))
      .finally(() => store.update({ '/loading': false }))
  }, [client, store])
  useEffect(() => { void refresh() }, [refresh])
  return <SpecView spec={spec as Spec} store={store} handlers={{ refresh }} />
}
