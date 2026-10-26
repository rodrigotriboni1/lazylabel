import { createContext, useContext } from 'react'
import type { FinLabelClient } from './ports/FinLabelClient'

export const FinLabelClientContext = createContext<FinLabelClient | null>(null)

export function useFinLabelClient(): FinLabelClient {
  const client = useContext(FinLabelClientContext)
  if (!client) throw new Error('FinLabelClientProvider ausente.')
  return client
}
