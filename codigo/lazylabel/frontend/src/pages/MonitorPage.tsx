import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleHelp, LoaderCircle, ShieldAlert } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { Finding, SourceInfo } from '@/application/ports/LazyLabelClient'
import { useLazyLabelClient } from '@/application/LazyLabelClientContext'

export default function MonitorPage() {
  const client = useLazyLabelClient()
  const [sources, setSources] = useState<SourceInfo[]>([])
  const [source, setSource] = useState('')
  const [findings, setFindings] = useState<Finding[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const refresh = useCallback(async (name: string) => {
    if (!name) return
    setBusy(true); setError(null); setFindings(null)
    try { setFindings((await client.getFindings(name)).findings) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Falha ao consultar o monitor.') }
    finally { setBusy(false) }
  }, [client])
  useEffect(() => { client.getSources().then(({ sources: items }) => { setSources(items); if (items[0]) { setSource(items[0].name); void refresh(items[0].name) } }).catch((e: Error) => setError(e.message)) }, [client, refresh])
  return <div className="space-y-6">
    <div><p className="mb-2 text-sm font-medium text-[#47805f]">LAZYLABEL / QUALIDADE</p><h1 className="text-3xl font-semibold tracking-tight">Monitoramento</h1><p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#718077]">Compara a estrutura atual com o esquema que foi confirmado para esta fonte. Os findings vêm da validação determinística local.</p></div>
    <Card className="border-[#e0e8e1] bg-white"><CardHeader><CardTitle className="text-lg">Esquema da fonte</CardTitle><CardDescription>Somente metadados estruturais; os valores dos registros não são exibidos.</CardDescription></CardHeader><CardContent className="flex flex-wrap items-end gap-3"><label className="grid min-w-[220px] flex-1 gap-1.5 text-sm font-medium">Fonte<select className="h-10 rounded-md border border-[#dce5de] bg-white px-3" value={source} onChange={(e) => { setSource(e.target.value); setFindings(null); void refresh(e.target.value) }}>{sources.map((item) => <option key={item.name} value={item.name}>{item.name} · {item.kind}</option>)}</select></label><Button variant="outline" disabled={!source || busy} onClick={() => void refresh(source)}>{busy ? <LoaderCircle className="animate-spin" size={15}/> : 'Atualizar'}</Button></CardContent></Card>
    {error && <Card className="border-[#eadbb4] bg-[#fffaf0]"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><CircleHelp size={18}/>Monitor indisponível</CardTitle><CardDescription>{error}</CardDescription></CardHeader><CardContent><p className="text-sm text-[#665a32]">Confirme o esquema local da fonte antes de usar o monitoramento. A ausência de um esquema não significa que a fonte está íntegra.</p></CardContent></Card>}
    {busy && <div className="flex items-center gap-2 rounded-lg border border-[#e0e8e1] bg-white p-5 text-sm text-[#718077]"><LoaderCircle className="animate-spin" size={16}/>Consultando esquema e estrutura…</div>}
    {findings && <Card className="border-[#e0e8e1] bg-white"><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle className="text-lg">Resultado da verificação</CardTitle><CardDescription>Fonte: {source}. Achados esperados e observados são os retornados pelo monitor.</CardDescription></div><Badge variant={findings.length ? 'outline' : 'secondary'} className={findings.length ? 'border-[#eadbb4] bg-[#fffaf0] text-[#765d25]' : 'bg-[#edf6ef] text-[#26764c]'}>{findings.length} achados</Badge></div></CardHeader><CardContent>
      {findings.length === 0 ? <div className="flex items-start gap-3 rounded-xl bg-[#edf6ef] p-5"><CheckCircle2 className="mt-0.5 text-[#25845a]" size={20}/><div><p className="font-semibold text-[#276a46]">Nenhuma divergência estrutural encontrada</p><p className="mt-1 text-sm text-[#597364]">A estrutura observada atende às verificações configuradas no esquema confirmado. Isso não valida o conteúdo semântico dos registros.</p></div></div> : <div className="space-y-3">{findings.map((finding, i) => <article key={`${finding.code}-${finding.column}-${i}`} className={`rounded-lg border p-4 ${finding.severity === 'error' ? 'border-[#f0d5d1] bg-[#fff7f5]' : 'border-[#eadbb4] bg-[#fffaf0]'}`}><div className="flex flex-wrap items-start justify-between gap-2"><div className="flex items-start gap-2"><span className={finding.severity === 'error' ? 'text-[#a23e36]' : 'text-[#85651e]'}>{finding.severity === 'error' ? <ShieldAlert size={18}/> : <AlertTriangle size={18}/>}</span><div><p className="font-medium">{finding.message}</p><p className="mt-1 text-xs text-[#77837a]">{finding.code}{finding.column ? ` · coluna ${finding.column}` : ''}</p></div></div><Badge variant="outline" className={finding.severity === 'error' ? 'border-[#e8beba] text-[#9b3c35]' : 'border-[#eadbb4] text-[#765d25]'}>{finding.severity === 'error' ? 'Erro' : 'Aviso'}</Badge></div><div className="mt-3 grid gap-2 text-xs sm:grid-cols-2"><div className="rounded-md bg-white/70 p-2"><span className="text-[#87938a]">Esperado</span><p className="mt-0.5 font-medium">{finding.expected ?? '—'}</p></div><div className="rounded-md bg-white/70 p-2"><span className="text-[#87938a]">Observado</span><p className="mt-0.5 font-medium">{finding.observed ?? '—'}</p></div></div></article>)}</div>}
    </CardContent></Card>}
    {!busy && !error && sources.length === 0 && <p className="rounded-lg border border-dashed border-[#d7e1d8] p-5 text-sm text-[#718077]">Nenhuma fonte local configurada para monitorar.</p>}
  </div>
}
