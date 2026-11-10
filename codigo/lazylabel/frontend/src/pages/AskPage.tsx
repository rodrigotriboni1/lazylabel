import { useEffect, useMemo, useState } from 'react'
import { createStateStore, type StateStore } from '@json-render/core'
import { useLazyLabelClient } from '@/application/LazyLabelClientContext'
import { SpecView } from '@/ui/SpecView'
import { usePageStore, type Spec } from '@/ui/store'
import { aiSystemPrompt, parseGeneratedSpec } from '@/ui/aiCatalog'
import spec from '@/specs/ask.json'

const MAX_ROWS = 100

export default function AskPage() {
  const client = useLazyLabelClient()
  const store = usePageStore({ source: '', sourceOptions: [], hasSources: false, noSources: false, question: '', busy: false, progress: null, error: null })
  const [generated, setGenerated] = useState<{ spec: Spec; store: StateStore; runId: string } | null>(null)

  const handlers = useMemo(() => ({
    ask: async () => {
      const source = store.get('/source') as string, question = (store.get('/question') as string).trim()
      if (!source || !question) return
      setGenerated(null)
      store.update({ '/busy': true, '/error': null, '/progress': 'Planejando a análise…' })
      try {
        const { plan } = await client.proposeAnalysis(source, question)
        store.update({ '/progress': 'Calculando os valores exatos…' })
        const result = await client.runAnalysis(source, question, plan)
        store.update({ '/progress': 'A IA está montando a tela…' })
        const prompt = [`PERGUNTA: ${question}`, `PLANO: ${JSON.stringify(result.plan)}`,
          `RESULT ROWS (${Math.min(result.rows.length, MAX_ROWS)} de ${result.total_rows}): ${JSON.stringify(result.rows.slice(0, MAX_ROWS))}`,
          result.highlights.length ? `OBSERVAÇÕES: ${result.highlights.join(' | ')}` : ''].filter(Boolean).join('\n')
        const { text } = await client.generateUi(aiSystemPrompt, prompt)
        const screen = parseGeneratedSpec(text)
        setGenerated({ spec: screen, store: createStateStore((screen.state ?? {}) as Record<string, unknown>), runId: result.run_id })
        store.update({ '/progress': null })
      } catch (cause) {
        store.update({ '/progress': null, '/error': cause instanceof Error ? cause.message : 'Falha ao gerar a tela.' })
      } finally {
        store.update({ '/busy': false })
      }
    },
  }), [client, store])

  useEffect(() => {
    client.getSources().then(({ sources }) => store.update({
      '/sourceOptions': sources.map((s) => ({ value: s.name, label: `${s.name} · ${s.kind}` })),
      '/source': sources[0]?.name ?? '', '/hasSources': sources.length > 0, '/noSources': sources.length === 0,
    })).catch((e: Error) => store.update({ '/error': e.message }))
  }, [client, store])

  return <div className="space-y-6">
    <SpecView spec={spec as Spec} store={store} handlers={handlers} />
    {generated && <section aria-label="Tela gerada pela IA" className="space-y-3">
      <p className="text-xs text-muted-foreground">Layout gerado por IA a partir dos valores calculados. Confira os números exatos em <a className="underline" href={`/analysis/${generated.runId}`}>análise {generated.runId.slice(0, 8)}</a>.</p>
      <SpecView spec={generated.spec} store={generated.store} />
    </section>}
  </div>
}
