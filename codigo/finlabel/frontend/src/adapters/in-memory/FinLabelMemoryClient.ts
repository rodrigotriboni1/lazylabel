import { ApiError, type FinLabelClient } from '@/application/ports/FinLabelClient'

type Responses = { [K in keyof FinLabelClient]: Awaited<ReturnType<FinLabelClient[K]>> }
export interface MemoryClientOptions { responses?: Partial<Responses>; error?: ApiError }

/** Deterministic, local presentation adapter. Mutations require explicit scenario responses. */
export class FinLabelMemoryClient implements FinLabelClient {
  private readonly responses: Partial<Responses>
  private readonly error?: ApiError

  constructor(options: MemoryClientOptions = {}) {
    this.error = options.error
    this.responses = structuredClone({
      getHealth: { status: 'ok', project: 'memory', sources: 0 },
      getSources: { sources: [] },
      getFindings: { findings: [] },
      getAutonomyOverview: { sources: [], tasks: [], runs: [], active_models: [], training_cycles: [], model_events: [] },
      getTrainingOverview: { datasets: [], tasks: [], gate: { authorized: false, missing: ['not_configured'], model_id: null },
        active_version: null, active_diagnostic: null, registry_diagnostics: [], versions: [], jobs: [], evaluation_jobs: [] },
      getTrainingVersions: { versions: [], active_version: null, active_diagnostic: null, registry_diagnostics: [] },
      ...options.responses,
    })
  }

  private async result<K extends keyof FinLabelClient>(operation: K): Promise<Responses[K]> {
    if (this.error) throw this.error
    const response = this.responses[operation]
    if (response === undefined) throw new ApiError(`Cenário não configurado: ${operation}`, 409, { error: 'scenario_not_configured' })
    return structuredClone(response)
  }
  getTrainingOverview: FinLabelClient['getTrainingOverview'] = () => this.result('getTrainingOverview')
  checkTrainingDataset: FinLabelClient['checkTrainingDataset'] = () => this.result('checkTrainingDataset')
  splitTrainingDataset: FinLabelClient['splitTrainingDataset'] = () => this.result('splitTrainingDataset')
  submitTraining: FinLabelClient['submitTraining'] = () => this.result('submitTraining')
  getTrainingJob: FinLabelClient['getTrainingJob'] = () => this.result('getTrainingJob')
  getTrainingVersions: FinLabelClient['getTrainingVersions'] = () => this.result('getTrainingVersions')
  evaluateTrainingCandidate: FinLabelClient['evaluateTrainingCandidate'] = () => this.result('evaluateTrainingCandidate')
  getEvaluationJob: FinLabelClient['getEvaluationJob'] = () => this.result('getEvaluationJob')
  transitionTrainingVersion: FinLabelClient['transitionTrainingVersion'] = () => this.result('transitionTrainingVersion')
  getHealth: FinLabelClient['getHealth'] = () => this.result('getHealth')
  getAutonomyOverview: FinLabelClient['getAutonomyOverview'] = () => this.result('getAutonomyOverview')
  runAutonomousCycle: FinLabelClient['runAutonomousCycle'] = () => this.result('runAutonomousCycle')
  getSources: FinLabelClient['getSources'] = () => this.result('getSources')
  getFindings: FinLabelClient['getFindings'] = () => this.result('getFindings')
  proposeAnalysis: FinLabelClient['proposeAnalysis'] = () => this.result('proposeAnalysis')
  runAnalysis: FinLabelClient['runAnalysis'] = () => this.result('runAnalysis')
  getAnalysisRun: FinLabelClient['getAnalysisRun'] = () => this.result('getAnalysisRun')
}
