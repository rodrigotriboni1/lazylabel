import { useState } from 'react'
import { createStateStore, type StateStore } from '@json-render/core'
import { defineRegistry, JSONUIProvider, Renderer } from '@json-render/react'
import { shadcnComponents } from '@json-render/shadcn'
import type { Spec } from '@json-render/core'
import { catalog, components } from './catalog'

const { registry } = defineRegistry(catalog, {
  components: Object.fromEntries(components.map((name) => [name, shadcnComponents[name]])) as never,
})

type Handlers = Record<string, (params: Record<string, unknown>) => unknown>

/** One store per mounted page; pages write fetched data into it and the spec reads it. */
export function usePageStore(initial: Record<string, unknown>): StateStore {
  const [store] = useState(() => createStateStore(initial))
  return store
}

export function SpecView({ spec, store, handlers }: { spec: Spec; store: StateStore; handlers?: Handlers }) {
  return <JSONUIProvider registry={registry} store={store} handlers={handlers}>
    <Renderer spec={spec} registry={registry} />
  </JSONUIProvider>
}

export type { Spec }
