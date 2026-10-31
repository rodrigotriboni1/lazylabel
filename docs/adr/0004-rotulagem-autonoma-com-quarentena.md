# ADR-0004: Rotulagem autônoma com confiança calibrada e quarentena (sem revisão humana por registro)

- **Status:** Aceita no projeto; **pendente de validação com o orientador** (ver Riscos)
- **Data:** 2026-10-31 (decisão de 2026-10-21)
- **Escopo:** FinLabel
- **Substitui:** o fluxo de revisão humana obrigatória do MVP (`.scratch/biblioteca-rotulagem-financeira/2026-10-19-design-mvp.md`, `docs/superpowers/specs/2026-10-20-supervised-training-lifecycle-design.md`)

## Contexto

O MVP inicial pedia que uma pessoa aceitasse, corrigisse ou rejeitasse cada sugestão (`ReviewLog`). Isso não escala e foi a governança central da proposta inicial. A spec de 2026-10-21 decidiu evoluir para autonomia dentro de uma política configurada.

## Decisão

- Após configurar tarefa e política, cada registro termina **aplicado** ou em **quarentena**; ninguém aprova linha a linha.
- Aplica-se uma previsão somente se: JSON/rótulo válidos, regras determinísticas satisfeitas, origem atual e **confiança calibrada** acima do limite da política.
- O backend Transformers bruto devolve `calibrated_confidence=None`; sem calibrador validado a previsão fica em quarentena. Confiança autorreportada pelo modelo é rejeitada.
- Pontuação por `label_json_mean_log_likelihood_v2` (incompatível com calibrações v1).
- Sem política, fonte confiável ou gates: abster-se. Nunca há limite universal presumido.
- `ReviewLog` e artefatos antigos continuam legíveis, fora do fluxo atual.

## Consequências

- (+) Fluxo repetível e auditável por lote, com motivos codificados de quarentena.
- (+) O modelo não valida a si mesmo.
- (−) Exige calibrador e política por tarefa antes de qualquer rótulo ser aplicado; em configuração incompleta, cobertura é zero.
- (−) Cada classe custa uma passagem extra do modelo no cálculo de escores.
- (−) A proposta original destacava revisão humana como eixo de governança; essa decisão a contradiz.

## Riscos / pontos abertos

- **Não há evidência em dados reais** de que a calibração mantém erro aceitável; só smoke com 24 exemplos sintéticos (acurácia 70,83%, macro-F1 0,7056).
- Confirmar com o orientador que "autonomia com quarentena" substitui "revisão humana" como eixo demonstrado.

## Evidência

`docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md`; README (contrato de previsão); `docs/local-model-inference-2026-10-26.md`; relatório final §5.
