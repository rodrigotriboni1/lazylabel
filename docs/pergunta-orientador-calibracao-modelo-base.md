# Pergunta para o orientador: calibração do modelo-base antes da primeira promoção

- **Data:** 2026-11-01
- **Estado:** pergunta aberta, rascunho para a próxima conversa. Nenhuma decisão tomada.
- **Relacionados:** [ADR-0004](adr/0004-rotulagem-autonoma-com-quarentena.md), [ADR-0005](adr/0005-treino-com-gates-promocao-e-rollback.md), [PRD](prd/finlabel.md), [ciclo de treino verificado](../codigo/finlabel/docs/verified-training-cycle.md).

## O problema em uma frase

Quem instala o FinLabel e roda `finlabel label` pela primeira vez não tem nenhum rótulo aplicado: toda previsão vai para quarentena com o motivo `uncalibrated`, porque ainda não existe calibrador, e o calibrador só passa a valer para rotulagem depois que um candidato é treinado e promovido.

## Como funciona hoje

Segundo o README e `docs/verified-training-cycle.md` (não reverifiquei no código nesta nota):

1. O backend Transformers não produz confiança calibrada por conta própria.
2. A rotulagem só aplica um rótulo se a confiança calibrada passar do limite da política (ADR-0004). Sem calibrador, tudo é quarentena.
3. O ciclo `finlabel run` ajusta calibradores para o candidato **e** para o incumbente (antes da primeira promoção, o incumbente é o modelo-base exato) usando a mesma partição de calibração congelada.
4. A inferência ativa, porém, carrega o calibrador gravado junto com o **adaptador promovido**. Enquanto nada foi promovido, o calibrador do modelo-base existe como evidência, mas não é usado para aplicar rótulos.
5. A promoção exige rótulos de referência confiáveis, `training-gate.json`, política de rotulagem e política de promoção, e todos os gates precisam passar.

Resultado: o primeiro valor útil só aparece depois de um ciclo completo com dados de referência. Isso é seguro, mas contradiz o objetivo de facilitar o uso.

## As opções

| Opção | O que muda | Ganho | Risco |
|---|---|---|---|
| **A. Manter** | Nada. A primeira promoção continua sendo o pré-requisito. | Máxima cautela; o ADR-0004 fica intacto. | O primeiro uso não rotula nada; difícil de demonstrar e de ensinar. |
| **B. Usar o calibrador do modelo-base** | Permitir que a rotulagem use o calibrador do incumbente (modelo-base) já gerado pelo ciclo, com a mesma política e o mesmo limite. | Rotulagem útil desde o primeiro ciclo, sem exigir promoção. | A qualidade depende só da partição de calibração; um modelo-base não adaptado passa a aplicar rótulos. |
| **C. Passo explícito de calibração** | Novo comando que ajusta e valida o calibrador do modelo-base num holdout confiável, sem treinar. | Separa "calibrar" de "treinar"; o usuário vê a evidência antes de ligar a rotulagem. | Mais um passo e mais uma superfície a documentar e testar. |

## Perguntas para decidir

1. Aplicar rótulos com o **modelo-base calibrado**, sem adaptação treinada, está dentro do escopo do TCC, ou o escopo exige que só um modelo promovido rotule?
2. Se sim, qual é o **mínimo de evidência**: tamanho do holdout, erro de calibração máximo, cobertura mínima? (O FinLabel não presume limite universal.)
3. A contribuição do TCC deve incluir "rotular desde o primeiro dia" ou apenas "melhorar com evidência e poder reverter"? Isso muda o que pode ser afirmado na conclusão.
4. Qual baseline simples (por exemplo, regressão logística) precisa ser comparado antes de afirmar que o modelo-base calibrado é útil?

## O que não sabemos

- Não há medida em dados reais: o único experimento é sintético (Qwen2.5-0.5B, 24 exemplos, 70,83% de acurácia), e o ciclo de treino foi exercitado só com stub.
- Não sabemos se um modelo-base não adaptado atinge cobertura útil depois de calibrado em South German Credit.

## Recomendação provisória (a confirmar)

Começar por **C**: é a opção que mantém a falha segura do ADR-0004 e ainda dá um primeiro resultado útil. Antes de qualquer implementação, rodar o ciclo uma vez em dados reais para ver a cobertura que o modelo-base calibrado realmente alcança.
