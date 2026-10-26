export interface Health {
  status: 'ok'
  project: string
  sources: number
}

export interface AutonomySource { name: string; kind: string; columns: { name: string; inferred_type: string; mapped_type: string | null }[] }
export interface AutonomyTask { task_id: string; input_columns: string[]; labels: string[]; model_ref: string; policy_configured: boolean }
export interface AutonomyRun {
  run_id: string; task_id: string; source: string; started_at: string; finished_at: string
  label_run_id: string; label_model_ref: string
  labels: { applied: number; quarantined: number; reason_counts: Record<string, number> }
  training: { state: string; reason_codes: string[]; candidate_id: string | null; evaluation_id: string | null
    promotion_action: string | null; active_model_ref: string | null }
}
export interface AutonomyOverview {
  sources: AutonomySource[]; tasks: AutonomyTask[]; runs: AutonomyRun[]
  active_models: { task_id: string; model_ref: string | null; candidate_id: string | null }[]
  training_cycles: { cycle_id: string; task_id: string; state: string; reason_codes: string[]
    candidate_id: string | null; evaluation_id: string | null; promotion_action: string | null
    active_model_ref: string | null; created_at: string | null; evaluation: {
      holdout_count: number; candidate_metrics: Record<string, number>; incumbent_metrics: Record<string, number>
      same_frozen_holdout: true
    } | null }[]
  model_events: { event_id: string; task_id: string; action: string; reason_codes: string[]
    active_model_ref: string | null; rollback_from: string | null; created_at: string }[]
}
export interface AutonomousRunResult {
  run_id: string; task_id: string; source: string; started_at: string; finished_at: string
  labeling: { run_id: string; model_ref: string | null; applied_count: number; quarantined_count: number
    outcome_count: number; reason_counts: Record<string, number> }
  training: AutonomyRun['training']
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

export function getAutonomyOverview(): Promise<AutonomyOverview> {
  return request('/api/autonomy/overview')
}

export function runAutonomousCycle(source: string, task: string, idempotencyKey: string): Promise<AutonomousRunResult> {
  return request('/api/autonomy/run', { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({ source, task }) })
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
