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

export function postJson<TResponse, TBody>(path: string, body: TBody): Promise<TResponse> {
  return request<TResponse>(path, { method: 'POST', body: JSON.stringify(body) })
}
