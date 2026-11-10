import { createContext, useContext } from 'react'
import type { LazyLabelClient } from './ports/LazyLabelClient'

export const LazyLabelClientContext = createContext<LazyLabelClient | null>(null)

export function useLazyLabelClient(): LazyLabelClient {
  const client = useContext(LazyLabelClientContext)
  if (!client) throw new Error('LazyLabelClientProvider ausente.')
  return client
}
