import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { LazyLabelHttpClient } from './adapters/http/LazyLabelHttpClient'
import './index.css'

const client = new LazyLabelHttpClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App client={client} />
  </StrictMode>,
)
