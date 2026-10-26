import { describe, expect, it } from 'vitest'
import { FinLabelMemoryClient } from './FinLabelMemoryClient'
import { ApiError } from '@/application/ports/FinLabelClient'

describe('in-memory client', () => {
  it('provides an empty workspace with no fabricated training evidence', async () => {
    const client = new FinLabelMemoryClient()
    expect(await client.getSources()).toEqual({ sources: [] })
    expect(await client.getAutonomyOverview()).toEqual({ sources: [], tasks: [], runs: [], active_models: [], training_cycles: [], model_events: [] })
    expect((await client.getTrainingOverview()).gate.authorized).toBe(false)
    await expect(client.runAutonomousCycle('source', 'task', 'key')).rejects.toMatchObject({ status: 409 })
  })

  it('returns configured successes deterministically and isolates mutable response data', async () => {
    const client = new FinLabelMemoryClient({ responses: { getHealth: { status: 'ok', project: 'demo', sources: 1 }, getSources: { sources: [{ name: 'demo', kind: 'csv', columns: [] }] } } })
    expect(await client.getHealth()).toEqual({ status: 'ok', project: 'demo', sources: 1 })
    const first = await client.getSources()
    first.sources.length = 0
    expect((await client.getSources()).sources).toHaveLength(1)
  })

  it('keeps configured error states distinct from empty results', async () => {
    const client = new FinLabelMemoryClient({ error: new ApiError('Unavailable', 503, { error: 'Unavailable' }) })
    await expect(client.getSources()).rejects.toMatchObject({ status: 503, message: 'Unavailable' })
    await expect(client.getTrainingOverview()).rejects.toMatchObject({ status: 503 })
  })
})
