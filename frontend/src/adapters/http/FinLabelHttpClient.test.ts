import { afterEach, describe, expect, it, vi } from 'vitest'
import { FinLabelHttpClient } from './FinLabelHttpClient'
import { ApiError, type FinLabelClient } from '@/application/ports/FinLabelClient'

const plan = { version: 1, metric: { operation: 'count' }, dimensions: [], filters: [], chart: 'bar' as const }
const split = { dataset_name: 'trusted', strategy: 'random', holdout_fraction: .2, seed: 42 }
const submit = { bundle_id: 'bundle', model_id: 'local/model', confirmed: true, exploratory_confirmed: false }
const transition = { action: 'activate' as const, version_id: 'v1', confirmed: true as const }
const operations: [string, (client: FinLabelClient) => Promise<unknown>, string, unknown?][] = [
  ['health', c => c.getHealth(), '/api/health'],
  ['autonomy overview', c => c.getAutonomyOverview(), '/api/autonomy/overview'],
  ['sources', c => c.getSources(), '/api/sources'],
  ['monitor', c => c.getFindings('a /?'), '/api/monitor?source=a%20%2F%3F'],
  ['saved analysis', c => c.getAnalysisRun('a /?'), '/api/analyses/a%20%2F%3F'],
  ['analysis proposal', c => c.proposeAnalysis('source', 'question'), '/api/plan', { source: 'source', question: 'question' }],
  ['analysis execution', c => c.runAnalysis('source', 'question', plan), '/api/analyze', { source: 'source', question: 'question', plan }],
  ['autonomous cycle', c => c.runAutonomousCycle('source', 'task', 'stable-key'), '/api/autonomy/run', { source: 'source', task: 'task' }],
  ['training overview', c => c.getTrainingOverview(), '/api/train/overview'],
  ['dataset quality', c => c.checkTrainingDataset('trusted'), '/api/train/check', { dataset_name: 'trusted' }],
  ['dataset split', c => c.splitTrainingDataset(split), '/api/train/split', split],
  ['training submission', c => c.submitTraining(submit), '/api/train/submit', submit],
  ['training job', c => c.getTrainingJob('a /?'), '/api/train/jobs/a%20%2F%3F'],
  ['versions', c => c.getTrainingVersions(), '/api/train/versions'],
  ['evaluation submission', c => c.evaluateTrainingCandidate('v1'), '/api/train/evaluate', { version_id: 'v1', confirmed: true }],
  ['evaluation job', c => c.getEvaluationJob('a /?'), '/api/train/evaluations/a%20%2F%3F'],
  ['version transition', c => c.transitionTrainingVersion(transition), '/api/train/transition', transition],
]

afterEach(() => { vi.unstubAllGlobals(); document.cookie = 'finlabel_csrf=; Max-Age=0; path=/' })

describe('HTTP client transport contract', () => {
  it.each(operations)('maps %s to the existing wire contract', async (_name, invoke, path, body) => {
    document.cookie = 'finlabel_csrf=encoded%20token; path=/'
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ result: 'server-response' }), { status: 200 }))
    vi.stubGlobal('fetch', fetcher)
    expect(await invoke(new FinLabelHttpClient())).toEqual({ result: 'server-response' })
    const [actualPath, init] = fetcher.mock.calls[0] as [string, RequestInit]
    expect(actualPath).toBe(path)
    expect(init.credentials).toBe('same-origin')
    expect(init.method ?? 'GET').toBe(body ? 'POST' : 'GET')
    expect(init.body).toBe(body ? JSON.stringify(body) : undefined)
    const headers = new Headers(init.headers)
    expect(headers.get('Content-Type')).toBe(body ? 'application/json' : null)
    expect(headers.get('X-CSRF-Token')).toBe(body ? 'encoded token' : null)
    expect(headers.get('Idempotency-Key')).toBe(path === '/api/autonomy/run' ? 'stable-key' : null)
  })

  it('preserves structured API errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: 'Blocked', reasons: ['policy'] }), { status: 409 })))
    const error = await new FinLabelHttpClient().getHealth().catch(e => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ name: 'ApiError', message: 'Blocked', status: 409, body: { error: 'Blocked', reasons: ['policy'] } })
  })

  it('handles non-JSON errors and missing CSRF cookies', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('bad gateway', { status: 502 }))
    vi.stubGlobal('fetch', fetcher)
    await expect(new FinLabelHttpClient().checkTrainingDataset('trusted')).rejects.toMatchObject({ message: 'A solicitação falhou (502).', body: null, status: 502 })
    expect(new Headers(fetcher.mock.calls[0][1].headers).has('X-CSRF-Token')).toBe(false)
  })

  it('propagates transport failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await expect(new FinLabelHttpClient().getHealth()).rejects.toThrow('offline')
  })
})
