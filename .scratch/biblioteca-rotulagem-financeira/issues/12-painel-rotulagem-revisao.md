# 12: Configuração de tarefas, sugestões e revisão humana no painel

**Status:** ready-for-human

**Escopo supersedido (26/10/2026):** o fluxo atual não oferece decisões manuais por registro. A página `/labeling` executa o ciclo autônomo, mostra contagens aplicadas/quarentena e motivos; o histórico legado permanece consultável. Branch integrada: `codex/finlabel-autonomous-mvp`. Ver `.scratch/biblioteca-rotulagem-financeira/completion/verification-report.md`.

**Plano:** `docs/superpowers/plans/2026-10-20-finlabel-react-local-panel.md`, Task 3.

## Objetivo

Habilitar a criação/seleção de uma tarefa configurável, gerar sugestões pelo modelo local e revisar cada decisão humana com proveniência explícita.

## Escopo

- Adicionar telas de tarefa, execução e revisão no React usando os endpoints e serviços de labeling atuais.
- Mostrar rótulos/colunas permitidas, fonte, modelo, estado de execução, sugestões, saídas inválidas, estado revisado e stale.
- Review actions `accept`, `edit`, `reject`, `skip` enviam identidade de run/suggestion/record/digest e chave idempotente estável.
- Lista oculta valores de registros; detalhe local explícito mostra apenas campos selecionados pela tarefa.
- Após sucesso/retry, consultar estado do servidor; nunca considerar estado local uma decisão persistida.

## Critérios de aceite manual

- Iniciar execução e inspecionar estado e payload; tratar indisponibilidade do modelo local sem simular resultado.
- Aceitar, editar, rejeitar e pular exemplos no browser; fazer refresh/retry e confirmar evento append-only único via CLI.
- Um registro com digest stale não oferece ação de revisão e não entra no dataset revisado.
- Saídas inválidas, pendentes e rejeitadas são visualmente distintas.
- Build e inspeção manual desktop/narrow viewport; nenhum teste automatizado.

## Limites

Valores de registro aparecem apenas no detalhe intencionalmente selecionado pelo operador local. Sem modelo/backend configurado, explicar requisito e manter ações indisponíveis.

Implementar em `codex/react-labeling` sobre integration `efe3507`.

## Implementação — 2026-10-20

- **Branch/commit/base:** `codex/react-labeling`, commit `0a782868ec55df6442734654db3e72745e6d48a2`, sobre `efe3507`.
- **Entregue:** telas React para escolher tarefa/fonte, iniciar execução local e revisar sugestões; painel apresenta contagens de válidas/inválidas, estados pendente/aceita/corrigida/rejeitada/pulada/stale e rótulo humano final. Lista/API padrão omitem valores de registros; ação “Ver campos” busca somente os campos da tarefa. Ações carregam proveniência, chave determinística por run/sugestão/ação, bloqueiam cliques duplicados e consultam estado do servidor após resultado ou erro.
- **API/domínio:** `GET /api/label/tasks` lista configuração sem valores; `GET /api/label/suggestion` fornece detalhe selecionado explicitamente; `skip` é evento append-only e é contado como `skipped`, sem elegibilidade para dataset. Retry de decisão já gravada retorna o evento existente antes de testar novamente se a fonte ficou stale.
- **Verificação manual sintética:** `npm ci && npm run build`; browser em 1280px e 390×844. Fixture CSV de quatro linhas e backend falso loopback permitiram aceitar, corrigir, rejeitar e pular. A lista omitiu `fields`; detalhe mostrou somente `text`. CLI `dataset prepare` incluiu 2 exemplos e reportou `skipped=1`, `rejected=1`, `unreviewed=0`. Reenvio da mesma decisão retornou HTTP 200 com `duplicate=true` e acrescentou somente um evento. Após alterar uma linha fixture, revisão retornou HTTP 409 e a lista indicou `stale=true`, sem ação disponível.
- **Comandos adicionais:** `python -m py_compile src/finlabel/review.py src/finlabel/training/dataset.py src/finlabel/web/app.py`; `git diff --check`.
- **Limitações:** tarefas continuam sendo criadas pelo CLI; a tela seleciona tarefas existentes. Nenhum teste automatizado foi adicionado ou executado; nenhum peso foi baixado/carregado e nenhum dado real foi usado.

### Ajustes da revisão — 2026-10-20

- A fila importa `task_file_path`; o endpoint de detalhe aplica `MAX_API_RESPONSE_BYTES` e responde HTTP 422 com erro limitado se os campos selecionados excederem 1 MiB.
- A chave idempotente de correção inclui o rótulo final configurado, serializado junto com a identidade run/suggestion/action. Retentar a mesma correção mantém a chave; escolher outro rótulo gera uma chave distinta.
- Ajustes registrados no commit `c080413bc1d1fe12f2a5aeda4b3b99635d0af41f` da branch `codex/react-labeling`.
- **Probe sintético:** `GET /api/label/tasks` e `/api/label/suggestions` responderam 200; a fila não incluiu `fields`; detalhe com fixture maior que 1 MiB respondeu 422 com corpo de 72 bytes. Correção repetida gerou mesma chave, recebeu duplicata no retry sem segundo evento; rótulo corrigido diferente gerou chave/evento novos. Nenhum teste automatizado foi executado.
- Revisão independente: os três achados foram corrigidos, sem findings restantes. A fila resolve a tarefa, detalhe aplica limite de payload e a chave da decisão de correção inclui o rótulo final. Branch integrada no cumulativo após aprovação.
