import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { LazyLabelHttpClient } from './adapters/http/LazyLabelHttpClient'
import './index.css'

const client = new LazyLabelHttpClient()

// Follow the OS light/dark setting.
const dark = window.matchMedia('(prefers-color-scheme: dark)')
const applyTheme = () => document.documentElement.classList.toggle('dark', dark.matches)
applyTheme()
dark.addEventListener('change', applyTheme)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App client={client} />
  </StrictMode>,
)
