# Agenda semanal do TCC

Rodrigo Mialichi Triboni — Engenharia de Controle e Automação — UFU

Tema: Redes bayesianas e utilidade esperada aplicadas à seleção de next best action em sistemas automatizados de decisão.

Agenda baseada nas etapas A a H do projeto enviado. As datas abaixo são uma proposta com início em 28/09/2026 e fechamento em dezembro, sujeita ao prazo oficial de entrega e defesa e à disponibilidade semanal. Não representam o calendário oficial da UFU. Etapas já concluídas podem liberar tempo para revisão.

## Rotina semanal sugerida

Reservar inicialmente três blocos de trabalho, totalizando cerca de 5 horas por semana. Essa é uma hipótese de organização, não uma estimativa garantida de esforço; semanas de modelagem podem exigir mais tempo.

- Bloco 1 — 1h30: leitura ou planejamento da tarefa da semana.
- Bloco 2 — 2h: execução da análise, código ou revisão prevista.
- Bloco 3 — 1h30: escrever sobre o que foi feito, guardar resultados e registrar dúvidas.

Ao terminar cada semana, registrar a entrega, o que ficou pendente e a próxima tarefa. Propor alinhamentos com o orientador nas semanas 1, 4, 8, 10 e 12, conforme a disponibilidade dele.

## Metas por semana

### Semana 1 — 28 de setembro a 4 de outubro

Etapa A — Delimitação e protocolo

- [ ] Revisar a pergunta de pesquisa e os objetivos com o orientador.
- [ ] Confirmar o prazo de entrega e defesa e os requisitos do curso.
- [ ] Definir o desfecho, a codificação das classes e o protocolo de validação antes de treinar modelos.
- [ ] Organizar pastas para referências, dados, código, resultados e texto.

Entrega: uma página com pergunta, escopo e protocolo experimental preliminar.

### Semana 2 — 5 a 11 de outubro

Etapas A e B — Revisão e entendimento da base

- [ ] Ler e fichar duas referências prioritárias sobre redes bayesianas e teoria da decisão.
- [ ] Obter o German Credit Data e documentar origem, variáveis e significado das classes.
- [ ] Separar os dados conforme o protocolo; explorar os dados destinados ao desenvolvimento sem usar o teste para orientar ajustes.
- [ ] Registrar distribuições, possíveis problemas de qualidade e proporção das classes.

Entrega: dicionário de dados, análise exploratória inicial e fichamentos.

### Semana 3 — 12 a 18 de outubro

Etapa B — Preparação dos dados

- [ ] Implementar o pipeline de pré-processamento.
- [ ] Definir o tratamento de variáveis categóricas e a discretização quando necessária.
- [ ] Garantir que transformações sejam ajustadas somente no treino de cada partição.
- [ ] Escrever a subseção de dados e pré-processamento.

Entrega: pipeline executável e descrição das transformações.

### Semana 4 — 19 a 25 de outubro

Etapa C — Modelo de referência

- [ ] Implementar a regressão logística como baseline.
- [ ] Avaliar discriminação e calibração nos dados de validação.
- [ ] Aplicar calibração conforme o protocolo, sem utilizar o teste final para ajuste.
- [ ] Registrar configuração, sementes e resultados preliminares.

Entrega: baseline reproduzível e primeira tabela de métricas de validação.

### Semana 5 — 26 de outubro a 1 de novembro

Etapas C e D — Rede inicial e ações

- [ ] Definir e justificar uma estrutura inicial da rede bayesiana.
- [ ] Estimar suas probabilidades com suavização ou priores documentados.
- [ ] Executar inferências em casos de exemplo.
- [ ] Esboçar ações admissíveis e custos e benefícios demonstrativos.

Entrega: primeira rede funcional, desenho do grafo e rascunho das ações.

### Semana 6 — 2 a 8 de novembro

Etapa C — Comparação de estruturas

- [ ] Implementar uma estratégia de aprendizado de estrutura.
- [ ] Comparar a estrutura aprendida e a inicial usando o mesmo protocolo.
- [ ] Avaliar calibração e selecionar a configuração nos dados de desenvolvimento.
- [ ] Escrever as escolhas de modelagem e suas justificativas.

Entrega: comparação das redes e configuração selecionada para avaliação final.

### Semana 7 — 9 a 15 de novembro

Etapa D — Seleção de ações

- [ ] Finalizar e documentar a matriz de utilidade.
- [ ] Explicitar as hipóteses da simulação, pois a base não contém resultados históricos para cada ação.
- [ ] Implementar o ranking por utilidade esperada, a segunda melhor ação e a diferença de utilidade.
- [ ] Conferir os cálculos com exemplos pequenos calculados manualmente.

Entrega: mecanismo de decisão funcional e matriz de utilidade explicada no texto.

### Semana 8 — 16 a 22 de novembro

Etapa E — Avaliação dos resultados

- [ ] Executar a avaliação final conforme o protocolo, após fechar os ajustes.
- [ ] Comparar ROC-AUC, Brier score, log loss e diagramas de calibração; incluir PR-AUC quando pertinente.
- [ ] Comparar utilidade média, custo esperado e distribuição das ações com a política de limiares do baseline.
- [ ] Separar as conclusões sobre previsão das conclusões sobre a decisão simulada.

Entrega: tabelas e figuras da comparação principal.

### Semana 9 — 23 a 29 de novembro

Etapa E — Sensibilidade e robustez

- [ ] Variar custos e benefícios em cenários previamente definidos.
- [ ] Identificar quando a ação recomendada muda.
- [ ] Avaliar o comportamento com evidências incompletas.
- [ ] Consolidar limitações e discutir os resultados com o orientador.

Entrega: análise de sensibilidade e robustez e metodologia validada para seguir ao protótipo.

### Semana 10 — 30 de novembro a 6 de dezembro

Etapa F — Protótipo demonstrativo

- [ ] Montar uma interface simples após concluir a validação metodológica.
- [ ] Exibir evidências, risco estimado, ranking de ações e justificativa.
- [ ] Conferir se a interface reproduz as saídas do código experimental.
- [ ] Capturar exemplos para a monografia e apresentação.

Entrega: demonstração funcional do fluxo completo.

### Semana 11 — 7 a 13 de dezembro

Etapa G — Monografia completa

- [ ] Integrar os trechos escritos ao longo das semanas.
- [ ] Finalizar discussão, limitações e conclusão, sem pressupor superioridade do modelo proposto.
- [ ] Revisar introdução e objetivos à luz dos resultados obtidos.
- [ ] Encaminhar a versão completa ao orientador, conforme combinado.

Entrega: primeira versão integral da monografia.

### Semana 12 — 14 a 20 de dezembro

Etapa H — Revisão e apresentação

- [ ] Incorporar as correções recebidas.
- [ ] Conferir citações, referências, figuras e formatação exigida pelo curso.
- [ ] Executar o projeto a partir das instruções de reprodução e registrar versões das dependências.
- [ ] Preparar slides e ensaiar dentro do tempo previsto para a defesa.

Entrega: texto revisado, código reproduzível e apresentação ensaiada.

### Semana 13 — 21 a 27 de dezembro

Reserva condicionada ao prazo oficial

- [ ] Resolver pendências finais, se o calendário do curso permitir.
- [ ] Fazer a conferência final dos arquivos de entrega.
- [ ] Realizar novo ensaio e organizar backups.

Entrega: pacote final. Não depender desta semana para atividades essenciais; se o prazo oficial for anterior, antecipar e redistribuir as etapas.

## Ajustes em relação ao quadro mensal do projeto

A sequência metodológica foi preservada. Como a proposta começa no fim de setembro, o protótipo passa para o início de dezembro, após a validação de novembro. A redação permanece contínua, com uma pequena atualização a cada semana. O cronograma deverá ser ajustado quando forem confirmados o prazo oficial, as horas disponíveis e as etapas já concluídas.

## Registro de acompanhamento

Copiar este bloco a cada semana:

- Semana:
- Entrega concluída:
- Arquivo ou resultado gerado:
- Pendência:
- Dúvida para o orientador:
- Primeira tarefa da próxima semana:
