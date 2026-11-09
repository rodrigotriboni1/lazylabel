import { useState } from 'react'
import { createStateStore, type Spec, type StateStore } from '@json-render/core'

/** One store per mounted page; pages write fetched data into it and the spec reads it. */
export function usePageStore(initial: Record<string, unknown>): StateStore {
  const [store] = useState(() => createStateStore(initial))
  return store
}

export type { Spec }
