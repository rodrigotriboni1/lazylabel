import { useEffect, useState } from 'react'
import { ArrowRight, FileText, Play, RefreshCw } from 'lucide-react'
import { ApiError, getLabelTasks, startLabelRun, type LabelTask } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function LabelingPage() {
  const [tasks, setTasks] = useState<LabelTask[]>([])
  const [sources, setSources] = useState<string[]>([])
  const [taskId, setTaskId] = useState('')
  const [source, setSource] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const selected = tasks.find((task) => task.task_id === taskId)

  async function refresh() {
    setError(null)
    try {
      const response = await getLabelTasks()
      setTasks(response.tasks); setSources(response.sources)
      setTaskId((current) => response.tasks.some((task) => task.task_id === current) ? current : response.tasks[0]?.task_id ?? '')
      setSource((current) => response.sources.includes(current) ? current : response.sources[0] ?? '')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível carregar as tarefas.') }
  }
  useEffect(() => { void refresh() }, [])

  async function run() {
    if (!source || !selected) return
    setBusy(true); setError(null); setNotice(null)
    try {
      const result = await startLabelRun(source, selected.task_id)
      window.location.href = `/review?run_id=${encodeURIComponent(result.run_id)}&invalid=${result.invalid}&suggestions=${result.suggestions}`
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'A execução local falhou.'
      setError(message)
      if (cause instanceof ApiError && cause.status === 400 && /backend|model|configur/i.test(message)) {
        setNotice('Configure um modelo local para esta tarefa e tente novamente. Nenhuma sugestão foi simulada.')
      }
    } finally { setBusy(false) }
  }

  return <div className="space-y-7">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 text-sm font-medium text-[#47805f]">ROTULAGEM / LOCAL</p><h1 className="text-3xl font-semibold tracking-tight">Sugestões para revisão</h1><p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#718077]">Escolha uma tarefa e uma fonte. O modelo configurado roda localmente; cada decisão humana fica registrada no histórico do projeto.</p></div><Button variant="outline" className="gap-2" onClick={() => void refresh()}><RefreshCw size={15}/>Atualizar</Button></div>
    {error && <div role="alert" className="rounded-lg border border-[#f0d5d1] bg-white p-4 text-sm text-[#963f35]">{error}{notice && <p className="mt-2 text-[#6f514c]">{notice}</p>}</div>}
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(280px,.9fr)]">
      <Card className="border-[#e1e8e2] shadow-sm"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><FileText size={17} className="text-[#32845b]"/>Configurar execução</CardTitle><CardDescription>Use uma tarefa existente com campos e rótulos definidos.</CardDescription></CardHeader><CardContent className="space-y-5">
        <label className="block text-sm font-medium">Tarefa<select className="mt-2 w-full rounded-md border border-[#dce5de] bg-white px-3 py-2.5 text-sm" value={taskId} onChange={(event) => setTaskId(event.target.value)}><option value="">Selecione uma tarefa</option>{tasks.map((task) => <option key={task.task_id} value={task.task_id}>{task.task_id}</option>)}</select></label>
        <label className="block text-sm font-medium">Fonte somente leitura<select className="mt-2 w-full rounded-md border border-[#dce5de] bg-white px-3 py-2.5 text-sm" value={source} onChange={(event) => setSource(event.target.value)}><option value="">Selecione uma fonte</option>{sources.map((name) => <option key={name}>{name}</option>)}</select></label>
        {selected ? <div className="space-y-4 rounded-lg bg-[#f7faf7] p-4"><div><p className="text-xs font-medium uppercase tracking-wide text-[#77837a]">Instruções</p><p className="mt-1 text-sm leading-relaxed">{selected.instructions}</p></div><div><p className="mb-2 text-xs font-medium uppercase tracking-wide text-[#77837a]">Campos selecionados</p><div className="flex flex-wrap gap-2">{selected.input_columns.map((field) => <Badge key={field} variant="outline" className="bg-white">{field}</Badge>)}</div></div><div><p className="mb-2 text-xs font-medium uppercase tracking-wide text-[#77837a]">Rótulos permitidos</p><div className="flex flex-wrap gap-2">{selected.labels.map((label) => <Badge key={label} className="bg-[#e7f3e9] text-[#286444] hover:bg-[#e7f3e9]">{label}</Badge>)}</div></div><p className="text-xs text-[#718077]">Modelo local: <span className="font-medium text-[#39483d]">{selected.model_ref}</span></p></div> : <p className="rounded-lg border border-dashed p-4 text-sm text-[#718077]">{tasks.length ? 'Selecione uma tarefa para revisar sua configuração.' : 'Nenhuma tarefa configurada. Crie uma tarefa pelo CLI para continuar.'}</p>}
        <Button disabled={busy || !source || !selected} onClick={() => void run()} className="gap-2 bg-[#176c48] hover:bg-[#11583a]">{busy ? 'Executando localmente…' : 'Gerar sugestões'}<Play size={15}/></Button>
      </CardContent></Card>
      <Card className="border-[#e1e8e2] shadow-sm"><CardHeader><CardTitle className="text-base">Como funciona a revisão</CardTitle><CardDescription>As sugestões são propostas do modelo. Só uma decisão humana aceita ou corrige um rótulo.</CardDescription></CardHeader><CardContent><ol className="space-y-4">{[['01','Executar','Uma cópia somente leitura da fonte fornece os campos selecionados ao modelo local.'],['02','Inspecionar','A lista oculta valores; abra um item para ver somente os campos definidos na tarefa.'],['03','Decidir','Aceite, edite, rejeite ou pule. A decisão confirmada vem do servidor.']].map(([number,title,body]) => <li className="flex gap-3" key={number}><span className="grid size-8 shrink-0 place-items-center rounded-full bg-[#eaf5ed] text-xs font-semibold text-[#176c48]">{number}</span><div><p className="text-sm font-medium">{title}</p><p className="mt-1 text-xs leading-relaxed text-[#718077]">{body}</p></div></li>)}</ol><div className="mt-6 flex items-center gap-2 border-t border-[#edf1ed] pt-4 text-xs text-[#718077]"><ArrowRight size={14}/>Fontes originais não são alteradas.</div></CardContent></Card>
    </div>
  </div>
}
