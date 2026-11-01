# 02: Definir adapter para modelos locais

**Status:** ready-for-human

**What to build:** Integrar um modelo leve local com contrato que aceite registros financeiros serializados e produza sugestões de rótulos em formato estruturado.

## Bloqueadores de decisão

- Modelo Gemma e variante exata.
- Hardware mínimo e estratégia de quantização.
- Inferência base versus fine-tuning (e método de ajuste).
- Formato de serialização de linhas tabulares e política para colunas sensíveis.
- Esquema de saída, tratamento de recusa/saída inválida e modo de revisão humana.

Não começar treinamento por cliente até resolver esses itens e alinhar o protocolo experimental.


## Comments

### 2026-10-20 — Experimento sintético autorizado

Executado treino exploratório local com Qwen2.5-0.5B-Instruct, Apache-2.0, revisão `7ae557604adf67be50417f59c2c2f167def9a775`, em Apple M4/16 GB via MPS. Dataset artificial: 72 exemplos de treino e 24 reservados; 38 sugestões aceitas e 34 corrigidas contra oráculo sintético. Resultado reservado: base 9/24 (37,5%, macro-F1 0,300), LoRA 17/24 (70,8%, macro-F1 0,706); 10 casos melhoraram e 2 regrediram. Adapter e relatório: `.scratch/biblioteca-rotulagem-financeira/experiments/qwen25-05b-synthetic-2026-10-20/RESULTS.md`.

Este ensaio não resolve a escolha de modelo para o produto nem autoriza dados de clientes. A revisão foi comparada automaticamente ao oráculo sintético, não feita por anotador independente. Foi necessário aplicar o chat template do Qwen; o backend genérico atual não o aplica. Manter esses pontos para decisão humana antes de estudo com dados reais.

### 2026-10-20 — Revisão independente do experimento

Revisão read-only sem achados críticos. O conjunto reservado usa templates escritos separadamente, mas compartilha vocabulário e padrões semânticos com o treino; portanto, não sustenta alegação de generalização independente ou para dados reais. A revisão dos 72 rótulos foi simulada por comparação automática com o oráculo sintético.

Após a revisão, `RESULTS.md` e `PROTOCOL.md` explicitam esses limites e registram o commit local do FinLabel. `scripts/verify_experiment.py` foi reforçado para reconciliar os 72 eventos (38 aceitos e 34 corrigidos), alinhar previsões aos dados e rótulos reservados e recalcular as métricas salvas. A checagem executada em 20/10/2026 confirmou esses valores e a presença do adapter. Reexecutar `review_synthetic.py` no mesmo run manteve os 72 eventos, sem duplicações. A linha de comando completa do treino não foi capturada; reprodução requer o checkout local no commit registrado e ajuste do caminho editável no arquivo de dependências quando necessário.
