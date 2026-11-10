# Glossário

Vocabulário do projeto (TCC + biblioteca LazyLabel). Use estes termos em issues, specs, testes e documentos. Fonte: o código em `codigo/lazylabel`.

## Projeto

| Termo | Significado |
|---|---|
| **TCC** | Trabalho de conclusão de curso de Rodrigo Mialichi Triboni. O tema submetido foi redes bayesianas e utilidade esperada para *next best action*; a direção atual é a biblioteca LazyLabel (ver [decisão 7](decisoes.md)). |
| **LazyLabel** (`lazylabel`) | Biblioteca Python local-first para análise e rotulagem autônoma de dados financeiros, com CLI e painel web. Código em `codigo/lazylabel/`. |
| **Projeto** (LazyLabel) | Pasta de trabalho do usuário criada por `lazylabel project init`; guarda configuração e artefatos em `.lazylabel/`. Não confundir com o repositório do TCC. |
| **Workspace** | Conjunto de arquivos locais de um projeto LazyLabel (`.lazylabel/`): configuração, execuções, modelos, partições. É a fronteira de confiança. |

## Dados

| Termo | Significado |
|---|---|
| **Fonte** (`DataSource`) | Origem de dados registrada no projeto: CSV ou SQLite, sempre abertos **somente leitura**. |
| **Referência opaca** (`record_ref`) | Identificador derivado/opaco de um registro. Resumos e evidências usam isto, nunca a linha bruta nem CPF/CNPJ. |
| **Digest** | Hash SHA-256 de campos selecionados ou de um artefato; detecta alteração, não prova autoria. |
| **Esquema / baseline** | Estrutura esperada de uma fonte (colunas, tipos, obrigatórias, limites de ausentes), capturada por `schema capture` e confirmada pelo usuário. |
| **Monitoramento** | Comparação da fonte atual com o baseline confirmado (`lazylabel monitor`). |

## Rotulagem

| Termo | Significado |
|---|---|
| **Tarefa** | Definição declarativa (JSON): instruções, `input_columns`, `labels`, `model_id`/revisão. O modelo só vê `input_columns`. |
| **Política de rotulagem** | Regras e limites por tarefa que decidem se uma previsão pode ser aplicada. Nunca há limite universal presumido. |
| **Previsão** (`Prediction`) | Saída estruturada e imutável do modelo: rótulo, justificativa opcional, evidência por classe, método, digest da resposta. |
| **Confiança calibrada** | Confiança derivada de um **calibrador** validado para política, tarefa, modelo e método. Confiança autorreportada pelo modelo é rejeitada. |
| **Calibrador** | Artefato imutável por modelo exato que mapeia escores brutos em confiança; guardado em `.lazylabel/models/calibrators/`. |
| **Aplicado** | Estado terminal: previsão válida, regras satisfeitas, origem atual e confiança calibrada suficiente. |
| **Quarentena** | Estado terminal automático: saída inválida, rótulo desconhecido, regra violada, fonte desatualizada, confiança ausente/insuficiente ou erro. O registro não recebe rótulo final; não exige revisão humana. |
| **Cobertura** | Fração de linhas efetivamente **aplicadas**. Quarentenas permanecem no denominador. |
| **Rótulo confiável** (*trusted label*) | Rótulo de referência declarado pelo operador (`provided_ground_truth` ou `validated_rule`). Único alvo permitido para treino e avaliação. Previsão do modelo nunca vira rótulo confiável. |
| **Supervisão** | Registro (`lazylabel supervision add`) da fonte de rótulos confiáveis de uma tarefa, com proveniência. |
| **ReviewLog / revisão humana** | Mecanismo do MVP inicial (aceitar/corrigir/rejeitar por registro). Legado, só leitura; fora do fluxo autônomo ([decisão 4](decisoes.md)). |

## Treino e ciclo de vida do modelo

| Termo | Significado |
|---|---|
| **Partições congeladas** | Treino / calibração / **holdout** imutáveis, em `.lazylabel/trusted-datasets/<task>/<snapshot-sha256>/`, reconstruídas e comparadas byte a byte. |
| **Holdout** | Partição reservada só para avaliar candidato e incumbente. |
| **Candidato** | Adapter novo (PEFT/LoRA) treinado só na partição de treino. |
| **Incumbente** | Modelo ativo (ou o modelo-base exato antes da primeira promoção) contra o qual o candidato é comparado no mesmo holdout. |
| **Gate de treino** (`training-gate.json`) | Autorização explícita local: modelo, licença, hardware, política de dados, protocolo e `authorized: true`. |
| **Gate de promoção** | Política por tarefa (`promotion-policies/<task>.json`): métricas mínimas, cobertura, regressão por rótulo, erro de calibração, limites de rollback, tamanho mínimo do holdout. |
| **Promoção** | Troca do ponteiro de modelo ativo, só se **todos** os gates passam; gera evento hash-vinculado. |
| **Rejeição** | Candidato reprovado; modelo ativo permanece e o motivo é registrado. |
| **Ciclo bloqueado** | Pré-requisito ausente/inválido (política, rótulos, artefatos, gates); nada é treinado nem promovido. |
| **Rollback** | Retorno automático à versão anterior verificada quando a saúde pós-promoção viola `rollback_monitor_limits`. |
| **Registry** | Diário de eventos de modelo (`ModelRegistry`) com lock de arquivo e reprodução verificada. |
| **Fail closed** | Em dúvida, a biblioteca não aplica rótulo e não promove modelo. |

## Arquitetura

| Termo | Significado |
|---|---|
| **Domínio** | `src/lazylabel/domain/*`: regras e cálculos puros, sem I/O. |
| **Aplicação / casos de uso** | `application/use_cases`, depende de domínio e **portas**. |
| **Porta** | Protocolo em `application/ports/` que a aplicação exige. |
| **Adapter** | Implementação de porta (`adapters/inbound` CLI/HTTP; `adapters/outbound` fontes, persistência, modelos, treino). |
| **Bootstrap** | `src/lazylabel/bootstrap/`: única camada que conecta adapters concretos. |
| **Fachada de compatibilidade** | Módulos legados (`lazylabel.training.*`, `lazylabel.cli`…) que só encaminham para o caminho canônico. |
| **Painel** | App React local servido pelo FastAPI em loopback (`lazylabel serve`). |

## Processo (skills do agente)

| Termo | Significado |
|---|---|
| **Issue** | Tarefa de código no GitHub; com o label `factory`, vira PR automaticamente (ver `AGENTS.md`). |
| **Rótulos de triagem** | `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. |
| **Decisão** | Escolha de projeto registrada, com contexto e consequências, em `decisoes.md`. |
