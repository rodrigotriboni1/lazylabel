# TCC de Rodrigo Mialichi Triboni

**Tema:** Redes bayesianas e utilidade esperada aplicadas à seleção de *next best action* em sistemas automatizados de decisão.

## Por onde começar

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
| `codigo/finlabel/` | Primeiro incremento da biblioteca local de rotulagem financeira (`finlabel-local`) |
| `.documentos_qa/` | PDFs, imagens renderizadas e arquivos auxiliares de conferência de documentos |

## Entregas existentes

- `entregas/Apresentacao_do_andamento_TCC_Rodrigo.docx` — apresentação de andamento.
- `entregas/TCC_Research_Proposal_Rodrigo_English.docx` — versão em inglês da proposta.

## Estado do trabalho

Em 19/10/2026, Rodrigo informou que concluiu as atividades das Semanas 2 e 3. As pastas `codigo/`, `dados/`, `resultados/`, `referencias/` e `texto/` ainda não contêm os artefatos dessas atividades; registrá-los no [ticket 01](.scratch/proximas-etapas-tcc/issues/01-reconciliar-progresso-e-protocolo.md). Ele também informou que o professor autorizou IA como apoio para otimizar o tempo; consulte o fluxo de uso e registre as ferramentas e validações. As datas da agenda são uma proposta e precisam ser ajustadas ao prazo oficial.

South German Credit havia sido escolhida para o plano experimental anterior; a documentação da base indica código bruto 0 = risco ruim e 1 = risco bom. Em 19/10/2026, Rodrigo refinou a direção do TCC para uma biblioteca open source de rotulagem assistida de dados financeiros com modelos leves locais. O protocolo antigo de comparação entre regressão logística e redes bayesianas precisa ser revisto antes de continuar sua execução.

## Biblioteca de rotulagem financeira

A direção mais recente do projeto está registrada na [proposta da biblioteca](planejamento/Proposta_fluxo_reutilizavel.md) e no [épico atualizado](.scratch/proximas-etapas-tcc/epico.md). O primeiro incremento em `codigo/finlabel/` inspeciona CSVs localmente; fine-tuning de modelos leves, revisão humana e avaliação ainda serão implementados em etapas posteriores, após definição do modelo, hardware e protocolo.
