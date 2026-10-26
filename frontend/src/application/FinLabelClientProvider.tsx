import type { ReactNode } from 'react'
import type { FinLabelClient } from './ports/FinLabelClient'
import { FinLabelClientContext } from './FinLabelClientContext'

export function FinLabelClientProvider({ client, children }: { client: FinLabelClient; children: ReactNode }) {
  return <FinLabelClientContext.Provider value={client}>{children}</FinLabelClientContext.Provider>
}
