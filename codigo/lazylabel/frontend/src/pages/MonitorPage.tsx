import { useEffect, useMemo } from 'react'
import { useLazyLabelClient } from '@/application/LazyLabelClientContext'
import { SpecView } from '@/ui/SpecView'
import { usePageStore, type Spec } from '@/ui/store'
import spec from '@/specs/monitor.json'

export default function MonitorPage() {
  const client = useLazyLabelClient()
  const store = usePageStore({ source: '', sourceOptions: [], hasSources: false, noSources: false, busy: false, error: null, checked: false, clean: false, findings: [], resultSummary: '' })

  const refresh = useMemo(() => async () => {
    const source = store.get('/source') as string
    if (!source) return
    store.update({ '/busy': true, '/error': null, '/checked': false })
    try {
      const { findings } = await client.getFindings(source)
      store.update({
        '/checked': true,
        '/clean': findings.length === 0,
        '/resultSummary': `Fonte ${source}: ${findings.length} achado(s).`,
        '/findings': findings.map((f, i) => ({
          id: `${f.code}-${f.column}-${i}`,
          type: f.severity === 'error' ? 'error' : 'warning',
          title: `${f.severity === 'error' ? 'Erro' : 'Aviso'}: ${f.message}`,
          detail: `${f.code}${f.column ? ` · coluna ${f.column}` : ''} · esperado ${f.expected ?? '—'} · observado ${f.observed ?? '—'}`,
        })),
      })
    } catch (cause) {
      store.update({ '/error': cause instanceof Error ? cause.message : 'Falha ao consultar o monitor.' })
    } finally {
      store.update({ '/busy': false })
    }
  }, [client, store])

  useEffect(() => {
    client.getSources().then(({ sources }) => {
      store.update({ '/sourceOptions': sources.map((s) => ({ value: s.name, label: `${s.name} · ${s.kind}` })), '/hasSources': sources.length > 0, '/noSources': sources.length === 0, '/source': sources[0]?.name ?? '' })
      void refresh()
    }).catch((cause: Error) => store.update({ '/error': cause.message }))
  }, [client, store, refresh])

  return <SpecView spec={spec as Spec} store={store} handlers={{ refresh }} />
}
