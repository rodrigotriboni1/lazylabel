import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, Eye, RefreshCw } from 'lucide-react'
import { ApiError, getLabelSuggestionDetail, getLabelSuggestions, submitLabelReview, type LabelRunSuggestions, type LabelSuggestion, type ReviewAction } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

function actionKey(runId: string, item: LabelSuggestion, action: ReviewAction) {
  const bytes = new TextEncoder().encode(`${runId}:${item.suggestion_id}:${action}`)
  return crypto.subtle.digest('SHA-256', bytes).then((digest) =>
    Array.from(new Uint8Array(digest).slice(0, 16), (byte) => byte.toString(16).padStart(2, '0')).join(''))
}

const statusText: Record<string, string> = { accepted: 'Aceita', corrected: 'Corrigida', rejected: 'Rejeitada', skipped: 'Pulada' }

export default function ReviewPage() {
  const params = new URLSearchParams(window.location.search)
  const runId = params.get('run_id') ?? ''
  const invalid = Number(params.get('invalid') ?? 0)
  const [data, setData] = useState<LabelRunSuggestions | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, unknown> | null>(null)
  const [detailStale, setDetailStale] = useState(false)
  const [editLabels, setEditLabels] = useState<Record<string, string>>({})

  const refresh = useCallback(async () => {
    if (!runId) return
    setError(null)
    try { setData(await getLabelSuggestions(runId)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível atualizar a revisão.') }
  }, [runId])
  useEffect(() => { void refresh() }, [refresh])

  async function showDetail(item: LabelSuggestion) {
    setDetailId(item.suggestion_id); setFields(null); setDetailStale(item.stale); setError(null)
    try {
      const detail = await getLabelSuggestionDetail(runId, item.suggestion_id)
      setFields(detail.fields); setDetailStale(detail.stale)
      if (detail.stale !== item.stale) await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível abrir o detalhe.') }
  }

  async function decide(item: LabelSuggestion, action: ReviewAction) {
    if (item.stale || item.review_action || busy) return
    setBusy(item.suggestion_id); setError(null); setMessage(null)
    try {
      const idempotency_key = await actionKey(runId, item, action)
      await submitLabelReview({
        run_id: runId, suggestion_id: item.suggestion_id, record_id: item.record_id,
        input_digest: item.input_digest, idempotency_key, action,
        ...(action === 'corrected' ? { final_label: editLabels[item.suggestion_id] } : {}),
      })
      await refresh()
      setMessage('Estado atualizado a partir do servidor.')
    } catch (cause) {
      // A response can be lost after append. Refresh to discover whether the idempotent action committed.
      await refresh()
      if (cause instanceof ApiError && cause.status === 409) setError(`${cause.message} A lista foi atualizada; itens stale não podem ser revisados.`)
      else setError(`${cause instanceof Error ? cause.message : 'A solicitação falhou.'} Estado consultado novamente; você pode tentar outra vez com a mesma chave de ação.`)
    } finally { setBusy(null) }
  }

  const reviewed = data?.suggestions.filter((item) => item.review_action).length ?? 0

  return <div className="space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><a href="/labeling" className="mb-3 inline-flex items-center gap-1 text-xs font-medium text-[#508064] hover:underline"><ArrowLeft size={14}/>Voltar às tarefas</a><p className="mb-2 text-sm font-medium text-[#47805f]">REVISÃO HUMANA / LOCAL</p><h1 className="text-3xl font-semibold tracking-tight">Revisar sugestões</h1><p className="mt-2 text-sm text-[#718077]">Run <span className="font-mono">{runId || 'não informado'}</span> · decisões são gravadas no histórico local.</p></div><Button variant="outline" className="gap-2" onClick={() => void refresh()}><RefreshCw size={15}/>Atualizar do servidor</Button></div>
    {error && <div role="alert" className="rounded-lg border border-[#f0d5d1] bg-white p-4 text-sm text-[#963f35]">{error}</div>}{message && <div role="status" className="rounded-lg border border-[#d7e8db] bg-[#f4faf5] p-3 text-sm text-[#286444]">{message}</div>}
    {!runId ? <p className="rounded-lg border border-dashed p-5 text-sm text-[#718077]">Informe um run gerado pela página de rotulagem para consultar sugestões.</p> : <>
      <div className="grid gap-3 sm:grid-cols-3"><Card className="border-[#e1e8e2]"><CardContent className="p-4"><p className="text-xs text-[#718077]">Sugestões válidas</p><p className="mt-1 text-2xl font-semibold">{data?.total ?? '—'}</p></CardContent></Card><Card className="border-[#e1e8e2]"><CardContent className="p-4"><p className="text-xs text-[#718077]">Saídas inválidas</p><p className="mt-1 text-2xl font-semibold text-[#986b25]">{invalid || 0}</p></CardContent></Card><Card className="border-[#e1e8e2]"><CardContent className="p-4"><p className="text-xs text-[#718077]">Decisões registradas</p><p className="mt-1 text-2xl font-semibold">{data ? `${reviewed} / ${data.total}` : '—'}</p></CardContent></Card></div>
      <Card className="border-[#e1e8e2] shadow-sm"><CardHeader><CardTitle className="text-base">Fila de revisão</CardTitle><CardDescription>Valores dos registros não aparecem nesta lista. Abra “Ver campos” para inspecionar apenas os campos selecionados pela tarefa.</CardDescription></CardHeader><CardContent className="space-y-3">
        {!data && !error && <p className="text-sm text-[#718077]">Carregando sugestões…</p>}{data?.suggestions.map((item) => <article key={item.suggestion_id} className={`rounded-xl border p-4 ${item.stale ? 'border-[#edc9c4] bg-[#fff9f8]' : 'border-[#e6ece7] bg-white'}`}>
          <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">Sugestão <span className="font-mono text-xs">{item.suggestion_id.slice(0, 8)}</span></span>{item.stale ? <Badge className="bg-[#f8e3df] text-[#963f35] hover:bg-[#f8e3df]">Stale</Badge> : item.review_action ? <Badge variant="outline">{statusText[item.review_action] ?? item.review_action}</Badge> : <Badge className="bg-[#eef2ed] text-[#536257] hover:bg-[#eef2ed]">Pendente</Badge>}</div><p className="mt-2 text-sm">Rótulo sugerido: <strong>{item.suggested_label}</strong></p>{item.final_label && <p className="mt-1 text-sm text-[#286444]">Rótulo final humano: <strong>{item.final_label}</strong></p>}{item.rationale && <p className="mt-1 max-w-3xl text-xs leading-relaxed text-[#718077]">Justificativa do modelo: {item.rationale}</p>}<p className="mt-2 font-mono text-[10px] text-[#89958c]">registro {item.record_id.slice(0, 18)} · digest {item.input_digest.slice(0, 12)}</p></div><Button size="sm" variant="outline" className="gap-2" onClick={() => void showDetail(item)}><Eye size={14}/>Ver campos</Button></div>
          {detailId === item.suggestion_id && <div className={`mt-4 rounded-lg p-3 ${detailStale ? 'bg-[#fff0ed]' : 'bg-[#f6faf6]'}`}><p className="mb-2 text-xs font-semibold">Detalhe selecionado {detailStale && <span className="text-[#963f35]">· digest stale, revisão bloqueada</span>}</p>{fields ? <dl className="grid gap-2 sm:grid-cols-2">{Object.entries(fields).map(([key,value]) => <div key={key} className="min-w-0 rounded-md bg-white p-2"><dt className="text-[11px] text-[#718077]">{key}</dt><dd className="mt-1 break-words text-sm">{String(value ?? '—')}</dd></div>)}</dl> : <p className="text-xs text-[#718077]">Carregando campos selecionados…</p>}</div>}
          {!item.stale && !item.review_action && <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-[#edf1ed] pt-3"><Button size="sm" disabled={busy !== null} onClick={() => void decide(item, 'accepted')}>Aceitar</Button><label className="text-xs text-[#718077]">Corrigir para<select className="ml-2 rounded-md border border-[#dce5de] bg-white px-2 py-1.5 text-xs" value={editLabels[item.suggestion_id] ?? ''} onChange={(event) => setEditLabels((current) => ({...current,[item.suggestion_id]:event.target.value}))}><option value="">Escolha um rótulo</option>{item.labels.map((label) => <option key={label}>{label}</option>)}</select></label><Button size="sm" variant="outline" disabled={busy !== null || !editLabels[item.suggestion_id] || editLabels[item.suggestion_id] === item.suggested_label} onClick={() => void decide(item, 'corrected')}>Salvar correção</Button><Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void decide(item, 'rejected')}>Rejeitar</Button><Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => void decide(item, 'skipped')}>Pular</Button>{busy === item.suggestion_id && <span className="text-xs text-[#718077]">Salvando e consultando o servidor…</span>}</div>}
        </article>)}{data?.suggestions.length === 0 && <p className="rounded-lg border border-dashed p-5 text-sm text-[#718077]">Nenhuma sugestão válida nesta execução. Saídas inválidas: {invalid || 0}.</p>}{data?.truncated && <p className="text-xs text-[#718077]">Exibindo os primeiros itens permitidos pelo painel. Use a CLI para consultar ou revisar o restante.</p>}</CardContent></Card>
    </>}
  </div>
}
