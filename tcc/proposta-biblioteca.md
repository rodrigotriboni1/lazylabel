# Proposta de biblioteca open source para rotulagem assistida de dados financeiros

**Estado:** rascunho para discussão com o orientador. Em 19/10/2026, Rodrigo informou que o orientador gostou da visão do projeto e indicou a reutilização do fluxo como foco principal. Este documento propõe como delimitar e avaliar essa ideia; não substitui o protocolo experimental já existente até que o orientador aprove a revisão.

## Ideia do projeto

Criar uma biblioteca open source que facilite o ajuste local (fine-tuning) de modelos leves, como modelos da família Gemma, para tarefas de rotulagem assistida de dados financeiros. A ferramenta deverá ajudar a preparar exemplos, configurar e executar o ajuste, solicitar revisão humana dos rótulos e registrar configurações, versões e decisões para permitir auditoria e reprodução.

O modelo sugere rótulos e explicações; a pessoa revisa os casos conforme a política definida. O projeto não deve pressupor que o LLM sozinho garante qualidade dos dados ou compliance. A visão futura é reutilizar a biblioteca em diferentes tarefas financeiras. O TCC vai demonstrar uma tarefa delimitada: rotular registros da South German Credit como risco bom/ruim, após confirmar a adequação do dataset e do protocolo com o orientador.

## Pergunta de pesquisa provisória

> **Como uma biblioteca open source pode facilitar o ajuste local de um modelo leve para rotulagem assistida de dados financeiros, mantendo revisão humana e rastreabilidade, em uma demonstração de classificação de risco de crédito?**

Essa formulação é uma hipótese de trabalho. Precisamos discutir com o orientador se o TCC deve avaliar principalmente a qualidade dos rótulos sugeridos, a facilidade/reprodutibilidade do processo de fine-tuning, a rastreabilidade, ou uma combinação delimitada dessas dimensões.

## Fluxo mínimo candidato a demonstrar

1. **Preparar ambiente local** — selecionar modelo leve compatível, verificar requisitos e garantir que os dados de treino permaneçam na máquina usada na demonstração.
2. **Preparar exemplos** — transformar registros e rótulos de referência em exemplos conforme formato definido; excluir identificadores desnecessários e registrar origem/licença dos dados.
3. **Configurar fine-tuning** — facilitar seleção do modelo, parâmetros e método eficiente de ajuste, mantendo configuração explícita e exportável.
4. **Treinar e sugerir rótulos** — executar localmente e gerar sugestões, confiança/indicadores disponíveis e justificativas estruturadas, sem tratar a explicação como prova.
5. **Revisar com humano** — permitir aceitar, corrigir ou rejeitar sugestões e salvar a decisão final separada da previsão do modelo.
6. **Avaliar** — comparar o modelo ajustado com uma linha de base definida (por exemplo, modelo original, regras simples ou processo manual), usando partição reservada e métricas adequadas ao rótulo.
7. **Auditar e reproduzir** — guardar versão do modelo/base, parâmetros, resultados, rótulos previstos e decisões humanas.

## O que será reutilizável e o que exige configuração

| Parte | Potencialmente reutilizável | Dependente do problema/dados |
|---|---|---|
| Ingestão e inspeção | Interface de carregamento, perfilamento e alertas de qualidade | Formato, esquema, permissões, tamanho e significado das colunas |
| Preparação | Pipeline configurável e registro das transformações | Tratamento de variáveis, faltantes, classes, datas e vazamento |
| Modelagem | Contrato comum para ajustar, prever e salvar configurações | Algoritmos compatíveis com o tipo de problema e escolhas de hiperparâmetros |
| Avaliação | Interface comum para comparar execuções e registrar métricas | Métricas, validação e limites dependem do objetivo e dos dados |
| Decisão de negócio | Mecanismo parametrizável para limiares/custos/utilidade | Ações, consequências, matriz de utilidade e restrições vêm do domínio e precisam de validação humana |
| Visualização | Componentes reutilizáveis e filtros | Gráficos e cortes dependem das variáveis e da pergunta analítica |

## Critérios candidatos para demonstrar reutilização

Rodrigo escolheu demonstrar **as duas formas** de reutilização: reconfigurar sem reescrever as etapas comuns e aplicar a biblioteca a uma segunda base financeira. O novo foco de rotulagem assistida substitui o plano anterior de comparar regressão logística e redes bayesianas como contribuição central. A comparação de modelos só permanece se contribuir diretamente para avaliar a biblioteca e for aprovada pelo orientador.

- **Separação de componentes:** documentar quais partes de preparação, ajuste, inferência, revisão e logging são genéricas e quais dependem da tarefa de rotulagem.
- **Reprodução por configuração:** repetir o fine-tuning/inferência alterando a configuração ou tarefa sem reescrever o núcleo, se tecnicamente viável.
- **Portabilidade entre bases:** aplicar a biblioteca a uma segunda base financeira, registrar adaptações de esquema e rótulos e separar essas adaptações de reescritas da biblioteca.
- **Rastreabilidade:** registrar dados, transformações, partições, modelos, parâmetros, métricas e hipóteses usados em cada execução.
- **Esforço de adaptação:** medir e descrever os passos e alterações necessários para configurar o caso, usando protocolo observável; evitar afirmar economia de tempo sem comparar tarefa/tempo de forma planejada.
- **Correção analítica:** conferir que a execução configurada reproduz o protocolo e que o protótipo corresponde aos resultados experimentais validados.
- **Compreensibilidade para o usuário:** considerar avaliação formativa com tarefas e participantes apenas se houver tempo, aprovação metodológica e condições éticas adequadas; não alegar facilidade de uso só por inspeção do desenvolvedor.

## Segunda base candidata para validar portabilidade

Como candidata inicial, avaliar o **Default of Credit Card Clients**, também do UCI. A página do UCI informa 30.000 registros, 23 atributos e uma variável-alvo binária para inadimplência no mês seguinte; os dados incluem perfil, histórico mensal de pagamentos, valores de faturas e pagamentos. Isso oferece contraste com a South German Credit e permite testar se preparação de exemplos, ajuste, inferência, revisão e auditoria podem ser reaproveitados após mapear o esquema. [UCI — Default of Credit Card Clients](https://archive.ics.uci.edu/dataset/350/defaultofcreditcardclients)

Esta base é apenas uma **candidata**, não uma escolha metodológica aprovada. Ela continua no domínio de crédito (Taiwan, dados de 2005) e tem outro desenho e população; não deve ser usada para afirmar que o fluxo generaliza a toda análise financeira. O uso de atributos mensais e a separação entre preditores e alvo também precisam ser conferidos para evitar vazamento temporal.

## Limites do primeiro protótipo

- Casos demonstrativos candidatos: rotulagem bom/ruim na South German Credit corrigida e portabilidade para uma segunda base financeira, sujeitos à aprovação do orientador e à revisão de viabilidade.
- “Modelo treinado” deve ser especificado: fine-tuning local por usuário é diferente de apenas executar um modelo pré-treinado localmente. Definir se a biblioteca treina de fato, quais dados entram no treino e quais configurações/hardware são necessários.
- Avaliar se o dataset é adequado para fine-tuning de um LLM: registros tabulares podem exigir serialização para texto e podem não justificar um LLM quando modelos tabulares mais simples forem mais adequados. Comparar com baseline apropriado.
- Não prometer compliance automático, detecção completa de inconsistências, privacidade absoluta ou facilidade de adoção sem controles e evidências; definir controles, limitações e fronteiras de qualquer onboarding com LLM externo.
- Não afirmar que a ferramenta atende “qualquer coisa” ou que aceita qualquer base sem adaptação.
- Não usar métricas do South German Credit para inferir tendências de uma carteira bancária brasileira.
- SCR.data do BCB pode ser discutido como fonte agregada de contexto, mas só entra no escopo se houver uma pergunta definida e aprovação do orientador; seu uso não demonstra adaptação de modelos a uma segunda base.
- Decisões de concessão ou intervenção só podem ser exemplificadas sob hipóteses explícitas; o dataset não contém resultados contrafactuais das ações.

## Decisões para a próxima conversa com o orientador

1. Esta tarefa — rotulagem assistida com modelo leve local — representa a ideia aprovada?
2. O escopo deve exigir fine-tuning de fato ou comparar fine-tuning com inferência de um modelo pré-treinado?
3. Qual baseline e quais métricas serão apropriados para avaliar a qualidade dos rótulos?
4. O Default of Credit Card Clients é adequado como segunda base e que parte do fluxo deve ser repetida nele?
5. Revisão humana e registro de auditoria são suficientes como eixo de governança demonstrado, sem afirmar conformidade normativa completa?
6. Quais evidências e método de avaliação são adequados às regras e ao prazo do curso?

## Recomendação provisória

Manter a visão de biblioteca open source reutilizável, mas testar primeiro se fine-tuning local de um modelo leve acrescenta valor à rotulagem tabular frente a baselines mais simples. Definir com o orientador uma tarefa, protocolo de avaliação e limites de privacidade/compliance; depois validar a segunda base candidata. A evidência sustentará apenas o reuso nas tarefas e bases avaliadas, não suporte universal.
