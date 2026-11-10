# Decisões do projeto

As escolhas que moldam o LazyLabel e o TCC, em uma linha cada, com o motivo e o custo. Uma decisão nova entra no fim, numerada.

| # | Decisão | Situação |
|---|---|---|
| 1 | Tudo roda na máquina do usuário; nenhum dado sai dela | Substituída pela 8 (local continua como opção) |
| 2 | Fontes CSV e SQLite abertas só para leitura | Aceita |
| 3 | Código em camadas (domínio no centro, adaptadores em volta) | Aceita |
| 4 | Rotulagem autônoma: cada registro é aplicado ou vai para quarentena | Aceita |
| 5 | Treino só com rótulos confiáveis; promoção só se todos os gates passam; rollback automático | Aceita |
| 6 | Análises calculadas de forma exata (Decimal), a partir de um plano revisável | Aceita |
| 7 | Tema do TCC passa a ser a biblioteca LazyLabel, avaliada por reutilização | Proposta · falta o orientador |
| 8 | Usar modelos na nuvem pela Vercel (AI Gateway) e painel feito com json-render | Aceita (09/11/2026, autorizada pelo coordenador) |

## 1. Tudo local

- **Por quê:** dados financeiros são sensíveis; a biblioteca deve servir a quem não pode enviar registros a terceiros.
- **Como:** modelos locais (Transformers, LoRA) como dependência opcional; o modelo vê só as colunas da tarefa, nunca linhas inteiras; painel só em `localhost`, com checagem de Host, Origin e CSRF; logs com referências opacas, sem linhas.
- **Custo:** qualidade limitada a modelos leves que cabem no computador do usuário.
- **Hoje:** substituída pela decisão 8. Rodar tudo local continua possível, mas deixou de ser obrigatório.

## 2. Fontes só leitura

- **Por quê:** ler os dados sem nenhum risco de alterá-los.
- **Como:** `CsvSource` e `SqliteSource` abrem a origem em modo leitura; tudo que o LazyLabel produz vai para `.lazylabel/`. Tipos de data e número são mapeados à mão (`source set-type`).
- **Custo:** não escreve de volta; só duas fontes hoje.

## 3. Camadas

- **Por quê:** trocar modelo, fonte ou interface sem reescrever as regras. É o que sustenta a tese de reutilização.
- **Como:** `domain` ← `application` ← `adapters` (CLI, HTTP, fontes, modelos) ← `bootstrap`. Testes de arquitetura impedem dependência na direção errada. Módulos antigos ficam como fachadas.
- **Custo:** mais arquivos.
- **Atualização (09/11/2026):** as fachadas de compatibilidade (`lazylabel.cli`, `lazylabel.labeling.*` etc.) foram removidas; não havia usuários externos. Correspondência dos caminhos em `codigo/lazylabel/docs/architecture/clean-hexagonal-module-map.md`.

## 4. Aplicado ou quarentena

- **Por quê:** ninguém revisa linha a linha; na dúvida, o sistema se abstém.
- **Como:** só aplica se a saída é válida, as regras passam, a fonte está atual e a confiança **calibrada** supera o limite da política. Confiança declarada pelo próprio modelo é ignorada.
- **Custo:** sem calibrador, tudo vai para quarentena na primeira execução (ver `perguntas-orientador.md`).

## 5. Treino com gates

- **Por quê:** só trocar de modelo com evidência, e poder voltar atrás.
- **Como:** `lazylabel run` rotula e depois treina com rótulos confiáveis em partições congeladas (treino, calibração, holdout); candidato e modelo atual são comparados no mesmo holdout; tudo fica num registro com hash; não há botão manual de promoção.
- **Custo:** exige configurar autorização, políticas e rótulos antes de qualquer treino.

## 6. Análise exata

- **Por quê:** números financeiros não podem variar por arredondamento ou pelo modelo.
- **Como:** um plano JSON (escrito à mão ou sugerido por modelo, que vê só nomes de colunas) é executado com `Decimal`; o resultado guarda plano, tabela, gráfico e hashes.
- **Custo:** só operações simples (contagem, soma, média, participação).

## 7. Novo tema do TCC

- **Pergunta proposta:** até que ponto um fluxo configurável de rotulagem financeira pode ser reaplicado a outras tarefas e bases sem alterar o núcleo, mantendo rastreabilidade e controle de qualidade?
- **Evidência planejada:** reconfigurar a mesma tarefa e aplicar a uma segunda base (candidata: UCI Default of Credit Card Clients).
- **Falta:** aprovação do orientador; baseline e métricas; atualizar o protocolo.

## 8. Nuvem pela Vercel

- **Decisão (09/11/2026):** dados e modelos podem ir para a nuvem. Autorizado pelo coordenador.
- **Como:** modelos pelo Vercel AI Gateway (API compatível com OpenAI, chave em `AI_GATEWAY_API_KEY`); painel feito com json-render + shadcn. O modelo local continua como opção.
- **Limites:** a Vercel não treina nem hospeda pesos próprios. Um modelo ajustado nosso precisa ser treinado num provedor (por exemplo, OpenAI ou Azure) e ligado ao Gateway com chave própria (BYOK).
- **Continua valendo:** o modelo recebe só as colunas da tarefa; logs sem linhas; quarentena quando não há confiança calibrada (decisão 4).
