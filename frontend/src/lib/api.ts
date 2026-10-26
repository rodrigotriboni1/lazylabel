export interface Health {
  status: 'ok'
  project: string
  sources: number
}

export interface SourceColumn {
  name: string
  inferred_type: string
  mapped_type: string | null
  missing_count: number
  non_missing_count: number
}

export interface SourceInfo {
  name: string
  kind: string
  columns: SourceColumn[]
}

export interface LabelTask {
  task_id: string
  instructions: string
  input_columns: string[]
  labels: string[]
  model_ref: string
  min_examples_per_label: Record<string, number>
}

export interface TrainingGate { authorized: boolean; missing: string[]; model_id: string | null }
export interface TrainingDataset { name: string; rows: number | null; task_id: string | null; source: string | null; sha256: string | null }
export interface TrainingTask { task_id: string; labels: string[]; model_ref: string }
export interface TrainingQuality {
  total: number; label_counts: Record<string, number>; duplicate_suggestion_ids: number
  duplicate_event_ids: number; duplicate_examples: number; excluded_counts: Record<string, number>
  source_snapshot_matches: boolean; warnings: string[]; blockers: string[]; ready: boolean
}
export interface TrainingVersion {
  version_id: string; base_model_ref: string; dataset_sha256: string; split_sha256: string
  created_at: string | null; state: string; has_evaluation: boolean; is_active: boolean
  integrity_valid: boolean; integrity_error: string | null
  evaluation?: TrainingEvaluation
}
export interface TrainingEvaluation {
  overall: Record<string, Record<string, number | null>>
  per_label: { label: string; model: string; support: number; precision: number | null; recall: number | null; f1: number | null }[]
  confusion: Record<string, Record<string, Record<string, number>>>
  error_count: number; warnings: string[]
}
export interface TrainingOverview {
  datasets: TrainingDataset[]; tasks: TrainingTask[]; gate: TrainingGate
  active_version: string | null; active_diagnostic: string | null; registry_diagnostics: { version_id: string; error: string }[]
  versions: TrainingVersion[]; jobs: TrainingJob[]; evaluation_jobs: EvaluationJob[]
}
export interface TrainingJob {
  job_id: string; state: 'queued' | 'running' | 'succeeded' | 'failed'; progress: string
  error: string | null; model_id: string; dataset_sha256: string; final_metrics: Record<string, number>
  bundle_id: string | null; version_id: string | null; created_at?: string
}
export interface EvaluationJob {
  job_id: string; state: 'queued' | 'running' | 'succeeded' | 'failed'; progress: string
  error: string | null; version_id: string; created_at?: string
}

export function getTrainingOverview() { return request<TrainingOverview>('/api/train/overview') }
export function checkTrainingDataset(dataset_name: string) {
  return postJson<TrainingQuality, { dataset_name: string }>('/api/train/check', { dataset_name })
}
export function splitTrainingDataset(body: {
  dataset_name: string; strategy: string; holdout_fraction: number; seed: number
  group_column?: string; time_column?: string
}) {
  return postJson<{ bundle_id: string; task_id: string; train_count: number; holdout_count: number
    strategy: string; holdout_fraction: number; seed: number; label_counts: Record<string, Record<string, number>>
    warnings: string[]; quality: TrainingQuality }, typeof body>('/api/train/split', body)
}
export function submitTraining(body: {
  bundle_id: string; model_id: string; confirmed: boolean; exploratory_confirmed: boolean
  revision?: string | null; epochs?: number; batch_size?: number; learning_rate?: number; lora_rank?: number; seed?: number
}) { return postJson<{ job_id: string; state: string; progress: string }, typeof body>('/api/train/submit', body) }
export function getTrainingJob(jobId: string) { return request<TrainingJob>(`/api/train/jobs/${encodeURIComponent(jobId)}`) }
export function getTrainingVersions() {
  return request<{ versions: TrainingVersion[]; active_version: string | null; active_diagnostic: string | null; registry_diagnostics: { version_id: string; error: string }[] }>('/api/train/versions')
}
export function evaluateTrainingCandidate(version_id: string) {
  return postJson<{ job_id: string; state: EvaluationJob['state']; progress: string }, { version_id: string; confirmed: true }>(
    '/api/train/evaluate', { version_id, confirmed: true })
}
export function getEvaluationJob(jobId: string) {
  return request<EvaluationJob>(`/api/train/evaluations/${encodeURIComponent(jobId)}`)
}
export function transitionTrainingVersion(body: { action: 'activate' | 'reject' | 'rollback' | 'recover'; version_id: string; confirmed: true; reason?: string }) {
  return postJson<{ version: TrainingVersion; active_version: string | null }, typeof body>('/api/train/transition', body)
}

export interface LabelSuggestion {
  suggestion_id: string
  record_id: string
  input_digest: string
  suggested_label: string
  rationale: string | null
  labels: string[]
  stale: boolean
  review_action: 'accepted' | 'corrected' | 'rejected' | 'skipped' | null
  final_label: string | null
}

export interface LabelRunSuggestions {
  run_id: string
  task_id: string
  suggestions: LabelSuggestion[]
  total: number
  truncated: boolean
}

export function getLabelTasks() {
  return request<{ tasks: LabelTask[]; sources: string[] }>('/api/label/tasks')
}

export function startLabelRun(source: string, task: string) {
  return request<{ run_id: string; source: string; task: string; suggestions: number; invalid: number }>('/api/label/start', {
    method: 'POST', body: JSON.stringify({ source, task }),
  })
}

export function getLabelSuggestions(runId: string) {
  return request<LabelRunSuggestions>(`/api/label/suggestions?run_id=${encodeURIComponent(runId)}`)
}

export function getLabelSuggestionDetail(runId: string, suggestionId: string) {
  return request<{ fields: Record<string, unknown> | null; stale: boolean }>(`/api/label/suggestion?run_id=${encodeURIComponent(runId)}&suggestion_id=${encodeURIComponent(suggestionId)}`)
}

export type ReviewAction = 'accepted' | 'corrected' | 'rejected' | 'skipped'
export function submitLabelReview(body: {
  run_id: string; suggestion_id: string; record_id: string; input_digest: string
  idempotency_key: string; action: ReviewAction; final_label?: string
}) {
  return request<{ event_id: string; duplicate: boolean }>('/api/label/review', {
    method: 'POST', body: JSON.stringify(body),
  })
}

export interface AnalysisPlan {
  version: number
  metric: { operation: string; column?: string | null; denominator_scope?: string[] | null }
  dimensions: string[]
  time_axis?: { column: string; grain: string } | null
  filters: { column: string; operation: string; value: unknown }[]
  chart: 'line' | 'bar' | 'stacked_bar'
}

export interface AnalysisResponse {
  run_id: string
  rows: Record<string, unknown>[]
  total_rows: number
  valid_row_count: number
  highlights: string[]
  plan: AnalysisPlan
  formula_metadata: Record<string, unknown>
  invalid_value_counts: Record<string, number>
}

export interface Finding {
  code: string
  severity: 'error' | 'warning'
  column: string | null
  expected: string | null
  observed: string | null
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

function csrfToken(): string | undefined {
  const item = document.cookie.split('; ').find((entry) => entry.startsWith('finlabel_csrf='))
  return item ? decodeURIComponent(item.slice('finlabel_csrf='.length)) : undefined
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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

export function getHealth(): Promise<Health> {
  return request<Health>('/api/health')
}

export function getSources(): Promise<{ sources: SourceInfo[] }> {
  return request('/api/sources')
}

export function getFindings(source: string): Promise<{ findings: Finding[] }> {
  return request(`/api/monitor?source=${encodeURIComponent(source)}`)
}

export function proposeAnalysis(source: string, question: string) {
  return request<{ plan: AnalysisPlan; requires_confirmation: true }>('/api/plan', {
    method: 'POST', body: JSON.stringify({ source, question }),
  })
}

export function runAnalysis(source: string, question: string, plan: AnalysisPlan) {
  return request<AnalysisResponse>('/api/analyze', {
    method: 'POST', body: JSON.stringify({ source, question, plan }),
  })
}

export function getAnalysisRun(runId: string): Promise<AnalysisResponse> {
  return request(`/api/analyses/${encodeURIComponent(runId)}`)
}

export function postJson<TResponse, TBody>(path: string, body: TBody): Promise<TResponse> {
  return request<TResponse>(path, { method: 'POST', body: JSON.stringify(body) })
}
