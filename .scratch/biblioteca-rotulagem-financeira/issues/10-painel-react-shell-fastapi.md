# 10: Shell React/Vite e entrega estática segura pelo FastAPI

**Status:** ready-for-human

**Conclusão integrada (26/10/2026):** `codex/finlabel-autonomous-mvp`; servidor FastAPI fornece shell SPA e endpoints locais de health/fontes/autonomia. Rotas diretas, refresh e navegação foram conferidos em desktop e mobile. Evidências e limites em `.scratch/biblioteca-rotulagem-financeira/completion/verification-report.md`.

**Plano:** `docs/superpowers/plans/2026-10-20-finlabel-react-local-panel.md`, Task 1.

## Objetivo

Preparar o app React/TypeScript com shadcn/ui e servir seus arquivos buildados pelo painel FastAPI local sem alterar a fronteira de segurança existente.

## Escopo

- Criar `frontend/` com Vite, React, TypeScript, Tailwind, shadcn/ui e cliente API tipado, incluindo lockfile e saída estável em `src/finlabel/web/static/app/`.
- Integrar arquivos estáticos ao pacote Python.
- Servir `/` e rotas SPA conhecidas pelo app; APIs e `/static/*` existentes preservam precedência. Asset ausente e `/api/*` nunca retornam `index.html`.
- Shell responsivo inicial com navegação e estado seguro do projeto/servidor sem retornar valores de registros.
- Preservar bind loopback, validação Host/Origin, CSRF, limites de corpo/resposta e headers existentes.

## Critérios de aceite manual

- Build Vite de produção gera arquivos estáticos no diretório de pacote esperado.
- FastAPI serve `/` e caminho SPA conhecido; asset inexistente retorna 404; `/api/health` ou metadata equivalente retorna JSON; `/api/*` não cai no fallback HTML.
- Host inválido e POST sem CSRF continuam bloqueados; servidor não aceita bind externo.
- App não requer CDN/serviço remoto e o cliente API envia CSRF em mutações.
- Registrar comandos de build/serve/browser e limites; sem testes automatizados.

## Implementação e revisão

- Branch `codex/react-shell`, commit `11c338e`, integrado no branch cumulativo após revisão independente aprovada.
- `npm ci && npm run build` e wheel local foram verificados. Rota SPA, `/api/health`, unknown API, missing asset 404, Host inválido, CSRF ausente/válido, bind externo e desktop/mobile foram exercitados manualmente.
- Nenhum teste automatizado foi adicionado ou executado.

## Limites

Esta fatia cria o shell; analytics, monitoramento, review e treino entram em tickets seguintes. Desenvolvimento em `codex/react-shell` sobre integration `d9e040a`.

## Implementação — 2026-10-20

- **Branch/commit:** `codex/react-shell`, base `d9e040a`, commit `11c338e`.
- **Arquivos:** `frontend/` (React, Vite, TypeScript, shadcn/ui, Tailwind e cliente API tipado), `src/finlabel/web/static/app/` (build local), `src/finlabel/web/app.py`, `pyproject.toml` e `README.md`.
- **Entregue:** shell responsivo pt-BR com navegação, estado e contagem de fontes do workspace; endpoint metadata-only `/api/health`; cookie CSRF emitido pelo shell; mutações API enviam o cookie no header `X-CSRF-Token`; nomes estáveis no build e assets incluídos no wheel. Rotas conhecidas atendem o shell depois das rotas/API existentes, sem fallback de HTML para API ou asset ausente.
- **Verificação manual:** `cd frontend && npm ci && npm run build`; `python3.12 -m pip wheel --no-deps -w /tmp/finlabel-react-wheel .`; `finlabel project init /tmp/finlabel-react-shell-manual`; `finlabel serve --project /tmp/finlabel-react-shell-manual --host 127.0.0.1 --port 8876`; `curl` para `/`, `/training`, `/static/app/assets/missing.js`, `/api/health`, `/api/missing` e Host inválido. Resultado: shell 200, caminho SPA 200, asset ausente 404, health JSON 200, API desconhecida JSON 404 e Host inválido 400. POST sem CSRF 403; cookie/header correspondente chega ao handler (400 por fonte deliberadamente inexistente). `create_app(..., host="0.0.0.0")` rejeitou bind externo.
- **Browser:** `/` carregou e mostrou workspace e status local; inspeção em 390×844 encontrou rótulos inferiores sobrepostos, corrigidos com rótulos móveis curtos e espaço para a barra fixa; inspeção visual repetida mostrou navegação legível. Viewport restaurado.
- **Limites:** nenhuma suíte automatizada adicionada ou executada. Analytics, monitor, revisão e treino permanecem telas de shell para tickets posteriores. `npm audit` e `npm audit --omit=dev` reportaram zero vulnerabilidades após remover o CLI shadcn das dependências do projeto.
