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

export interface SplitTrainingRequest {
  dataset_name: string; strategy: string; holdout_fraction: number; seed: number
  group_column?: string; time_column?: string
}
export interface SplitTrainingResult {
  bundle_id: string; task_id: string; train_count: number; holdout_count: number
  strategy: string; holdout_fraction: number; seed: number; label_counts: Record<string, Record<string, number>>
  warnings: string[]; quality: TrainingQuality
}
export interface SubmitTrainingRequest {
  bundle_id: string; model_id: string; confirmed: boolean; exploratory_confirmed: boolean
  revision?: string | null; epochs?: number; batch_size?: number; learning_rate?: number; lora_rank?: number; seed?: number
}
export interface JobSubmission { job_id: string; state: string; progress: string }
export interface TrainingVersions {
  versions: TrainingVersion[]; active_version: string | null; active_diagnostic: string | null
  registry_diagnostics: { version_id: string; error: string }[]
}
export interface TransitionTrainingRequest {
  action: 'activate' | 'reject' | 'rollback' | 'recover'; version_id: string; confirmed: true; reason?: string
}

/** Application contract. Transport, cookies and browser APIs belong to adapters. */
export interface LazyLabelClient {
  getHealth(): Promise<Health>
  getAutonomyOverview(): Promise<AutonomyOverview>
  runAutonomousCycle(source: string, task: string, idempotencyKey: string): Promise<AutonomousRunResult>
  getSources(): Promise<{ sources: SourceInfo[] }>
  getFindings(source: string): Promise<{ findings: Finding[] }>
  proposeAnalysis(source: string, question: string): Promise<{ plan: AnalysisPlan; requires_confirmation: true }>
  runAnalysis(source: string, question: string, plan: AnalysisPlan): Promise<AnalysisResponse>
  getAnalysisRun(runId: string): Promise<AnalysisResponse>
  getTrainingOverview(): Promise<TrainingOverview>
  checkTrainingDataset(dataset_name: string): Promise<TrainingQuality>
  splitTrainingDataset(body: SplitTrainingRequest): Promise<SplitTrainingResult>
  submitTraining(body: SubmitTrainingRequest): Promise<JobSubmission>
  getTrainingJob(jobId: string): Promise<TrainingJob>
  getTrainingVersions(): Promise<TrainingVersions>
  evaluateTrainingCandidate(version_id: string): Promise<{ job_id: string; state: EvaluationJob['state']; progress: string }>
  getEvaluationJob(jobId: string): Promise<EvaluationJob>
  /** Ask the cloud model to lay out a json-render spec; returns its raw JSONL text. */
  generateUi(system: string, prompt: string): Promise<{ text: string }>
  transitionTrainingVersion(body: TransitionTrainingRequest): Promise<{ version: TrainingVersion; active_version: string | null }>
}
