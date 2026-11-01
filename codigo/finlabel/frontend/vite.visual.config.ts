import { defineConfig, mergeConfig, type Plugin } from 'vite'
import base from './vite.config.ts'

const runId = 'f31089a288754258b182c78fb43d43fe'
const result = {
  run_id: runId, total_rows: 4, valid_row_count: 125,
  rows: [
    { month: '2026-01', category: 'Cartões', value: '0.42' },
    { month: '2026-01', category: 'Crédito pessoal', value: '0.58' },
    { month: '2026-02', category: 'Cartões', value: '0.48' },
    { month: '2026-02', category: 'Crédito pessoal', value: '0.52' },
    { month: '2026-03', category: 'Cartões', value: '0.51' },
  ],
  highlights: ['Dados sintéticos para QA visual.'],
  plan: { version: 1, metric: { operation: 'share_of_total', column: 'saldo' }, dimensions: ['category'], time_axis: { column: 'month', grain: 'month' }, filters: [], chart: 'line' },
  formula_metadata: { valid_row_count: 125, denominator_group_fields: ['month'] },
  invalid_value_counts: { saldo: 3 },
}

const fixture: Plugin = {
  name: 'finlabel-visual-fixture',
  configureServer(server) {
    server.middlewares.use((request, response, next) => {
      if (request.url === '/api/health') {
        response.setHeader('Content-Type', 'application/json')
        response.end(JSON.stringify({ status: 'ok', project: 'QA sintético', sources: 1 }))
      } else if (request.url === '/api/sources') {
        response.setHeader('Content-Type', 'application/json')
        response.end(JSON.stringify({ sources: [{ name: 'carteira_demo', kind: 'csv', columns: [] }] }))
      } else if (request.url === '/api/train/overview') {
        response.setHeader('Content-Type', 'application/json')
        response.end(JSON.stringify({ datasets: [], tasks: [], gate: { authorized: false, missing: ['dataset confiável'], model_id: null }, active_version: null, active_diagnostic: null, registry_diagnostics: [], versions: [], jobs: [], evaluation_jobs: [] }))
      } else if (request.url === `/api/analyses/${runId}`) {
        response.setHeader('Content-Type', 'application/json')
        response.end(JSON.stringify(result))
      } else next()
    })
  },
}

export default mergeConfig(base, defineConfig({ base: '/', plugins: [fixture], server: { port: 5178 } }))
