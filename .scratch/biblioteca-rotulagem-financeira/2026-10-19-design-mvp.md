# Especificação de desenho: biblioteca local de análise e rotulagem assistidas

**Data:** 2026-10-19  
**Estado:** proposta de desenho para revisão do autor; não iniciar implementação até aprovação desta especificação e de um plano de execução.

## Objetivo

Definir um MVP para uma biblioteca open source Python que ajude desenvolvedores a conectar e inspecionar dados localmente, fazer perguntas analíticas, gerar gráficos e resumos fundamentados, obter sugestões de rótulos de um modelo leve, revisar as sugestões e preparar exemplos para fine-tuning local. A primeira demonstração será financeira, mas tarefas, análises e rótulos devem ser configuráveis para mostrar que o fluxo pode ser reutilizado.

O usuário principal é um desenvolvedor que integra a biblioteca Python/CLI a uma tarefa própria. O MVP também fornece um painel web local para visualizar e executar o mesmo fluxo, incluindo exploração de dados, tendências e composição/participação, como market share quando os dados e a definição do indicador permitirem.

## Fluxo principal

1. O desenvolvedor cria uma tarefa de rotulagem configurando instruções, colunas de entrada e conjunto de rótulos permitidos.
2. Conecta uma fonte por CSV ou SQLite. Os conectores iniciais são locais e somente de leitura.
3. A biblioteca perfilha a fonte e roda verificações estruturais e de qualidade, como colunas ausentes, valores vazios, tipos inesperados e mudanças em relação ao esquema configurado.
4. O desenvolvedor faz uma pergunta analítica pela CLI ou painel. A IA local propõe um plano estruturado usando o esquema disponível; o desenvolvedor confirma ou ajusta dimensões, filtros e definições ambíguas.
5. Um motor analítico determinístico executa somente operações permitidas sobre a fonte local e produz tabelas agregadas e gráficos, como tendências e composição/participação. Uma IA local pode resumir os resultados calculados, indicando métricas, período, filtros e campos usados.
6. Um backend local compatível gera sugestões de rótulo no formato configurado. Saídas inválidas são sinalizadas e não são tratadas como rótulos aceitos.
7. O desenvolvedor revisa cada sugestão — aceita, edita ou rejeita — pela CLI ou pelo painel web.
8. As decisões são registradas localmente e permanecem separadas das previsões originais do modelo.
9. Quando explicitamente solicitado, a biblioteca prepara um dataset local com somente as colunas selecionadas e rótulos revisados.
10. Um comando/ação explícita executa o fine-tuning local e salva configuração e adaptadores em armazenamento local.

Monitoramento e treinamento são iniciados pelo usuário, sob demanda. Agendamento e execução contínua não fazem parte do MVP.

## Arquitetura e interfaces

- Um núcleo Python compartilha regras de tarefa, conectores, validação, inferência, revisão, persistência e treino.
- A CLI oferece o fluxo completo: configurar fonte/tarefa, inspecionar e monitorar, perguntar/analisar dados, gerar gráficos como artefatos locais, gerar sugestões, revisar rótulos, preparar dataset e iniciar treino.
- Um comando inicia o servidor web local. O painel permite executar as mesmas operações, ver gráficos e revisar os resultados visualmente.
- CLI e painel chamam os mesmos serviços da biblioteca; não implementam regras de negócio duplicadas.
- O servidor web deve escutar apenas em `localhost` por padrão.
- Os detalhes do framework web, layout, esquema de armazenamento e nomes finais dos comandos serão definidos no plano de implementação.

## Exploração analítica e gráficos

- A pessoa pode perguntar em linguagem natural sobre os dados conectados, por exemplo: “Como a participação de cada produto nas vendas mudou por trimestre?”.
- A IA local transforma a pergunta em um plano estruturado — métrica, dimensão, período, filtros, agregação e visualização — e apresenta esse plano para confirmação quando a definição for ambígua ou não estiver mapeada.
- A execução numérica é feita por um motor determinístico, não por aritmética livre do LLM. O MVP não executa código ou SQL arbitrário gerado pelo modelo; usa operações permitidas sobre conectores somente de leitura.
- Tipos iniciais de análise: tendência temporal, comparação entre grupos e composição/participação. Gráficos iniciais: linha, barra e barra empilhada. “Market share” só é calculado quando o usuário mapeia a medida, o grupo que representa o mercado, o período e o denominador; a biblioteca não presume uma definição universal.
- A explicação textual é gerada a partir dos resultados calculados e identifica período, filtros e campos usados. Ela não pode inventar valores, causalidade ou recomendações ausentes dos dados.
- Se a fonte não tiver campos adequados, a interface pede mapeamento ou informa que a análise não pode ser feita; não inventa colunas nem preenche dados ausentes sem autorização.
- Pelo painel web, o resultado inclui gráfico e descrição da consulta. Pela CLI, o comando exibe resumo e salva uma representação local do gráfico/resultado para abrir ou exportar.
- As mesmas operações analíticas ficam disponíveis nas duas interfaces por meio do núcleo compartilhado.

## Conectores e dados

- Conectores iniciais: arquivo CSV local e banco SQLite local.
- A interface interna de conectores permite adicionar outras fontes depois, sem afirmar suporte universal no MVP.
- Fontes originais são sempre abertas em modo somente leitura e não são alteradas pela biblioteca.
- Inspeção e inferência operam localmente. A biblioteca não envia linhas da fonte a serviços externos.
- Na análise, a IA local trabalha sobre a pergunta e o esquema; o motor local acessa registros e calcula resultados. Um resumo pode usar agregados calculados, que permanecem no ambiente local.
- Por padrão, a biblioteca não copia a base original para sua área de trabalho.
- Só cria um dataset de treino local quando solicitado explicitamente; ele contém as colunas que o desenvolvedor escolheu para a tarefa e os rótulos revisados.
- O modelo-base pode ser baixado quando necessário; pesos, dataset de treino, revisões e adaptadores permanecem no ambiente local.

## Tarefas, rótulos e resultados

- A tarefa define instruções, campos de entrada e rótulos válidos; não existe uma taxonomia financeira rígida no núcleo.
- A primeira demonstração usará uma tarefa financeira, mas a seleção exata da base e do problema de rotulagem ainda precisa ser alinhada ao protocolo do TCC e ao orientador.
- A resposta do modelo deve ser validada contra um formato estruturado e contra o conjunto de rótulos configurado.
- Cada sugestão fica identificada como previsão do modelo e pode incluir uma justificativa curta. Justificativas não são evidência de correção.
- Não usar uma pontuação de confiança não calibrada para aceitar rótulos automaticamente.
- Revisões guardam a sugestão original, a ação humana, o rótulo final e o momento/configuração relevantes para auditoria local.

## Modelo e fine-tuning

- Integração inicial: Transformers para carregar/executar modelos locais e PEFT/LoRA para ajuste eficiente.
- Não prometer suporte a qualquer modelo: a compatibilidade depende do backend, arquitetura, tokenizer, licença e capacidade de produzir a saída estruturada exigida.
- Modelo local sugere rótulos; regras determinísticas são responsáveis pelo monitoramento estrutural e de qualidade.
- Treino nunca começa automaticamente. O desenvolvedor inicia a preparação dos exemplos e o fine-tuning por comando/ação explícita.
- O fine-tuning usa exemplos revisados da tarefa. Os detalhes de parâmetros, hardware mínimo e referência de modelo devem ser fixados no plano e validados antes da implementação.
- Mostrar requisitos locais e a licença/termos do modelo selecionado antes do download ou treino, quando essa informação estiver disponível.

## Onboarding externo opcional

- Uma LLM externa pode auxiliar a sugerir configuração no onboarding, mas não é necessária para operar o núcleo.
- Nenhuma linha ou valor de registro pode ser enviado à LLM externa.
- Somente metadados selecionados pelo desenvolvedor — por exemplo, nomes de colunas e tipos — podem ser enviados, após aprovação explícita para aquele envio.
- Configurações geradas externamente exigem revisão e confirmação humana antes de uso.

## Persistência e privacidade

- Configurações de tarefa/fonte, relatórios, sugestões, decisões de revisão, datasets solicitados e adaptadores são mantidos localmente.
- A fonte original permanece somente leitura; eventuais alterações de rótulo são registradas em separado.
- O painel é local e não expõe uma porta de rede externa por padrão.
- O MVP não promete conformidade regulatória, anonimização automática nem detecção completa de dados pessoais.
- O desenvolvedor é responsável por selecionar colunas permitidas, controlar arquivos locais e conferir licença e autorização dos dados/modelos.

## Escopo incluído

- Biblioteca Python e interface CLI.
- Painel web local iniciado por comando e capaz de operar o fluxo completo.
- CSV e SQLite somente leitura.
- Tarefas e conjuntos de rótulos configuráveis.
- Perfil e monitoramento estrutural/qualidade sob demanda.
- Perguntas analíticas em linguagem natural convertidas em planos revisáveis e executadas por operações determinísticas permitidas.
- Gráficos locais de tendência, comparação e composição/participação, com resumo textual fundamentado nos resultados calculados.
- Sugestões locais de rótulos com Transformers.
- Revisão humana para aceitar, editar e rejeitar sugestões, com trilha local.
- Preparação explícita de dataset revisado e fine-tuning local via PEFT/LoRA.
- Caso financeiro demonstrativo e documentação de adaptação.

## Fora do escopo do MVP

- Compatibilidade garantida com todo modelo ou toda fonte de dados.
- Escrita/alteração da fonte CSV ou banco de origem.
- Fine-tuning automático ou agendado.
- Envio de linhas da base para qualquer LLM externa.
- Serviço hospedado, colaboração multiusuário, autenticação e implantação em nuvem.
- Analytics avançado, gráficos de carteira prontos para um domínio, alertas contínuos e previsão automática de mercado.
- Execução de SQL ou código arbitrário gerado por IA e recomendações de investimento/crédito.
- Afirmações sobre market share sem definição de mercado, denominador, período e cobertura de dados configurados.
- Alegações de compliance ou qualidade automática garantida.

## Critérios de aceite do produto

1. Um desenvolvedor configura uma tarefa com instruções, colunas e rótulos permitidos.
2. CSV e SQLite são inspecionados sem modificar a fonte e sem imprimir valores de registros na saída de inspeção por padrão.
3. Verificações determinísticas sinalizam problemas estruturais/qualidade com localização compreensível.
4. Uma pergunta analítica gera um plano estruturado que pode ser inspecionado e corrigido antes da execução.
5. Métricas, agrupamentos e séries temporais são calculados pelo motor determinístico e ligados aos campos, filtros e períodos usados; o gráfico e resumo correspondem aos resultados.
6. Um backend local compatível produz sugestões validadas contra o conjunto de rótulos.
7. A mesma sugestão pode ser revisada por CLI e painel web; aceitar, editar e rejeitar preserva a previsão original e a decisão humana.
8. Um dataset de treino não é criado sem ação explícita e inclui somente as colunas selecionadas e os rótulos revisados.
9. O usuário pode iniciar fine-tuning explicitamente; modelo e artefatos resultantes permanecem locais.
10. Nenhum dado de linha é enviado externamente; o painel é limitado a `localhost` por padrão.
11. A interface de conectores e de backend permite extensões sem reescrever o núcleo, mas a documentação delimita as compatibilidades efetivamente demonstradas.

## Questões acadêmicas ainda abertas

- Definir, com o orientador, o caso financeiro de demonstração e as bases adequadas.
- Definir como demonstrar reutilização: reconfiguração do mesmo fluxo, aplicação a outra tarefa/base financeira, ou ambos, e quais evidências serão coletadas.
- Fixar a pergunta de pesquisa e separar avaliação de engenharia (reprodutibilidade/esforço de adaptação) da avaliação da qualidade dos rótulos.
- Escolher baseline, partições e métricas. O uso de LLM tabular precisa ser comparado a alternativas simples apropriadas.
- Fixar modelo-base, hardware disponível, licenças, requisitos de memória e critérios de viabilidade para fine-tuning local.
- Escolher framework do painel web, esquema de armazenamento e estratégia de identificação estável dos registros para revisão.
- Definir se a IA que elabora planos e resumos analíticos será um backend local separado, compartilhado com o modelo de rotulagem ou uma camada intercambiável; não presumir que o modelo ajustado para rótulos também seja bom em planejamento analítico.
- Delimitar as operações analíticas suportadas, fórmulas e validação de consultas para evitar resultados ambíguos ou não auditáveis.

## Fontes técnicas consultadas

- Hugging Face Transformers, integração PEFT: https://huggingface.co/docs/transformers/en/peft
- Hugging Face Transformers, modelos Gemma: https://huggingface.co/docs/transformers/model_doc/gemma

Essas fontes sustentam a escolha inicial de integração, mas não estabelecem suporte universal, adequação de um modelo a uma tarefa específica ou requisitos de hardware do experimento.
# Estado do escopo (26/10/2026)

O fluxo original com revisão humana por registro foi substituído pelo desenho autônomo aprovado em `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md` e pela conclusão integrada em `codex/finlabel-autonomous-mvp`. A interface continua oferecendo operação por CLI e painel web local. Casos sem política/confiança adequada vão para quarentena; treino usa somente dados confiáveis e promoção depende de holdout congelado e gates. Esta especificação antiga permanece como histórico dos requisitos originais.

