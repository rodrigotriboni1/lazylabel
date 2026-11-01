export * from '@/application/ports/FinLabelClient'
import type { FinLabelClient } from '@/application/ports/FinLabelClient'
import { FinLabelHttpClient } from '@/adapters/http/FinLabelHttpClient'

const client = new FinLabelHttpClient()
export const getTrainingOverview: FinLabelClient['getTrainingOverview'] = (...args) => client.getTrainingOverview(...args)
export const checkTrainingDataset: FinLabelClient['checkTrainingDataset'] = (...args) => client.checkTrainingDataset(...args)
export const splitTrainingDataset: FinLabelClient['splitTrainingDataset'] = (...args) => client.splitTrainingDataset(...args)
export const submitTraining: FinLabelClient['submitTraining'] = (...args) => client.submitTraining(...args)
export const getTrainingJob: FinLabelClient['getTrainingJob'] = (...args) => client.getTrainingJob(...args)
export const getTrainingVersions: FinLabelClient['getTrainingVersions'] = (...args) => client.getTrainingVersions(...args)
export const evaluateTrainingCandidate: FinLabelClient['evaluateTrainingCandidate'] = (...args) => client.evaluateTrainingCandidate(...args)
export const getEvaluationJob: FinLabelClient['getEvaluationJob'] = (...args) => client.getEvaluationJob(...args)
export const transitionTrainingVersion: FinLabelClient['transitionTrainingVersion'] = (...args) => client.transitionTrainingVersion(...args)
export const getHealth: FinLabelClient['getHealth'] = (...args) => client.getHealth(...args)
export const getAutonomyOverview: FinLabelClient['getAutonomyOverview'] = (...args) => client.getAutonomyOverview(...args)
export const runAutonomousCycle: FinLabelClient['runAutonomousCycle'] = (...args) => client.runAutonomousCycle(...args)
export const getSources: FinLabelClient['getSources'] = (...args) => client.getSources(...args)
export const getFindings: FinLabelClient['getFindings'] = (...args) => client.getFindings(...args)
export const proposeAnalysis: FinLabelClient['proposeAnalysis'] = (...args) => client.proposeAnalysis(...args)
export const runAnalysis: FinLabelClient['runAnalysis'] = (...args) => client.runAnalysis(...args)
export const getAnalysisRun: FinLabelClient['getAnalysisRun'] = (...args) => client.getAnalysisRun(...args)

/** Legacy generic helper; new presentation code uses the typed client port. */
export const postJson = client.postJson.bind(client)
