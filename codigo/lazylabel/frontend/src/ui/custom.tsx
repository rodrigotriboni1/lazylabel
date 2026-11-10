import { useId } from 'react'
import { z } from 'zod'
import { useBoundProp } from '@json-render/react'
import type { AnalysisResponse } from '@/application/ports/LazyLabelClient'
import { AnalysisResult } from '@/components/analysis/AnalysisResult'

// LazyLabel's own components: domain views plus accessible replacements where the
// shadcn catalog falls short (its Select label is not tied to the field).
export const customDefinitions = {
  Choice: {
    props: z.object({ label: z.string(), value: z.string().nullable(), placeholder: z.string().nullable(),
      options: z.array(z.object({ value: z.string(), label: z.string() })) }),
    events: ['change'],
    description: 'Native labeled dropdown; bind value with $bindState',
  },
  Metric: {
    props: z.object({ label: z.string(), value: z.string(), hint: z.string().nullable() }),
    description: 'One number with its label',
  },
  Pills: {
    props: z.object({ label: z.string(), items: z.array(z.string()) }),
    description: 'Labeled row of short tags',
  },
  Steps: {
    props: z.object({ label: z.string(), current: z.number(), steps: z.array(z.object({ title: z.string(), detail: z.string() })) }),
    description: 'Ordered workflow; current is the active step index',
  },
  Status: {
    props: z.object({ text: z.string() }),
    description: 'Polite live-region message',
  },
  AnalysisResult: {
    props: z.object({ result: z.any() }),
    description: 'Chart, KPIs and exact table of an analysis run',
  },
}

export const customComponents = {
  Choice: ({ props, bindings, emit }: { props: { label: string; value: string | null; placeholder: string | null; options: { value: string; label: string }[] }; bindings?: Record<string, string>; emit: (e: string) => void }) => {
    const id = useId()
    const [value, setValue] = useBoundProp<string>(props.value ?? '', bindings?.value)
    return <div className="grid w-full gap-2">
      <label htmlFor={id} className="text-sm font-medium">{props.label}</label>
      <select id={id} className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-xs" value={value ?? ''}
        onChange={(e) => { setValue(e.target.value); emit('change') }}>
        {props.placeholder && <option value="">{props.placeholder}</option>}
        {props.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  },
  Metric: ({ props }: { props: { label: string; value: string; hint: string | null } }) => <div className="rounded-lg border bg-muted/40 p-3">
    <p className="text-xs text-muted-foreground">{props.label}</p>
    <p className="mt-1 text-xl font-semibold tabular-nums">{props.value}</p>
    {props.hint && <p className="mt-1 text-xs text-muted-foreground">{props.hint}</p>}
  </div>,
  Pills: ({ props }: { props: { label: string; items: string[] } }) => <div>
    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{props.label}</p>
    <div className="mt-2 flex flex-wrap gap-2">{props.items.map((item) => <span key={item} className="rounded-md border px-2 py-0.5 text-xs">{item}</span>)}</div>
  </div>,
  Steps: ({ props }: { props: { label: string; current: number; steps: { title: string; detail: string }[] } }) =>
    <ol aria-label={props.label} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-7">
      {props.steps.map((step, i) => <li key={step.title} aria-current={i === props.current ? 'step' : undefined}
        className={`rounded-lg border p-3 ${i === props.current ? 'border-primary bg-primary/5' : i < props.current ? 'bg-muted/40' : ''}`}>
        <p className="text-xs font-semibold"><span className="mr-1 text-muted-foreground">{i + 1}.</span>{step.title}</p>
        <p className="mt-1 text-xs text-muted-foreground">{step.detail}</p>
      </li>)}
    </ol>,
  Status: ({ props }: { props: { text: string } }) => <p role="status" className="rounded-lg border bg-muted/40 p-3 text-sm">{props.text}</p>,
  AnalysisResult: ({ props }: { props: { result: AnalysisResponse } }) => <AnalysisResult result={props.result} />,
}
