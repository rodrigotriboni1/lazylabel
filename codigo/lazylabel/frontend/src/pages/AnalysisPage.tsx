import { useEffect, useMemo } from 'react'
import { ApiError, type AnalysisPlan } from '@/application/ports/LazyLabelClient'
import { useLazyLabelClient } from '@/application/LazyLabelClientContext'
import { SpecView } from '@/ui/SpecView'
import { usePageStore, type Spec } from '@/ui/store'
import spec from '@/specs/analysis.json'

const defaultPlan = JSON.stringify({ version: 1, metric: { operation: 'count_rows', column: null, denominator_scope: null }, dimensions: [], time_axis: null, filters: [], chart: 'bar' }, null, 2)

export default function AnalysisPage({ runId }: { runId?: string }) {
  const client = useLazyLabelClient()
  const store = usePageStore({ source: '', sourceOptions: [], hasSources: false, noSources: false, question: '', planText: defaultPlan,
    busy: Boolean(runId), notice: null, clarifications: null, error: null, result: null, waiting: false })

  const handlers = useMemo(() => {
    const settle = () => store.update({ '/waiting': !store.get('/result') && !store.get('/busy') && !store.get('/error') && Boolean(store.get('/hasSources')) })
    const start = () => store.update({ '/busy': true, '/error': null, '/notice': null, '/clarifications': null, '/result': null, '/waiting': false })
    const finish = () => { store.update({ '/busy': false }); settle() }
    const suggest = async () => {
      start()
      try {
        const proposed = await client.proposeAnalysis(store.get('/source') as string, store.get('/question') as string)
        store.update({ '/planText': JSON.stringify(proposed.plan, null, 2), '/notice': 'Proposta recebida com todos os campos. Revise o plano e calcule.' })
      } catch (e) {
        const questions = e instanceof ApiError && e.status === 422 && typeof e.body === 'object' && e.body !== null && 'questions' in e.body && Array.isArray(e.body.questions) ? e.body.questions as string[] : null
        store.update(questions ? { '/clarifications': questions.join(' · ') + ' — edite o plano JSON e calcule de novo.' }
          : { '/error': e instanceof Error ? e.message : 'Falha ao propor análise.' })
      } finally { finish() }
    }
    const calculate = async () => {
      start()
      try {
        const plan = JSON.parse(store.get('/planText') as string) as AnalysisPlan
        const question = (store.get('/question') as string) || 'Análise definida pelo plano revisado'
        store.update({ '/result': await client.runAnalysis(store.get('/source') as string, question, plan) })
      } catch (e) {
        store.update({ '/error': e instanceof Error ? e.message : 'O plano está malformado ou a análise não pôde ser calculada.' })
      } finally { finish() }
    }
    const clearResult = () => { store.update({ '/result': null }); settle() }
    return { suggest, calculate, clearResult, settle, finish }
  }, [client, store])

  useEffect(() => {
    client.getSources().then(({ sources }) => store.update({
      '/sourceOptions': sources.map((s) => ({ value: s.name, label: `${s.name} · ${s.kind}` })),
      '/source': sources[0]?.name ?? '', '/hasSources': sources.length > 0, '/noSources': sources.length === 0,
    })).catch((e: Error) => store.update({ '/error': e.message })).finally(handlers.settle)
    if (runId) client.getAnalysisRun(runId).then((result) => store.update({ '/result': result }))
      .catch((e: Error) => store.update({ '/error': e.message })).finally(handlers.finish)
  }, [client, store, runId, handlers])

  return <SpecView spec={spec as Spec} store={store} handlers={handlers} />
}
