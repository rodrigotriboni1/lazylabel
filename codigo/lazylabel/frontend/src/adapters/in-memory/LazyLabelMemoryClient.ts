import { ApiError, type LazyLabelClient } from '@/application/ports/LazyLabelClient'

type Responses = { [K in keyof LazyLabelClient]: Awaited<ReturnType<LazyLabelClient[K]>> }
export interface MemoryClientOptions { responses?: Partial<Responses>; error?: ApiError }

/** Deterministic, local presentation adapter. Mutations require explicit scenario responses. */
export class LazyLabelMemoryClient implements LazyLabelClient {
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

  private async result<K extends keyof LazyLabelClient>(operation: K): Promise<Responses[K]> {
    if (this.error) throw this.error
    const response = this.responses[operation]
    if (response === undefined) throw new ApiError(`Cenário não configurado: ${operation}`, 409, { error: 'scenario_not_configured' })
    return structuredClone(response)
  }
  getTrainingOverview: LazyLabelClient['getTrainingOverview'] = () => this.result('getTrainingOverview')
  checkTrainingDataset: LazyLabelClient['checkTrainingDataset'] = () => this.result('checkTrainingDataset')
  splitTrainingDataset: LazyLabelClient['splitTrainingDataset'] = () => this.result('splitTrainingDataset')
  submitTraining: LazyLabelClient['submitTraining'] = () => this.result('submitTraining')
  getTrainingJob: LazyLabelClient['getTrainingJob'] = () => this.result('getTrainingJob')
  getTrainingVersions: LazyLabelClient['getTrainingVersions'] = () => this.result('getTrainingVersions')
  evaluateTrainingCandidate: LazyLabelClient['evaluateTrainingCandidate'] = () => this.result('evaluateTrainingCandidate')
  getEvaluationJob: LazyLabelClient['getEvaluationJob'] = () => this.result('getEvaluationJob')
  transitionTrainingVersion: LazyLabelClient['transitionTrainingVersion'] = () => this.result('transitionTrainingVersion')
  getHealth: LazyLabelClient['getHealth'] = () => this.result('getHealth')
  getAutonomyOverview: LazyLabelClient['getAutonomyOverview'] = () => this.result('getAutonomyOverview')
  runAutonomousCycle: LazyLabelClient['runAutonomousCycle'] = () => this.result('runAutonomousCycle')
  getSources: LazyLabelClient['getSources'] = () => this.result('getSources')
  getFindings: LazyLabelClient['getFindings'] = () => this.result('getFindings')
  proposeAnalysis: LazyLabelClient['proposeAnalysis'] = () => this.result('proposeAnalysis')
  runAnalysis: LazyLabelClient['runAnalysis'] = () => this.result('runAnalysis')
  getAnalysisRun: LazyLabelClient['getAnalysisRun'] = () => this.result('getAnalysisRun')
  generateUi: LazyLabelClient['generateUi'] = () => this.result('generateUi')
}
