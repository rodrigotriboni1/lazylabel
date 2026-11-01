# TCC de Rodrigo Mialichi Triboni

**Tema submetido:** Redes bayesianas e utilidade esperada aplicadas à seleção de *next best action* em sistemas automatizados de decisão.

**Direção atual do projeto:** biblioteca local FinLabel para rotulagem assistida de dados financeiros. O pivô ainda não foi aprovado pelo orientador: [ADR-0007](docs/adr/0007-pivo-do-tcc-para-biblioteca-finlabel.md) (status Proposta).

## Por onde começar

- [PRD do FinLabel](docs/prd/finlabel.md), [decisões (ADRs)](docs/adr/) e [glossário](GLOSSARY.md)
- [Roadmap de melhorias](docs/roadmap-melhorias.md)
- [Guia rápido do FinLabel (inglês)](codigo/finlabel/docs/quickstart.md)
- [Pergunta ao orientador sobre calibração do modelo-base](docs/pergunta-orientador-calibracao-modelo-base.md)
- [Agenda semanal](Agenda_semanal_TCC.md)
- [Protocolo experimental preliminar](planejamento/Protocolo_experimental.md)
- [Fluxo de uso de IA no TCC](planejamento/Uso_de_IA_no_TCC.md)
- [Épico do TCC](.scratch/proximas-etapas-tcc/epico.md)
- [Mapa das próximas etapas](.scratch/proximas-etapas-tcc/map.md)
- [Primeira tarefa: reconciliar progresso e fechar o protocolo](.scratch/proximas-etapas-tcc/issues/01-reconciliar-progresso-e-protocolo.md)
- [Guia de estudo da Semana 1](planejamento/Guia_de_estudo_Semana_01.md)
- [Registro da Semana 1](planejamento/Semana_01.md)

## Estrutura

| Local | Conteúdo |
|---|---|
| `planejamento/` | Guias de estudo, registros semanais e protocolo experimental |
| `referencias/` | Fontes e fichamentos bibliográficos |
| `dados/brutos/` | Cópias originais das bases, preservadas sem alteração |
| `dados/processados/` | Dados derivados por scripts e prontos para análise |
| `codigo/` | Preparação de dados, treinamento e avaliação dos modelos |
| `resultados/` | Métricas, tabelas e figuras produzidas pelos experimentos |
| `texto/` | Capítulos e versões de trabalho da monografia |
| `entregas/` | Documentos preparados para compartilhar ou entregar |
| `docs/agents/` | Regras de tracker, labels e documentação de domínio para as skills |
| `.scratch/` | Mapa e tickets locais das próximas tarefas |
| `codigo/finlabel/` | Biblioteca local `finlabel-local`: CLI, painel web, rotulagem autônoma com quarentena e ciclo de treino com gates (ver PRD) |
| `.documentos_qa/` | PDFs, imagens renderizadas e arquivos auxiliares de conferência de documentos |

## Entregas existentes

- `entregas/Apresentacao_do_andamento_TCC_Rodrigo.docx` — apresentação de andamento.
- `entregas/TCC_Research_Proposal_Rodrigo_English.docx` — versão em inglês da proposta.

## Estado do trabalho

Em 19/10/2026, Rodrigo informou que concluiu as atividades das Semanas 2 e 3. As pastas `codigo/`, `dados/`, `resultados/`, `referencias/` e `texto/` ainda não contêm os artefatos dessas atividades; registrá-los no [ticket 01](.scratch/proximas-etapas-tcc/issues/01-reconciliar-progresso-e-protocolo.md). Ele também informou que o professor autorizou IA como apoio para otimizar o tempo; consulte o fluxo de uso e registre as ferramentas e validações. As datas da agenda são uma proposta e precisam ser ajustadas ao prazo oficial.

South German Credit havia sido escolhida para o plano experimental anterior; a documentação da base indica código bruto 0 = risco ruim e 1 = risco bom. Em 19/10/2026, Rodrigo refinou a direção do TCC para uma biblioteca open source de rotulagem assistida de dados financeiros com modelos leves locais. O protocolo antigo de comparação entre regressão logística e redes bayesianas precisa ser revisto antes de continuar sua execução.

## Biblioteca de rotulagem financeira

O código em `codigo/finlabel/` já cobre fontes CSV/SQLite somente leitura, monitoramento de esquema, análises determinísticas, rotulagem autônoma com quarentena, ciclo local de treino com gates de promoção e rollback, CLI e painel web. Escopo, limites e métricas estão no [PRD](docs/prd/finlabel.md); as decisões, nos [ADRs](docs/adr/). O que ainda não foi comprovado (dados reais, baseline simples, portabilidade) está listado no [roadmap](docs/roadmap-melhorias.md). Para experimentar, veja o [guia rápido](codigo/finlabel/docs/quickstart.md) e o comando `finlabel quickstart` descrito no [README da biblioteca](codigo/finlabel/README.md).

A proposta original da biblioteca continua em [Proposta_fluxo_reutilizavel.md](planejamento/Proposta_fluxo_reutilizavel.md); ela descreve revisão humana por registro, que o produto atual substituiu por quarentena e supervisão confiável (ADR-0004).
