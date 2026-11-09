import { useEffect } from 'react'
import { useLazyLabelClient } from '@/application/LazyLabelClientContext'
import { SpecView, usePageStore, type Spec } from '@/ui/SpecView'
import spec from '@/specs/overview.json'

export default function OverviewPage() {
  const client = useLazyLabelClient()
  const store = usePageStore({ status: 'loading', error: null, empty: false, sources: [] })
  useEffect(() => {
    client.getSources().then(({ sources }) => store.update({
      '/status': 'ready',
      '/empty': sources.length === 0,
      '/sources': sources.map((source) => ({
        name: source.name,
        kind: source.kind,
        summary: [`${source.columns.length} campos`, ...source.columns.map((c) => `${c.name} (${c.mapped_type ?? c.inferred_type})`)].join(' · '),
      })),
    })).catch((cause: Error) => store.update({ '/status': 'error', '/error': cause.message }))
  }, [client, store])
  return <SpecView spec={spec as Spec} store={store} handlers={{ reload: () => window.location.reload() }} />
}
