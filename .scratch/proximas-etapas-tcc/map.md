# Próximas etapas do TCC

Épico deste esforço: [Criar um fluxo acessível e reutilizável de modelagem para problemas financeiros](epico.md).

## Notes

Atualização de 19/10/2026: Rodrigo confirmou que realizou as atividades das Semanas 2 e 3 e informou que o professor autorizou o uso de IA como apoio para otimizar o tempo. Os artefatos das Semanas 2 e 3 ainda precisam ser localizados. O orientador escolheu a versão South German Credit corrigida e recomendou flexibilidade para o tema evoluir.

Esta sequência parte da agenda semanal e do protocolo preliminar, mas pode mudar conforme o tema evolui. Rodrigo concluiu as Semanas 2 e 3; a próxima tarefa é localizar e registrar os artefatos, não refazer o trabalho. South German Credit foi escolhida. O prazo e algumas decisões metodológicas ainda estão em aberto.

## Decisions-so-far

- Rodrigo confirmou o objetivo do épico: produzir uma análise comparativa e um protótipo demonstrativo para o TCC.
- O usuário aprovou a sequência de oito tickets e suas dependências em 19/10/2026.
- O registro da Semana 1 confirma a preparação inicial do protocolo e das pastas, mas também lista validações acadêmicas ainda pendentes. Rodrigo confirmou que realizou as atividades das Semanas 2 e 3; registrar os artefatos no ticket 01.
- O professor autorizou IA como apoio ao trabalho e à gestão do tempo; confirmar usos permitidos e forma de declaração conforme as regras aplicáveis ao curso.
- O orientador escolheu South German Credit corrigido; Rodrigo prefere a divisão 80/20 com cinco partições de validação cruzada no desenvolvimento.
- O tema pode evoluir conforme exploração e orientação; crédito é o primeiro caso demonstrativo, e a ferramenta não deve ser descrita como solução universal sem evidência.
- Em 19/10/2026, Rodrigo concordou em propor ao orientador a inclusão de tendências agregadas de crédito no Brasil usando SCR.data do BCB. Isso ainda é uma proposta de escopo, não uma decisão acadêmica final. Os indicadores de mercado devem ficar separados dos resultados dos modelos treinados no South German Credit.
- Em 19/10/2026, Rodrigo esclareceu a visão de longo prazo: criar um projeto reutilizável para que pessoas conectem suas próprias bases e construam modelos/análises financeiros com facilidade, apoiados por conceitos matemáticos e de mercado. Crédito deve ser o primeiro domínio demonstrativo; a afirmação de funcionar com qualquer base/problema não faz parte do escopo comprovado do TCC.
- Em 19/10/2026, Rodrigo informou que o orientador gostou da proposta e que o foco principal deve ser a reutilização do fluxo. A comparação de modelos fica como parte da demonstração no caso de crédito. Definir com o orientador critérios verificáveis para avaliar a reutilização.
- Rodrigo escolheu demonstrar as duas evidências de reutilização: reconfigurar o fluxo sem reescrever as etapas comuns e aplicá-lo a uma segunda base financeira. O documento de proposta indica o dataset UCI Default of Credit Card Clients como candidato, ainda sujeito à aprovação do orientador e à avaliação de viabilidade.
- Atualização posterior em 19/10/2026: Rodrigo refinou o produto para uma biblioteca open source de fine-tuning local de modelos leves, voltada à rotulagem assistida de dados financeiros com revisão humana. Esta direção substitui o planejamento anterior centrado em regressão logística, redes bayesianas e utilidade esperada como contribuição principal; revisar os tickets experimentais antes de executá-los.
- 21/10/2026: Rodrigo aprovou substituir a revisão humana por registro por um fluxo autônomo: previsões válidas são aplicadas conforme política calibrada, casos incertos vão para quarentena, e retreino/promoção automáticos só usam rótulos confiáveis e gates configurados por tarefa. A especificação aprovada é `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md`; etapas: planos 1 (rotulagem/quarentena), 2 (supervisão confiável e promoção), 3 (CLI/painel).
- Rascunho do fluxo mínimo, critérios candidatos e perguntas para o orientador: [Proposta_fluxo_reutilizavel.md](../../planejamento/Proposta_fluxo_reutilizavel.md). Ainda não substituir o protocolo experimental até validação do recorte.
- Avaliar previsão e política de decisão simulada separadamente. A base não oferece resultados contrafactuais das ações.
- Construir o protótipo após a avaliação metodológica.

## Fog

- Prazo oficial de entrega e defesa.
- Convenção de modelagem da classe positiva; o código bruto da fonte é 0 = ruim e 1 = bom.
- Confirmação do desenho 80/20 com cinco partições e alinhamento das hipóteses da matriz de utilidade.
- Formulação da pergunta de pesquisa e critérios verificáveis para avaliar reutilização do fluxo.
- Definição do público inicial e do fluxo mínimo do protótipo.
- Artefatos e resultados produzidos nas Semanas 2 e 3.
- Regras do curso para declarar e delimitar o uso de IA no TCC.
- Decidir com o orientador se SCR.data agrega valor ao recorte ou fica como contexto/futuro.

## Frontier

A visão do produto está descrita no épico e foi definida por Rodrigo. O recorte acadêmico, a pergunta de pesquisa e os limites do protótipo ainda requerem alinhamento com o orientador. Começar pelo ticket 01. Os tickets seguintes permanecem bloqueados conforme indicado em cada arquivo.
