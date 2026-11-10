import type { ReactNode } from 'react'
import type { LazyLabelClient } from './ports/LazyLabelClient'
import { LazyLabelClientContext } from './LazyLabelClientContext'

export function LazyLabelClientProvider({ client, children }: { client: LazyLabelClient; children: ReactNode }) {
  return <LazyLabelClientContext.Provider value={client}>{children}</LazyLabelClientContext.Provider>
}
