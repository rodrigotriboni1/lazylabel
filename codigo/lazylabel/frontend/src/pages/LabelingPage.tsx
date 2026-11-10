import { useEffect, useMemo, useRef } from 'react'
import type { AutonomyOverview } from '@/application/ports/LazyLabelClient'
import { useLazyLabelClient } from '@/application/LazyLabelClientContext'
import { SpecView } from '@/ui/SpecView'
import { usePageStore, type Spec } from '@/ui/store'
import spec from '@/specs/labeling.json'

const message = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback

export default function LabelingPage() {
  const client = useLazyLabelClient()
  const store = usePageStore({ loading: true, busy: false, error: null, source: '', task: '', sourceOptions: [], taskOptions: [],
    hasTask: false, taskInfo: { inputs: [], labels: [], model: '', noPolicy: false }, showEmpty: false,
    runDisabled: true, runLabel: 'Executar ciclo autônomo', showResult: false, result: {}, runs: [], noRuns: true })
  const overview = useRef<AutonomyOverview | null>(null)
  // One key per chosen (source, task); a retry of the same choice reuses it.
  const idempotencyKey = useRef(crypto.randomUUID())

  const handlers = useMemo(() => {
    const sync = () => {
      const o = overview.current
      const task = o?.tasks.find((t) => t.task_id === store.get('/task'))
      const busy = store.get('/busy') as boolean
      store.update({
        '/hasTask': Boolean(task),
        '/taskInfo': task ? { inputs: task.input_columns, labels: task.labels, model: `Modelo: ${task.model_ref}`, noPolicy: !task.policy_configured }
          : { inputs: [], labels: [], model: '', noPolicy: false },
        '/showEmpty': Boolean(o) && !task && !store.get('/error'),
        '/runDisabled': busy || store.get('/loading') === true || !store.get('/source') || !task,
        '/runLabel': busy ? 'Executando ciclo…' : 'Executar ciclo autônomo',
      })
    }
    const refresh = () => client.getAutonomyOverview().then((o) => {
      overview.current = o
      const keep = (current: unknown, names: string[]) => names.includes(current as string) ? current : names[0] ?? ''
      store.update({
        '/error': null,
        '/sourceOptions': o.sources.map((s) => ({ value: s.name, label: `${s.name} · ${s.kind}` })),
        '/taskOptions': o.tasks.map((t) => ({ value: t.task_id, label: t.task_id })),
        '/source': keep(store.get('/source'), o.sources.map((s) => s.name)),
        '/task': keep(store.get('/task'), o.tasks.map((t) => t.task_id)),
        '/noRuns': o.runs.length === 0,
        '/runs': o.runs.map((r) => ({ id: r.run_id, training: `Treino ${r.training.state}`,
          text: `${r.source} · ${r.task_id} · ${new Date(r.finished_at).toLocaleString('pt-BR')} · ${r.labels.applied} aplicados · ${r.labels.quarantined} em quarentena` })),
      })
    }).catch((cause) => store.update({ '/error': message(cause, 'Não foi possível carregar o estado local.') }))
      .finally(() => { store.update({ '/loading': false }); sync() })
    const select = () => { idempotencyKey.current = crypto.randomUUID(); sync() }
    const run = async () => {
      const source = store.get('/source') as string, task = store.get('/task') as string
      if (!source || !task) return
      store.update({ '/busy': true, '/error': null, '/showResult': false }); sync()
      try {
        const r = await client.runAutonomousCycle(source, task, idempotencyKey.current)
        const count = (n: number) => n.toLocaleString('pt-BR')
        store.update({ '/showResult': true, '/result': {
          summary: `Execução ${r.run_id.slice(0, 12)} · ${r.source} · tarefa ${r.task_id}`,
          total: count(r.labeling.outcome_count), applied: count(r.labeling.applied_count), quarantined: count(r.labeling.quarantined_count),
          trainingState: r.training.state + (r.training.promotion_action ? ` · ${r.training.promotion_action}` : ''),
          reasons: Object.keys(r.labeling.reason_counts).length ? 'Motivos: ' + Object.entries(r.labeling.reason_counts).map(([k, v]) => `${k}: ${v}`).join(' · ') : '',
        } })
        idempotencyKey.current = crypto.randomUUID()
        await refresh()
      } catch (cause) {
        store.update({ '/error': message(cause, 'A execução local falhou.') })
      } finally {
        store.update({ '/busy': false }); sync()
      }
    }
    return { refresh, select, run }
  }, [client, store])

  useEffect(() => { void handlers.refresh() }, [handlers])
  return <SpecView spec={spec as Spec} store={store} handlers={handlers} />
}
