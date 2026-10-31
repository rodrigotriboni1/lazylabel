# 14: Aplicação React local completa e pacote instalável

**Status:** ready-for-human

**Plano:** `docs/superpowers/plans/2026-10-20-finlabel-react-local-panel.md`, Task 5.
**Branch:** `codex/react-package-final`, base `d639e2b` (`codex/finlabel-lifecycle`).

## Objetivo

Servir todas as páginas do produto no React empacotado e garantir que a distribuição Python instalada funcione sem servidor Vite, removendo as telas legadas somente depois de comprovar paridade.

## Escopo

- Roteamento SPA para `/`, `/analysis`, `/analysis/{run_id}`, `/monitor`, `/labeling`, `/review` e `/training`, mantendo APIs e assets explicitamente separados.
- Converter análise com `run_id` para uma rota React que leia resultados pelo endpoint seguro; preservar gráficos locais já gerados apenas quando isso puder ser feito sem introduzir scripts externos/violação de CSP.
- Remover Jinja/templates e JS/CSS UI-only somente após confirmar que nenhuma rota ainda os usa; manter dependências se necessário.
- Incluir bundles/fontes frontend no wheel e executar `finlabel serve` a partir de instalação limpa sem frontend dev server.
- Documentar build/instalação/serve e limitações no README.

## Critérios de aceite manual

- `npm ci && npm run build`; wheel construído e instalado em ambiente limpo/temporário.
- Executar CLI/painel instalado em loopback após primeiro inspecionar listeners/processos existentes; usar porta livre e processo temporário. Registrar comando e efeitos.
- Confirmar deep links e refresh das rotas, `/api/*` JSON, assets ausentes 404, Host/Origin/CSRF, headers locais, e todos os fluxos Overview/Analysis/Monitor/Labeling/Review/Training.
- Inspecionar o ciclo de treinamento/diagrama e o app em viewport desktop e estreita se o browser host permitir; registrar limites de QA visual.
- Nenhum teste automatizado, peso/modelo real, treino ou inferência real.

## Guardrails

- Dados financeiros e revisão ficam locais; sem scripts/CDNs/analytics externos.
- Loopback por padrão. Para serviço local: inspecionar primeiro; não parar/reiniciar processo existente sem necessidade.
- Não apagar componentes/arquivos até pesquisar referências e validar substituição.

## Implementação

Worktree: `codigo/finlabel/.worktrees/react-package-final`.

## Revisão independente

- Re-review aprovou roteamento React, análise por deep link, verificação de hash, fallback API/SPA, retirada de Jinja e packaging.
- Solicitou um ajuste P2: impor limite de tamanho nos arquivos `result.json` e manifesto antes de leitura/parse no endpoint da análise. Resolvido no commit `ec701e3`.

### Implementação desta etapa

- Todas as rotas de tela (`/`, `/analysis`, `/analysis/{run_id}`, `/monitor`, `/labeling`, `/review`, `/training`) servem o shell React em acesso direto/refresh. `/api/*` e `/static/*` permanecem separados; asset inexistente não recebe o fallback SPA.
- A rota `/analysis/{run_id}` agora carrega o resultado salvo por `/api/analyses/{run_id}`. A API valida o ID, rejeita symlinks, confere `result_sha256`, limita a leitura de `result.json` a 1 MiB e a leitura do manifesto a 64 KiB antes do parse, e retorna no máximo 100 linhas.
- Removidos os quatro templates Jinja e o JS/CSS legado de interface após busca de referências. `jinja2` saiu do extra `web`; Plotly foi mantido porque `finlabel analyze` ainda gera gráficos HTML offline.
- O README documenta build, criação de wheel, instalação das dependências `web`, uso local e deep links.

### Evidências manuais

- `cd frontend && npm ci && npm run build`: concluído (Vite 8.3.4; aviso de bundle JS acima de 500 kB, sem falha).
- `/Users/rodrigotriboni1/.local/bin/python3.12 -m pip wheel --no-deps . --wheel-dir /tmp/finlabel-task5-final-dist.Crgu0M`: wheel final `finlabel_local-0.1.0-py3-none-any.whl` criado (382438 bytes; SHA-256 `c85ef9169321549ea6ac488ccd2062dfc6e7bf40e96e046f2795a086a9b1720e`).
- Ambiente Python limpo `/tmp/finlabel-task5-final-venv.spDG18`: wheel final instalado; `finlabel.__file__` apontou para `site-packages`; shell e JS/CSS/fontes estavam empacotados e `web/templates` ausente. Dependências web foram instaladas separadamente no mesmo ambiente.
- `finlabel serve --project /private/tmp/finlabel-task5-project --host 127.0.0.1 --port 18765`: iniciou o wheel instalado sem Vite, PID 96637 e depois PID 96814, somente em loopback. Antes de cada início, `lsof -nP -iTCP:18765 -sTCP:LISTEN` mostrou porta livre; após cada parada o listener não permaneceu.
- HTTP manual: sete rotas de tela e refresh/deep link retornaram shell React (200); `/api/health`, `/api/sources`, `/api/label/tasks`, `/api/train/overview` e resultado analítico sintético retornaram JSON (200); deep link de análise com run inexistente e API desconhecida retornaram 404; asset ausente retornou 404 sem shell; Host inválido 400; Origin inválida 403; POST sem CSRF 403; hash adulterado do artefato de análise 409.
- `python3.12 -m compileall -q src/finlabel/web/app.py` e `git diff --check`: concluídos. Busca por URLs/scripts/CDNs externos na fonte React e shell compilado não encontrou referências.
- Re-review P2: `python3.12 -m py_compile src/finlabel/web/app.py` e `git diff --check` passaram. Aceitação sintética instrumentou `Path.open`: resultado inválido com tamanho acima de 1 MiB respondeu 422 em 82 bytes sem abrir o arquivo; manifesto acima de 64 KiB respondeu 409 em 68 bytes sem abrir o arquivo; artefato com hash válido respondeu 200 em 168 bytes.
- Verificação cumulativa final em `59f6205`: `npm ci && npm run build`, `python3.12 -m compileall -q src/finlabel`, `git diff --check d639e2b..HEAD` e novo build de wheel passaram. O wheel atualizado foi instalado em `/tmp/finlabel-final-venv-verified`; shell React, JS, CSS, cinco fontes e ausência de templates foram confirmados.

### Limites desta validação

- Nenhum teste automatizado foi adicionado ou executado. Nenhum modelo/peso, fine-tuning ou inferência foi executado; o projeto sintético estava sem fontes e credenciais.
- Não foi possível revisar visualmente desktop/viewport estreita nem a interação das telas no browser: o host macOS estava bloqueado. Foram confirmadas as rotas, o shell empacotado e os endpoints básicos via HTTP; QA visual e fluxos que exigem modelo permanecem para revisão humana.
