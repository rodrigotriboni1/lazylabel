# Protocolo experimental preliminar

Versão 0.1 — 27/09/2026. Proposta de execução derivada do projeto enviado, ainda sujeita à discussão com o orientador. Nenhum dado foi baixado ou modelo treinado nesta etapa.

## Pergunta e critérios de avaliação

Avaliar separadamente a estimação probabilística de risco e a seleção de ações sob uma matriz de utilidade demonstrativa. Não adotar superioridade da rede bayesiana como requisito de sucesso do TCC.

Para a previsão, usar Brier score como critério principal de seleção no desenvolvimento, acompanhado de ROC-AUC, log loss e diagrama de calibração. Brier e log loss avaliam a qualidade probabilística e não isolam calibração; interpretar o diagrama em conjunto. Reportar average precision como resumo complementar da curva precisão e revocação, identificando essa definição no texto.

Para a decisão, reportar utilidade média calculada com os rótulos observados sob a matriz simulada, utilidade esperada prevista, custo quando houver matriz de custos definida e distribuição das ações. Distinguir a previsão de utilidade da avaliação feita com os rótulos: nenhuma das duas mede o efeito real de uma intervenção de crédito.

## Base e variável alvo

Decisão registrada em 19/10/2026: usar **South German Credit**, a versão corrigida publicada na UCI, conforme conversa de Rodrigo com o orientador. A base tem 1000 registros e 20 variáveis preditoras. Preservar o arquivo original com as categorias codificadas e documentar os nomes e significados a partir do código de leitura e da tabela da própria base.

A variável alvo é `kredit` (`credit_risk`): o código bruto `0` representa risco ruim (`bad`) e `1` representa risco bom (`good`), conforme o código de leitura associado à versão corrigida. Para facilitar a interpretação do estudo, propõe-se recodificar para `y=1` como risco ruim e `y=0` como risco bom; deixar essa transformação explícita no pipeline e nos resultados.

A amostra é estratificada e contém 300 casos ruins e 700 bons; a frequência amostral não deve ser apresentada como prevalência populacional. Não equiparar automaticamente o rótulo a inadimplência em um horizonte temporal definido.

Registrar fonte, data de obtenção, hash do arquivo, número de linhas, dicionário, mapeamento e proporção observada de classes. A proporção é uma verificação descritiva, não uma métrica de desempenho.

## Separação e prevenção de vazamento

Proposta: divisão estratificada em 80% para desenvolvimento e 20% para teste final, com semente 42 e índices salvos. Havendo duplicatas ou registros relacionados, revisar o desenho antes de dividir, evitando que casos equivalentes apareçam nos dois lados.

No desenvolvimento, usar cinco partições estratificadas compartilhadas entre modelos. Todo pré-processamento aprendido, discretização, seleção de variáveis e aprendizado de estrutura deve ocorrer dentro do treino de cada partição. O conjunto de teste não orienta análise exploratória, escolhas de modelo, limiares ou utilidades.

Comparar probabilidades brutas e calibração sigmoidal. Quando houver calibração, gerar as previsões para ajustar o calibrador em subdivisões internas do treino, sem incluir a partição externa usada para avaliar a configuração. Após selecionar a configuração pela média do Brier nas cinco partições, reajustá-la no desenvolvimento completo usando a mesma separação interna para calibração.

Antes de abrir o teste final, registrar a configuração, os cenários de utilidade, os limiares, as métricas e os testes de robustez. Se um erro de implementação exigir repetir a avaliação, registrar a correção e não apresentar o teste como intocado após essa consulta.

## Modelos comparados

1. Regressão logística com pré-processamento adequado às variáveis.
2. Rede bayesiana com estrutura inicial justificada pelo conhecimento do problema.
3. Rede bayesiana com estrutura aprendida apenas nos dados de treino.

Documentar suavização das probabilidades condicionais e limites da complexidade da rede. Como ponto de partida para conter o esforço, propor no máximo dois pais por nó e um único critério de busca, BIC, sujeito à revisão antes dos experimentos. Definir previamente uma grade pequena de configurações. Não acrescentar modelos apenas para tentar obter vantagem no teste.

## Decisão e utilidade

No caso inicial, usar EU(a|x) = soma_y P(y|x) U(a,y), tratando y como o estado de risco observado e adotando explicitamente a hipótese simplificadora de que sua distribuição não muda com a ação na simulação.

Não estimar P(y|a,x) a partir desta base: ela não contém os resultados das diferentes ações. Ações como solicitar informação ou garantia e análise manual precisam de hipóteses explícitas sobre custo e resultado, sem atribuir benefício comprovado. Começar por aprovar e rejeitar e acrescentar ações intermediárias quando suas hipóteses estiverem documentadas.

Comparações propostas: regressão logística com limiar; regressão logística com utilidade esperada; rede bayesiana com limiar; rede bayesiana com utilidade esperada. Assim, é possível examinar a contribuição do modelo de risco e a do critério de decisão separadamente. Usar a mesma matriz em todas as avaliações comparáveis. Em um caso binário simples, o máximo de utilidade pode equivaler a um limiar; essa equivalência é um resultado a explicar, não uma falha.

Definir limiar fixo de 0,5 como referência simples e um limiar selecionado no desenvolvimento pela utilidade média simulada. Registrar como cada política mapeia probabilidades para ações. No caso de ações adicionais, explicitar que uma comparação com política binária também envolve conjuntos diferentes de ações.

Guardar a ação escolhida, o ranking, a segunda opção e a diferença de utilidade. Documentar um critério determinístico para empates antes da avaliação. Valores monetários ou utilidades serão hipotéticos, não estimativas de retorno financeiro real.

## Sensibilidade e evidências incompletas

Propor cenários com variação de 10%, 25% e 50% nos custos e benefícios não nulos, mantendo também o cenário central. Reportar utilidade e proporção de recomendações alteradas; cenários não serão selecionados pelo resultado mais favorável.

Propor remoção simulada de 10%, 20% e 30% das evidências de entrada, com máscaras e sementes comuns entre modelos. Para a rede, inferir marginalizando variáveis não observadas; para o baseline, usar tratamento de ausências definido e ajustado no treino. Verificar a compatibilidade entre calibração e entradas incompletas e registrar limitações. Esse teste representa o mecanismo de ausência simulado, não qualquer situação real de dados faltantes.

## Incerteza e reprodutibilidade

Guardar previsões por caso e apresentar variação das métricas nas partições. No teste, propor intervalos por bootstrap pareado estratificado com 1000 reamostragens para diferenças principais, reutilizando os mesmos casos em cada comparação. Esses intervalos descrevem incerteza de amostragem condicionada aos modelos ajustados; não capturam toda a variabilidade do treinamento. Evitar concluir superioridade com diferenças pequenas ou intervalos amplos.

Guardar versões das bibliotecas, sementes, índices das divisões, parâmetros, matriz de utilidade, logs e instruções de execução. Construir o protótipo somente após a avaliação metodológica.

## Fontes consultadas

- Projeto de TCC fornecido por Rodrigo, seções de objetivos, metodologia e cronograma.
- [UCI Statlog German Credit Data](https://archive.ics.uci.edu/dataset/144/statlog+german+credit+data): características e arquivos da base prevista.
- [UCI South German Credit](https://archive.ics.uci.edu/dataset/573/south+german+credit+update): correção da documentação e contexto amostral.
- [scikit-learn sobre calibração](https://scikit-learn.org/stable/modules/calibration.html): separação dos dados para calibração e interpretação das métricas probabilísticas.

Consultas realizadas em 27/09/2026. Proporções de divisão, sementes, grades e cenários acima são propostas deste protocolo, não exigências da UCI, da UFU ou do projeto original.


## Registro de atualização — 19/10/2026

- Rodrigo informou que o orientador escolheu a base **South German Credit**, versão corrigida. A UCI descreve o alvo `kredit` como contrato cumprido (`good`) ou não cumprido (`bad`). A nota técnica associada à versão corrigida define os níveis do alvo como `0 = bad` e `1 = good`.
- Para os modelos, ainda falta registrar se a classe positiva será risco ruim (`bad = 1`), que é uma recodificação de análise, não o código bruto da base.
- Rodrigo prefere usar 20% como teste final e cinco partições estratificadas no conjunto de desenvolvimento. Manter como desenho de trabalho, sujeito à confirmação metodológica do orientador.
- O orientador encorajou flexibilidade no tema. Reavaliar problema, modelos e caso de estudo se isso melhorar relevância ou viabilidade; o resultado desejado segue sendo uma análise comparativa e um protótipo demonstrativo.

Fontes para a codificação: [UCI South German Credit](https://archive.ics.uci.edu/dataset/573/south%2Bgerman%2Bcredit%2Bupdate) e [Grömping (2019), *South German Credit Data: Correcting a Widely Used Data Set*](https://www1.beuth-hochschule.de/FB_II/reports/Report-2019-004.pdf), apêndice B.
