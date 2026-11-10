import { lazy, Suspense, useEffect, useState } from 'react'
import { Activity, BarChart3, MessageSquareText, Database, FlaskConical, LayoutDashboard, ListChecks, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { LazyLabelClient, Health } from '@/application/ports/LazyLabelClient'
import { LazyLabelClientProvider } from '@/application/LazyLabelClientProvider'
import { useLazyLabelClient } from '@/application/LazyLabelClientContext'

const OverviewPage = lazy(() => import('@/pages/OverviewPage'))
const AnalysisPage = lazy(() => import('@/pages/AnalysisPage'))
const MonitorPage = lazy(() => import('@/pages/MonitorPage'))
const LabelingPage = lazy(() => import('@/pages/LabelingPage'))
const TrainingPage = lazy(() => import('@/pages/TrainingPage'))
const AskPage = lazy(() => import('@/pages/AskPage'))

const navigation = [
  { label: 'Visão geral', mobileLabel: 'Início', path: '/', icon: LayoutDashboard },
  { label: 'Perguntar', mobileLabel: 'Perguntar', path: '/ask', icon: MessageSquareText },
  { label: 'Análises', mobileLabel: 'Análises', path: '/analysis', icon: BarChart3 },
  { label: 'Monitoramento', mobileLabel: 'Monitor', path: '/monitor', icon: Activity },
  { label: 'Rotulagem', mobileLabel: 'Rótulos', path: '/labeling', icon: ListChecks },
  { label: 'Treinamento', mobileLabel: 'Treino', path: '/training', icon: FlaskConical },
]

function pageName(path: string) {
  if (path.startsWith('/analysis/')) return 'Análise salva'
  if (path === '/review') return 'Histórico local'
  return navigation.find((item) => item.path === path)?.label ?? 'Visão geral'
}

export default function App({ client }: { client: LazyLabelClient }) {
  return <LazyLabelClientProvider client={client}><AppShell /></LazyLabelClientProvider>
}

function AppShell() {
  const client = useLazyLabelClient()
  const path = window.location.pathname
  const analysisRunId = /^\/analysis\/([0-9a-f]{32})$/.exec(path)?.[1]
  const activePath = analysisRunId ? '/analysis' : path
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    client.getHealth().then(setHealth).catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : 'Não foi possível consultar o painel local.')
    })
  }, [client])

  const status = health ? 'Servidor ativo' : error ? 'Sem conexão' : 'Conectando'
  return (
    <div className="min-h-screen bg-background text-foreground">
      <aside className="fixed inset-y-0 left-0 hidden w-60 border-r bg-sidebar px-4 py-6 md:flex md:flex-col">
        <a className="flex items-center gap-2.5 px-2" href="/" aria-label="LazyLabel, visão geral">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground"><Database size={16} /></span>
          <span className="text-base font-semibold tracking-tight">LazyLabel</span>
        </a>
        <nav aria-label="Navegação principal" className="mt-8 space-y-0.5">
          {navigation.map(({ label, path: itemPath, icon: Icon }) => (
            <a key={itemPath} href={itemPath} aria-current={activePath === itemPath ? 'page' : undefined}
              className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors ${activePath === itemPath ? 'bg-accent font-medium text-accent-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'}`}>
              <Icon size={16} strokeWidth={1.8} />{label}
            </a>
          ))}
        </nav>
        <p className="mt-auto flex items-center gap-2 px-2 text-xs text-muted-foreground"><ShieldCheck size={14} />Fontes abertas só para leitura</p>
      </aside>

      <main className="min-h-screen pb-20 md:ml-60 md:pb-0">
        <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b bg-background/80 px-5 backdrop-blur md:px-10">
          <span className="text-sm font-medium">{pageName(path)}</span>
          <Badge variant="outline" className="gap-2 font-normal">
            <span className={`size-1.5 rounded-full ${health ? 'bg-emerald-500' : error ? 'bg-destructive' : 'animate-pulse bg-amber-500'}`} />
            {health ? 'Servidor local ativo' : status}
          </Badge>
        </header>

        <section className="mx-auto max-w-6xl px-5 py-8 md:px-10 md:py-10">
          <Suspense fallback={<p role="status" className="text-sm text-muted-foreground">Carregando página…</p>}>
          {path === '/analysis' || analysisRunId ? <AnalysisPage runId={analysisRunId} /> : path === '/monitor' ? <MonitorPage /> : path === '/labeling' || path === '/review' ? <LabelingPage /> : path === '/training' ? <TrainingPage /> : path === '/ask' ? <AskPage /> : error ? <div role="alert" className="space-y-3 rounded-lg border border-destructive/30 p-5"><p className="font-medium">Não foi possível conectar</p><p className="text-sm text-muted-foreground">{error}</p><Button variant="outline" onClick={() => window.location.reload()}>Tentar novamente</Button></div> : <OverviewPage />}
          </Suspense>
        </section>
      </main>
      <nav aria-label="Navegação móvel" className="fixed inset-x-0 bottom-0 z-10 grid grid-cols-6 border-t bg-background px-1 py-2 md:hidden">
        {navigation.map(({ mobileLabel, path: itemPath, icon: Icon }) => <a key={itemPath} href={itemPath} aria-current={activePath === itemPath ? 'page' : undefined} className={`flex min-w-0 flex-col items-center gap-1 py-1 text-[11px] leading-tight ${activePath === itemPath ? 'font-medium text-foreground' : 'text-muted-foreground'}`}><Icon size={17} /><span className="whitespace-nowrap">{mobileLabel}</span></a>)}
      </nav>
    </div>
  )
}
