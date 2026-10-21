import { useEffect, useState } from 'react'
import { Activity, BarChart3, CircleHelp, Database, FlaskConical, LayoutDashboard, ListChecks, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getHealth, type Health } from '@/lib/api'
import OverviewPage from '@/pages/OverviewPage'
import AnalysisPage from '@/pages/AnalysisPage'
import MonitorPage from '@/pages/MonitorPage'
import LabelingPage from '@/pages/LabelingPage'
import ReviewPage from '@/pages/ReviewPage'

const navigation = [
  { label: 'Visão geral', mobileLabel: 'Início', path: '/', icon: LayoutDashboard },
  { label: 'Análises', mobileLabel: 'Análises', path: '/analysis', icon: BarChart3 },
  { label: 'Monitoramento', mobileLabel: 'Monitor', path: '/monitor', icon: Activity },
  { label: 'Rotulagem', mobileLabel: 'Rótulos', path: '/labeling', icon: ListChecks },
  { label: 'Treinamento', mobileLabel: 'Treino', path: '/training', icon: FlaskConical },
]

function pageName(path: string) {
  if (path === '/review') return 'Revisão humana'
  return navigation.find((item) => item.path === path)?.label ?? 'Visão geral'
}

export default function App() {
  const path = window.location.pathname
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getHealth().then(setHealth).catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : 'Não foi possível consultar o painel local.')
    })
  }, [])

  return (
    <div className="min-h-screen bg-[#f5f7f4] text-[#16251f]">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-[#e0e7e1] bg-white px-5 py-6 md:flex md:flex-col">
        <a className="flex items-center gap-3 rounded-xl px-2 py-1" href="/" aria-label="FinLabel, visão geral">
          <span className="grid size-10 place-items-center rounded-xl bg-[#dff1e5] text-[#16734a]"><Database size={20} /></span>
          <span><span className="block text-lg font-semibold tracking-tight">FinLabel</span><span className="block text-xs text-[#738178]">Painel local</span></span>
        </a>
        <p className="mb-3 mt-10 px-3 text-[11px] font-semibold uppercase tracking-[.14em] text-[#87938a]">Workspace</p>
        <nav aria-label="Navegação principal" className="space-y-1">
          {navigation.map(({ label, path: itemPath, icon: Icon }) => (
            <a key={itemPath} href={itemPath} aria-current={path === itemPath ? 'page' : undefined}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${path === itemPath ? 'bg-[#eaf5ed] font-semibold text-[#176c48]' : 'text-[#57645b] hover:bg-[#f3f6f3]'}`}>
              <Icon size={17} strokeWidth={1.8} />{label}
            </a>
          ))}
        </nav>
        <div className="mt-auto rounded-xl border border-[#e5ebe6] bg-[#fafcf9] p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium"><ShieldCheck size={16} className="text-[#25845a]" />Dados protegidos localmente</div>
          <p className="text-xs leading-relaxed text-[#77837a]">O painel conversa apenas com este servidor local.</p>
        </div>
      </aside>

      <main className="min-h-screen pb-20 md:ml-64 md:pb-0">
        <header className="flex min-h-16 items-center justify-between border-b border-[#e0e7e1] bg-white/90 px-5 md:px-10">
          <div className="flex items-center gap-3"><span className="grid size-8 place-items-center rounded-lg bg-[#eaf5ed] text-[#176c48] md:hidden"><Database size={17} /></span><span className="font-medium">{pageName(path)}</span></div>
          <Badge variant="outline" className="gap-2 border-[#dce8df] bg-[#f7fbf7] px-2.5 py-1 text-[#42604d]">
            <span className={`size-1.5 rounded-full ${health ? 'bg-[#299464]' : error ? 'bg-[#c74f46]' : 'animate-pulse bg-[#c28a25]'}`} />
            {health ? 'Servidor local ativo' : error ? 'Sem conexão' : 'Conectando'}
          </Badge>
        </header>

        <section className="mx-auto max-w-6xl px-5 py-8 md:px-10 md:py-12">
          {path === '/analysis' ? <AnalysisPage /> : path === '/monitor' ? <MonitorPage /> : path === '/labeling' ? <LabelingPage /> : path === '/review' ? <ReviewPage /> : <>
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div><p className="mb-2 text-sm font-medium text-[#47805f]">FINLABEL / LOCAL</p><h1 className="text-3xl font-semibold tracking-tight md:text-4xl">Seu espaço de trabalho</h1><p className="mt-2 max-w-xl text-sm leading-relaxed text-[#718077]">Análise, revisão humana e preparação de dados em um único ambiente privado.</p></div>
            <Button variant="outline" className="gap-2 border-[#dce5de] bg-white text-[#34493a]"><CircleHelp size={16} />Ajuda</Button>
          </div>

          {error ? <Card className="border-[#f0d5d1] bg-white"><CardHeader><CardTitle className="text-base">Não foi possível conectar</CardTitle><CardDescription>{error}</CardDescription></CardHeader><CardContent><Button variant="outline" onClick={() => window.location.reload()}>Tentar novamente</Button></CardContent></Card> : <OverviewPage />}
          </>}
        </section>
        <footer className="px-5 pb-8 text-center text-xs text-[#94a097] md:px-10">FinLabel · ambiente de processamento local</footer>
      </main>
      <nav aria-label="Navegação móvel" className="fixed inset-x-0 bottom-0 z-10 grid grid-cols-5 border-t border-[#e0e7e1] bg-white px-1 py-2 md:hidden">
        {navigation.map(({ mobileLabel, path: itemPath, icon: Icon }) => <a key={itemPath} href={itemPath} aria-current={path === itemPath ? 'page' : undefined} className={`flex min-w-0 flex-col items-center gap-1 py-1 text-[10px] leading-tight ${path === itemPath ? 'font-semibold text-[#176c48]' : 'text-[#718077]'}`}><Icon size={17} /><span className="whitespace-nowrap">{mobileLabel}</span></a>)}
      </nav>
    </div>
  )
}
