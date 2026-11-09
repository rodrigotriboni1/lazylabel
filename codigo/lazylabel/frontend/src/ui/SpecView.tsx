import type { StateStore } from '@json-render/core'
import { defineRegistry, JSONUIProvider, Renderer } from '@json-render/react'
import { shadcnComponents } from '@json-render/shadcn'
import type { Spec } from '@json-render/core'
import { catalog, components } from './catalog'
import { customComponents } from './custom'

const { registry } = defineRegistry(catalog, {
  components: { ...Object.fromEntries(components.map((name) => [name, shadcnComponents[name]])), ...customComponents } as never,
})

type Handlers = Record<string, (params: Record<string, unknown>) => unknown>

export function SpecView({ spec, store, handlers }: { spec: Spec; store: StateStore; handlers?: Handlers }) {
  return <JSONUIProvider registry={registry} store={store} handlers={handlers}>
    <Renderer spec={spec} registry={registry} />
  </JSONUIProvider>
}

