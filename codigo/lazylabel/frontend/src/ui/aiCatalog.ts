import { compileSpecStream, defineCatalog, type Spec } from '@json-render/core'
import { schema } from '@json-render/react/schema'
import { shadcnComponentDefinitions as d } from '@json-render/shadcn/catalog'
import { customDefinitions as c } from './custom'

// Display-only subset: a generated screen can show results, never act on the workspace.
export const aiCatalog = defineCatalog(schema, {
  components: { Card: d.Card, Stack: d.Stack, Grid: d.Grid, Separator: d.Separator, Heading: d.Heading, Text: d.Text,
    Badge: d.Badge, Alert: d.Alert, Table: d.Table, Progress: d.Progress, Metric: c.Metric, Pills: c.Pills },
  actions: {},
})

// The server sends this as the system prompt (src/lazylabel/web/ai_ui_system_prompt.txt, synced by aiCatalog.test.ts).
export const aiSystemPrompt = aiCatalog.prompt({
  customRules: [
    'Use ONLY the numbers, labels and dates present in RESULT ROWS. Never invent, estimate or add sample data; this overrides any rule asking for sample data.',
    'Copy numeric values exactly as given; do not recompute, round or convert them.',
    'Include one Table listing every row given in RESULT ROWS, and no other rows. If fewer rows were given than the total, say so in a Text.',
    'Write every visible text in Brazilian Portuguese.',
  ],
})

const NUMBER = /^-?\d[\d.,]*%?$/

function strings(value: unknown, out: string[] = []): string[] {
  if (typeof value === 'string') out.push(value.trim())
  else if (typeof value === 'number') out.push(String(value))
  else if (Array.isArray(value)) value.forEach((v) => strings(v, out))
  else if (value && typeof value === 'object') Object.values(value).forEach((v) => strings(v, out))
  return out
}

/** Turns the model's JSONL into a display-only spec whose every number came from the computed rows. */
export function parseGeneratedSpec(text: string, rows: Record<string, unknown>[], totals: number[]): Spec {
  const jsonl = text.split('\n').filter((line) => line.trim().startsWith('{')).join('\n')
  const spec = compileSpecStream(jsonl) as unknown as Spec
  if (!spec?.root || !aiCatalog.validate(spec).success) throw new Error('A IA devolveu uma tela inválida. Tente reformular a pergunta.')
  const known = new Set([...strings(rows), ...totals.map(String)])
  const shown = strings([Object.values(spec.elements ?? {}).map((e) => e.props), spec.state])
  const invented = shown.filter((s) => NUMBER.test(s) && !known.has(s))
  if (invented.length) throw new Error(`A IA mostrou números que não vieram do cálculo (${invented.slice(0, 3).join(', ')}). A tela foi descartada.`)
  return spec
}
