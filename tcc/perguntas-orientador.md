# Perguntas para o orientador

Levar na próxima conversa. Registrar a resposta embaixo de cada pergunta, com data.

## Tema e método

1. Rotulagem assistida de dados financeiros com modelo leve, como biblioteca reutilizável, representa a ideia aprovada? (decisão 7)
2. O TCC deve exigir ajuste fino (fine-tuning) de fato, ou comparar ajuste fino com um modelo pré-treinado sem ajuste?
3. Qual baseline e quais métricas são adequados para avaliar a qualidade dos rótulos? (proposta: regressão logística; acurácia, macro-F1, Brier, erro de calibração e cobertura)
4. A base UCI Default of Credit Card Clients serve como segunda base? Que parte do fluxo deve ser repetida nela?
5. Quarentena automática e registro de auditoria bastam como governança demonstrada, sem alegar conformidade normativa?
6. Que evidências e método de avaliação cabem nas regras e no prazo do curso?

## Nuvem (decisão 8)

7. Posso usar modelos na nuvem (Vercel AI Gateway) em vez de só modelos locais? Isso muda o princípio de "nenhum dado sai da máquina". Se sim, só com dados públicos ou sintéticos?
   - **Resposta (09/11/2026):** sim, o coordenador autorizou colocar os dados na nuvem (decisão 8).

## Primeiro uso sem rótulos aplicados

Hoje, na primeira execução, toda previsão vai para quarentena: ainda não existe calibrador, e ele só passa a valer depois que um modelo é treinado e promovido. Seguro, mas o primeiro uso não rotula nada.

| Opção | O que muda | Ganho | Risco |
|---|---|---|---|
| A. Manter | Nada | Máxima cautela | Primeiro uso não rotula nada |
| B. Usar o calibrador do modelo-base | A rotulagem usa o calibrador já gerado para o modelo sem ajuste | Rotula desde o primeiro ciclo | Modelo não adaptado passa a aplicar rótulos |
| C. Passo explícito de calibração | Novo comando que calibra e valida sem treinar | Usuário vê a evidência antes de ligar a rotulagem | Mais um passo para documentar e testar |

8. Qual opção seguir? Recomendação provisória: **C**, depois de rodar o ciclo uma vez em dados reais para ver a cobertura que o modelo-base calibrado alcança.
