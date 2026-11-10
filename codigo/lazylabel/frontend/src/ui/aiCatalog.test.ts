/// <reference types="node" />
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { aiSystemPrompt, parseGeneratedSpec } from './aiCatalog'

const promptFile = resolve(import.meta.dirname, '../../../src/lazylabel/web/ai_ui_system_prompt.txt')
const line = (id: string, value: object) => JSON.stringify({ op: 'add', path: `/elements/${id}`, value })
const metric = (value: string) => ['{"op":"add","path":"/root","value":"m"}',
  line('m', { type: 'Metric', props: { label: 'A', value, hint: null }, children: [] })].join('\n')

describe('AI screen catalog', () => {
  it('ships the same system prompt the server sends (UPDATE_AI_PROMPT=1 rewrites it)', () => {
    if (process.env.UPDATE_AI_PROMPT) writeFileSync(promptFile, aiSystemPrompt)
    expect(readFileSync(promptFile, 'utf8')).toBe(aiSystemPrompt)
  })

  it('accepts numbers from the computed rows and rejects invented ones', () => {
    const rows = [{ cat: 'A', value: '0.6' }]
    expect(parseGeneratedSpec(metric('0.6'), rows, [1]).root).toBe('m')
    expect(() => parseGeneratedSpec(metric('0.75'), rows, [1])).toThrow(/não vieram do cálculo/)
  })
})
