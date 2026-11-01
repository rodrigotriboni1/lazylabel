# Épico: Criar uma biblioteca open source para rotulagem assistida de dados financeiros

**Estado:** Rodrigo informou que o orientador gostou da proposta de reutilização do fluxo. Em seguida, refinou a ideia para uma biblioteca open source que facilita fine-tuning local de modelos leves (ex.: Gemma) para rotulagem assistida de dados financeiros. O foco de reutilização é demonstrar reconfiguração sem reescrever etapas comuns e aplicação a uma segunda base. Tarefa, método de fine-tuning, avaliação e escopo ainda precisam de validação acadêmica.

## O que quero alcançar com o TCC

Quero criar uma biblioteca open source que ajude a ajustar localmente modelos leves para rotulagem assistida de dados financeiros, com revisão humana e registro das decisões. O modelo sugere rótulos e a pessoa aceita, corrige ou rejeita; a biblioteca facilita preparar exemplos, configurar fine-tuning, executar inferência e avaliar resultados sem montar toda a infraestrutura do zero. A intenção é manter os dados na máquina do usuário durante o fluxo local.

Para o TCC, a tarefa inicial será rotulagem assistida de registros financeiros, demonstrada classificando risco bom/ruim na South German Credit, se confirmada pelo orientador. A reutilização será demonstrada por reconfiguração sem reescrita das etapas comuns e aplicação a uma segunda base financeira. A ideia de onboarding por uma LLM mais capaz e um modelo local observador é uma direção de produto; só entra no protótipo se couber no recorte e se os limites de privacidade forem definidos. Não alegar suporte universal, compliance automático ou benefício de adoção sem avaliação.

O resultado esperado é uma análise metodológica e um protótipo demonstrativo de um fluxo de modelagem financeira configurável, sustentados por dados, código e decisões registradas. O caso de crédito serve para avaliar o fluxo em um problema concreto. O objetivo não é provar que a rede bayesiana sempre supera a regressão logística, nem afirmar que as ações simuladas causam resultados reais.

## Por que este trabalho importa

Uma previsão de risco, sozinha, não define o que um sistema deveria fazer. A escolha da ação depende também dos custos, benefícios e hipóteses definidos para a decisão. O TCC separa essas duas partes para mostrar o que os modelos estimam e o que a política de decisão recomenda.

## Como saberei que o épico foi concluído

- A versão da base, o significado das classes e as transformações estão documentados.
- A biblioteca executa localmente o fluxo especificado de preparação, fine-tuning/inferência, sugestão de rótulos, revisão e registro, conforme o escopo técnico aprovado.
- A qualidade dos rótulos sugeridos é avaliada contra rótulos de referência e baseline(s) apropriado(s), com partição de avaliação reservada.
- Reconfiguração e aplicação a uma segunda base registram etapas reutilizadas e adaptações necessárias.
- A revisão humana mantém sugestões, correções e rótulos finais rastreáveis.
- Resultados, scripts e escolhas podem ser reproduzidos e conferidos.
- Um protótipo demonstra o fluxo configurável no caso de crédito sem se apresentar como sistema pronto para uso real ou como solução universal para qualquer base.
- A monografia distingue fatos observados, hipóteses simuladas e limitações causais.

## Limites do escopo

- South German Credit é uma base tabular histórica; avaliar se é apropriada para ajustar um LLM ou se serve apenas para a demonstração com um baseline mais simples.
- O modelo pode sugerir rótulos, mas revisão humana, rastreabilidade e limites explícitos são necessários; não afirmar compliance garantido.
- “Conectar qualquer base e modelar qualquer problema financeiro” é a visão de longo prazo; o TCC deve definir um recorte pequeno, verificável e compatível com a estrutura da base escolhida.
- A rede bayesiana não precisa vencer o baseline para o trabalho ser bem-sucedido.
- O protótipo é demonstrativo, não uma implantação operacional de política de crédito.
- O uso de IA é apoio ao estudo, à pesquisa, à programação, à depuração e à organização; não substitui as decisões, validações e responsabilidade autoral de Rodrigo.

## Como a IA entra no processo

A IA pode reduzir tempo de tarefas auxiliares: explicar conceitos, sugerir buscas, ajudar a entender fontes verificadas, esboçar ou depurar código, organizar etapas e revisar clareza textual. Rodrigo confere fontes e cálculos, executa e valida o código, interpreta os resultados e registra os usos relevantes conforme as orientações do professor e as regras do curso. A IA não é tratada como fonte de evidência experimental.

## Decisões ainda abertas

- Se o trabalho deve executar fine-tuning local de fato ou incluir também a comparação com modelo pré-treinado sem ajuste.
- Modelo leve, método de ajuste, hardware, dados de treino e critérios de avaliação.
- Prazo oficial, requisitos do curso e datas revisadas.
- Confirmação metodológica do desenho 80/20 com validação cruzada em cinco partes.
- Formulação da pergunta de pesquisa e critérios para avaliar a reutilização do fluxo.
- Delimitação do fluxo e critérios candidatos registrados em [Proposta_fluxo_reutilizavel.md](../../planejamento/Proposta_fluxo_reutilizavel.md), ainda sujeitos à validação do orientador.
- Público inicial e etapas do fluxo que o protótipo deve cobrir.
- Se o SCR.data agrega valor ao recorte ou se deve ficar apenas como referência contextual/futura.
- Adequação da South German Credit como tarefa/dados de rotulagem e segunda base para avaliar portabilidade.
- Usos específicos de IA permitidos pelo professor e forma de declaração.

## Caminho de execução

O épico é acompanhado pelo [mapa de próximas etapas](map.md) e pelos tickets locais:

1. Reconciliar progresso e alinhar o novo recorte com o orientador.
2. Fixar tarefas, bases, rótulos de referência e protocolo de avaliação.
3. Implementar baseline de rotulagem e pipeline local reproduzível.
4. Integrar e ajustar o modelo leve selecionado, se o fine-tuning for aprovado.
5. Avaliar qualidade, revisão humana, rastreabilidade e esforço de adaptação.
6. Reconfigurar o fluxo e aplicá-lo à segunda base aprovada.
7. Montar a interface/demonstração da biblioteca.
8. Consolidar monografia e apresentação.

## Workflow de desenvolvimento assistido por IA

Para decisões e planejamento do TCC, trabalhar em ciclos curtos: esclarecer a pergunta, registrar decisões e dúvidas, produzir uma tarefa pequena, validar a evidência e atualizar o mapa.

Quando houver código experimental para implementar, usar as skills Matt Pocock já instaladas: `grill-with-docs` → `to-spec` → `to-tickets` → `implement` ou `implement-spec` → `tdd` → `code-review`. Aplicar cada etapa só quando fizer sentido; a validação metodológica e a interpretação dos resultados permanecem com o autor e o orientador.
