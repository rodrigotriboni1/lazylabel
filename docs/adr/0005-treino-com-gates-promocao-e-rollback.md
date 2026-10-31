# ADR-0005: Ciclo de treino com rótulos confiáveis, gates, promoção e rollback

- **Status:** Aceita
- **Data:** 2026-10-31 (decisão de 2026-10-21; rollback concluído em 2026-10-26)
- **Escopo:** FinLabel

## Contexto

Treinar com as próprias previsões do modelo contaminaria a avaliação e degradaria silenciosamente o modelo. Ao mesmo tempo, promover adapters manualmente contraria a decisão de autonomia ([ADR-0004](0004-rotulagem-autonoma-com-quarentena.md)).

## Decisão

`finlabel run` rotula e depois executa um ciclo de treino em lote:

1. Só **rótulos confiáveis** de uma fonte registrada (`supervision add`, com proveniência) alimentam treino e avaliação; a coluna de rótulo nunca entra em `input_columns`.
2. Partições treino/calibração/holdout são **congeladas** e verificadas byte a byte.
3. Exige `training-gate.json` (modelo, licença, hardware, política de dados, protocolo, `authorized: true`), política de rotulagem e `promotion-policies/<task>.json`.
4. Candidato (só partição de treino) e incumbente são avaliados no **mesmo holdout** com calibradores próprios.
5. **Todos** os gates devem passar para promover; falha mantém o modelo ativo; pré-requisito ausente registra ciclo bloqueado.
6. Saúde pós-promoção reavaliada contra `rollback_monitor_limits`; violação restaura a versão anterior verificada (primeira promoção não tem alvo de rollback e falha fechada).
7. Eventos são hash-vinculados num registry com lock de arquivo e recuperação por replay. Não há botão manual de promoção.
8. `finlabel train` permanece como backend explícito, **sem** promover.

## Consequências

- (+) Promoção rastreável e reproduzível; evidência por linha mínima e sem dados brutos.
- (+) Falha fechada em toda ausência de evidência.
- (−) Muita configuração prévia (gates, política, rótulos confiáveis).
- (−) Hashes dão integridade dentro do workspace, não atestação criptográfica do avaliador; corrida possível entre validação do gate e a decisão se o arquivo for editado externamente.
- (−) Rotular primeiro e treinar depois: a promoção só afeta execuções seguintes.

## Riscos / pontos abertos

O ciclo **não foi executado com rótulos confiáveis reais**; a verificação HTTP de treino usou stub. O adapter histórico do experimento Qwen não pode ser promovido (sem identidade/calibração atuais).

## Evidência

`docs/verified-training-cycle.md`; `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md`; relatório final §4–5.
