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

export const aiSystemPrompt = aiCatalog.prompt({
  customRules: [
    'Use ONLY the numbers, labels and dates present in RESULT ROWS. Never invent, estimate or add sample data; this overrides any rule asking for sample data.',
    'Copy numeric values exactly as given; do not recompute, round or convert them.',
    'Always include one Table listing every result row.',
    'Write every visible text in Brazilian Portuguese.',
  ],
})

/** Turns the model's JSONL patches into a spec, or throws if it is not a valid display-only screen. */
export function parseGeneratedSpec(text: string): Spec {
  const jsonl = text.split('\n').filter((line) => line.trim().startsWith('{')).join('\n')
  const spec = compileSpecStream(jsonl) as unknown as Spec
  const checked = aiCatalog.validate(spec)
  if (!spec?.root || !checked.success) throw new Error('A IA devolveu uma tela inválida. Tente reformular a pergunta.')
  return spec
}
