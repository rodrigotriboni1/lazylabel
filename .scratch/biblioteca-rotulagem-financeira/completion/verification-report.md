# FinLabel — relatório de conclusão e verificação

Data: 26/10/2026  
Branch de integração: `codex/finlabel-autonomous-mvp`  
Branch da etapa do painel: `codex/finlabel-autonomous-panel`

## Branches para revisão por etapa

| Entrega | Branch | Commit |
|---|---|---|
| Dashboard, KPIs e heatmap | `codex/finlabel-dashboard-redesign` | `02671dc` |
| Contratos de rotulagem autônoma | `codex/finlabel-autonomous-contract-tests` | `84e7fd5` |
| Dados confiáveis e ciclo de treino | `codex/finlabel-trusted-training-completion` | `c962b26` |
| Rollback pós-promoção | `codex/finlabel-training-rollback` | `582395a` |
| Modelo local | `codex/finlabel-local-model-compat` | `28c116d` |
| Painel autônomo | `codex/finlabel-autonomous-panel` | `25d8783` |
| Análise e privacidade E2E | `codex/finlabel-analysis-e2e` | `bb282f5` |
| Verificação final | `codex/finlabel-full-verification` | `2b11cca` |

## Entregue

- Painel React com identidade visual limpa, KPIs contextuais e heatmap categoria × período; CSV e SQLite continuam somente leitura.
- Fluxo autônomo compartilhado entre CLI e painel: saídas válidas podem ser aplicadas pela política, casos incertos são colocados em quarentena e treino usa somente rótulos confiáveis.
- Treino em lote, avaliação em holdout congelado e promoção/rollback automáticos condicionados a políticas e evidências locais. Sem configuração válida, o fluxo falha fechado.
- Painel de rotulagem sem decisões manuais por registro, histórico agregado e diagrama acessível de sete etapas no treinamento.
- Endpoints locais de saúde e metadados de fontes, com payload limitado ao esquema; `model-status` apresenta histórico validado sem expor caminhos do adapter.

## Verificação automatizada

- Python: `PYTHONPATH=src ../dashboard-redesign/.venv/bin/python -m pytest -q` — **128 passaram, 17 subtestes passaram** (após o teste de integridade do journal na API).
- React/Vitest: `npm test -- --run` — **10 passaram**.
- `npm run build` — passou. O bundle principal tem 710,61 kB minificado e o Vite emite aviso de tamanho; build produz assets locais corretamente.
- `npm run lint` — exit 0; restaram avisos de export Fast Refresh em `button.tsx`/`badge.tsx` e `set-state-in-effect` em Training, Labeling e Analysis.
- `python -m compileall -q src/finlabel` e `git diff --check` — passaram.

## Revisão independente

A revisão encontrou uma leitura direta do journal de decisões no endpoint de autonomia, que deixava uma janela para exibir um evento adulterado após a validação inicial. O endpoint agora obtém os eventos via `ModelRegistry.history()`. Um teste simula a alteração do journal após a abertura do registry e confirma que a API falha fechada em vez de afirmar uma decisão adulterada. O revisor confirmou que o ajuste fecha o achado, sem apontar outro problema nesse trecho.

## Revisão visual manual

Rotas conferidas diretamente e por navegação em 1440×900 e 390×844: `/`, `/analysis`, `/monitor`, `/labeling`, `/training`, `/review` e uma análise salva em `/analysis/<run_id>`. As páginas renderizam após refresh. Não foi observado overflow horizontal no documento; tabelas de valores têm rolagem horizontal contida. A navegação móvel é fixa no rodapé, e o conteúdo restante segue acessível por rolagem. O diagrama mantém as sete etapas e indica o estado atual na árvore acessível.

Capturas: `../../finlabel-completion-2026-10-26/evidence/` (desktop/mobile por rota; inclui capturas em tela cheia de análise e treinamento).

## Smoke do modelo local

Modelo `Qwen/Qwen2.5-0.5B-Instruct`, revisão `7ae557604adf67be50417f59c2c2f167def9a775`, carregado offline em Apple MPS via Transformers/PEFT. Em 24 exemplos de holdout sintético, gerou 24 saídas válidas, 70,83% de acurácia exata e macro-F1 0,7056 em 12,099 s. Evidência: `../experiments/qwen25-05b-synthetic-2026-10-20/results/live-inference-2026-10-26-integration-final.json` e `codigo/finlabel/.worktrees/autonomous-mvp/docs/local-model-inference-2026-10-26.md`.

Esse smoke demonstra inferência local e formatação estruturada, não desempenho financeiro nem validação em clientes. O adapter histórico não atende aos artefatos de identidade/calibração do fluxo autônomo e não foi promovido. Não houve treino novo nem acesso a dados reais.

## Integração e limite de revisão

Branches por entrega ficam disponíveis para revisão, com integração em `codex/finlabel-autonomous-mvp`. `main` permanece inalterada. Revisão independente do diff da etapa do painel está registrada na conversa e deve ser incorporada aqui após a devolutiva do agente.
