import { useEffect, useMemo, useState } from 'react'
import { createStateStore, type StateStore } from '@json-render/core'
import type { AnalysisPlan } from '@/application/ports/LazyLabelClient'
import { clarificationQuestions } from '@/application/clarifications'
import { useLazyLabelClient } from '@/application/LazyLabelClientContext'
import { SpecView } from '@/ui/SpecView'
import { loadSourceOptions, usePageStore, type Spec } from '@/ui/store'
import { parseGeneratedSpec } from '@/ui/aiCatalog'
import spec from '@/specs/ask.json'

const MAX_ROWS = 100
const message = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback

export default function AskPage() {
  const client = useLazyLabelClient()
  const store = usePageStore({ source: '', sourceOptions: [], hasSources: false, noSources: false, question: '', planText: '',
    planReady: false, busy: false, progress: null, clarifications: null, error: null })
  const [generated, setGenerated] = useState<{ spec: Spec; store: StateStore; runId: string } | null>(null)

  const handlers = useMemo(() => {
    const start = (progress: string) => store.update({ '/busy': true, '/error': null, '/clarifications': null, '/progress': progress })
    const fail = (cause: unknown, fallback: string) => {
      const questions = clarificationQuestions(cause)
      store.update(questions ? { '/clarifications': questions.join(' · ') } : { '/error': message(cause, fallback) })
    }
    return {
      reset: () => { setGenerated(null); store.update({ '/planReady': false }) },
      // Step 1: the model only proposes; nothing is computed until the user confirms the plan.
      propose: async () => {
        const question = (store.get('/question') as string).trim()
        if (!question) { store.update({ '/error': 'Escreva uma pergunta.' }); return }
        setGenerated(null)
        start('Planejando a análise…')
        store.update({ '/planReady': false })
        try {
          const { plan } = await client.proposeAnalysis(store.get('/source') as string, question)
          store.update({ '/planText': JSON.stringify(plan, null, 2), '/planReady': true })
        } catch (cause) { fail(cause, 'Falha ao propor o plano.') }
        finally { store.update({ '/busy': false, '/progress': null }) }
      },
      // Step 2: compute the reviewed plan exactly, then let the model lay out those rows.
      confirm: async () => {
        const source = store.get('/source') as string, question = (store.get('/question') as string).trim()
        setGenerated(null)
        start('Calculando os valores exatos…')
        try {
          const plan = JSON.parse(store.get('/planText') as string) as AnalysisPlan
          const result = await client.runAnalysis(source, question, plan)
          const rows = result.rows.slice(0, MAX_ROWS)
          store.update({ '/progress': 'A IA está montando a tela…' })
          const prompt = [`PERGUNTA: ${question}`, `PLANO: ${JSON.stringify(result.plan)}`,
            `RESULT ROWS (${rows.length} de ${result.total_rows} grupos): ${JSON.stringify(rows)}`,
            result.highlights.length ? `OBSERVAÇÕES: ${result.highlights.join(' | ')}` : ''].filter(Boolean).join('\n')
          const { text } = await client.generateUi(prompt)
          const screen = parseGeneratedSpec(text, rows, [rows.length, result.total_rows, result.valid_row_count])
          setGenerated({ spec: screen, store: createStateStore((screen.state ?? {}) as Record<string, unknown>), runId: result.run_id })
        } catch (cause) { fail(cause, 'Falha ao gerar a tela.') }
        finally { store.update({ '/busy': false, '/progress': null }) }
      },
    }
  }, [client, store])

  useEffect(() => { loadSourceOptions(client, store).catch((e: Error) => store.update({ '/error': e.message })) }, [client, store])

  return <div className="space-y-6">
    <SpecView spec={spec as Spec} store={store} handlers={handlers} />
    {generated && <section aria-label="Tela gerada pela IA" className="space-y-3">
      <p className="text-xs text-muted-foreground">Layout gerado por IA a partir dos valores calculados. Confira os números exatos em <a className="underline" href={`/analysis/${generated.runId}`}>análise {generated.runId.slice(0, 8)}</a>.</p>
      <SpecView spec={generated.spec} store={generated.store} />
    </section>}
  </div>
}
