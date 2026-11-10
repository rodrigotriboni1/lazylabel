import { ApiError, type Health, type AutonomyOverview, type AutonomousRunResult, type SourceInfo, type Finding, type AnalysisPlan, type AnalysisResponse, type TrainingOverview, type TrainingQuality, type TrainingJob, type TrainingVersion, type EvaluationJob, type LazyLabelClient } from '@/application/ports/LazyLabelClient'

function csrfToken(): string | undefined {
  const item = document.cookie.split('; ').find((entry) => entry.startsWith('lazylabel_csrf='))
  return item ? decodeURIComponent(item.slice('lazylabel_csrf='.length)) : undefined
}

export class LazyLabelHttpClient implements LazyLabelClient {
getTrainingOverview() { return this.request<TrainingOverview>('/api/train/overview') }
checkTrainingDataset(dataset_name: string) {
  return this.postJson<TrainingQuality, { dataset_name: string }>('/api/train/check', { dataset_name })
}
splitTrainingDataset(body: {
  dataset_name: string; strategy: string; holdout_fraction: number; seed: number
  group_column?: string; time_column?: string
}) {
  return this.postJson<{ bundle_id: string; task_id: string; train_count: number; holdout_count: number
    strategy: string; holdout_fraction: number; seed: number; label_counts: Record<string, Record<string, number>>
    warnings: string[]; quality: TrainingQuality }, typeof body>('/api/train/split', body)
}
submitTraining(body: {
  bundle_id: string; model_id: string; confirmed: boolean; exploratory_confirmed: boolean
  revision?: string | null; epochs?: number; batch_size?: number; learning_rate?: number; lora_rank?: number; seed?: number
}) { return this.postJson<{ job_id: string; state: string; progress: string }, typeof body>('/api/train/submit', body) }
getTrainingJob(jobId: string) { return this.request<TrainingJob>(`/api/train/jobs/${encodeURIComponent(jobId)}`) }
getTrainingVersions() {
  return this.request<{ versions: TrainingVersion[]; active_version: string | null; active_diagnostic: string | null; registry_diagnostics: { version_id: string; error: string }[] }>('/api/train/versions')
}
evaluateTrainingCandidate(version_id: string) {
  return this.postJson<{ job_id: string; state: EvaluationJob['state']; progress: string }, { version_id: string; confirmed: true }>(
    '/api/train/evaluate', { version_id, confirmed: true })
}
getEvaluationJob(jobId: string) {
  return this.request<EvaluationJob>(`/api/train/evaluations/${encodeURIComponent(jobId)}`)
}
transitionTrainingVersion(body: { action: 'activate' | 'reject' | 'rollback' | 'recover'; version_id: string; confirmed: true; reason?: string }) {
  return this.postJson<{ version: TrainingVersion; active_version: string | null }, typeof body>('/api/train/transition', body)
}

getHealth(): Promise<Health> {
  return this.request<Health>('/api/health')
}

getAutonomyOverview(): Promise<AutonomyOverview> {
  return this.request('/api/autonomy/overview')
}

runAutonomousCycle(source: string, task: string, idempotencyKey: string): Promise<AutonomousRunResult> {
  return this.request('/api/autonomy/run', { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({ source, task }) })
}

getSources(): Promise<{ sources: SourceInfo[] }> {
  return this.request('/api/sources')
}

getFindings(source: string): Promise<{ findings: Finding[] }> {
  return this.request(`/api/monitor?source=${encodeURIComponent(source)}`)
}

generateUi(prompt: string) {
  return this.request<{ text: string }>('/api/ai/ui', { method: 'POST', body: JSON.stringify({ prompt }) })
}

proposeAnalysis(source: string, question: string) {
  return this.request<{ plan: AnalysisPlan; requires_confirmation: true }>('/api/plan', {
    method: 'POST', body: JSON.stringify({ source, question }),
  })
}

runAnalysis(source: string, question: string, plan: AnalysisPlan) {
  return this.request<AnalysisResponse>('/api/analyze', {
    method: 'POST', body: JSON.stringify({ source, question, plan }),
  })
}

getAnalysisRun(runId: string): Promise<AnalysisResponse> {
  return this.request(`/api/analyses/${encodeURIComponent(runId)}`)
}

private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (init.method && init.method.toUpperCase() !== 'GET') {
    const token = csrfToken()
    if (token) headers.set('X-CSRF-Token', token)
  }
  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const message = typeof body === 'object' && body !== null && 'error' in body && typeof body.error === 'string'
      ? body.error : `A solicitação falhou (${response.status}).`
    throw new ApiError(message, response.status, body)
  }
  return body as T
}

postJson<TResponse, TBody>(path: string, body: TBody): Promise<TResponse> {
  return this.request<TResponse>(path, { method: 'POST', body: JSON.stringify(body) })
}
}
