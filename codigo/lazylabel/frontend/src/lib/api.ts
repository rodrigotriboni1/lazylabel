export * from '@/application/ports/LazyLabelClient'
import type { LazyLabelClient } from '@/application/ports/LazyLabelClient'
import { LazyLabelHttpClient } from '@/adapters/http/LazyLabelHttpClient'

const client = new LazyLabelHttpClient()
export const getTrainingOverview: LazyLabelClient['getTrainingOverview'] = (...args) => client.getTrainingOverview(...args)
export const checkTrainingDataset: LazyLabelClient['checkTrainingDataset'] = (...args) => client.checkTrainingDataset(...args)
export const splitTrainingDataset: LazyLabelClient['splitTrainingDataset'] = (...args) => client.splitTrainingDataset(...args)
export const submitTraining: LazyLabelClient['submitTraining'] = (...args) => client.submitTraining(...args)
export const getTrainingJob: LazyLabelClient['getTrainingJob'] = (...args) => client.getTrainingJob(...args)
export const getTrainingVersions: LazyLabelClient['getTrainingVersions'] = (...args) => client.getTrainingVersions(...args)
export const evaluateTrainingCandidate: LazyLabelClient['evaluateTrainingCandidate'] = (...args) => client.evaluateTrainingCandidate(...args)
export const getEvaluationJob: LazyLabelClient['getEvaluationJob'] = (...args) => client.getEvaluationJob(...args)
export const transitionTrainingVersion: LazyLabelClient['transitionTrainingVersion'] = (...args) => client.transitionTrainingVersion(...args)
export const getHealth: LazyLabelClient['getHealth'] = (...args) => client.getHealth(...args)
export const getAutonomyOverview: LazyLabelClient['getAutonomyOverview'] = (...args) => client.getAutonomyOverview(...args)
export const runAutonomousCycle: LazyLabelClient['runAutonomousCycle'] = (...args) => client.runAutonomousCycle(...args)
export const getSources: LazyLabelClient['getSources'] = (...args) => client.getSources(...args)
export const getFindings: LazyLabelClient['getFindings'] = (...args) => client.getFindings(...args)
export const proposeAnalysis: LazyLabelClient['proposeAnalysis'] = (...args) => client.proposeAnalysis(...args)
export const runAnalysis: LazyLabelClient['runAnalysis'] = (...args) => client.runAnalysis(...args)
export const getAnalysisRun: LazyLabelClient['getAnalysisRun'] = (...args) => client.getAnalysisRun(...args)

/** Legacy generic helper; new presentation code uses the typed client port. */
export const postJson = client.postJson.bind(client)
