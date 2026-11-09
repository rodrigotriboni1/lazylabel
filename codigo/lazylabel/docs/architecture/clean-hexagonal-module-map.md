# LazyLabel — mapa final da arquitetura

Estado após o Milestone 6 (compatibilidade e enforcement). Para explicação do fluxo, composição e procedimento para adicionar conectores, veja [clean-hexagonal.md](clean-hexagonal.md).

## Regras verificadas no código

`tests/architecture/test_layer_dependencies.py` percorre todos os módulos Python em `src/lazylabel` e verifica imports declarados e relativos, inclusive dentro de funções. O conjunto transitório foi removido.

| Camada importadora | Pode importar | Não pode importar |
| --- | --- | --- |
| `domain` | Domínio e lista restrita de módulos puros da biblioteca padrão | Aplicação, adapters, bootstrap, frameworks, filesystem, processos, rede, modelos ou outros imports não puros |
| `application` | Aplicação, domínio e biblioteca padrão pura aprovada | Adapters, bootstrap, frameworks, filesystem, rede e modelos concretos |
| `adapters` | Adapters, aplicação e domínio | Bootstrap |
| `bootstrap` | Bootstrap, adapters, aplicação e domínio | Código externo não conectado por uma camada própria |
| Fachadas de compatibilidade | Apenas os destinos canônicos explicitamente declarados por fachada | Dependência lateral entre fachadas, lógica de implementação ou imports extras |

O mesmo teste garante que novos módulos são classificados (falham fechados se não classificados) e que fachadas não acumulam lógica. `tests/compatibility/` protege os imports públicos/legados e a importação lazy dos extras de web e ML. No frontend, `frontend/src/pages/` e `components/` usam a porta tipada; `tests/architecture/` e testes de cliente verificam que a apresentação não chama `fetch` nem importa o adapter HTTP diretamente.

## Composição e módulos canônicos

| Área | Localização canônica | Conteúdo |
| --- | --- | --- |
| Domínio | `src/lazylabel/domain/analysis/` | Planos, resultados, chart specs, cálculo e highlights determinísticos. |
| Domínio | `src/lazylabel/domain/labeling/` | Tarefas, valores/sugestões, validação e regras de decisão de rotulagem. |
| Domínio | `src/lazylabel/domain/monitoring/` | Baseline de schema e comparação determinística de qualidade. |
| Domínio | `src/lazylabel/domain/projects/` | Perfil e valores de colunas/dataset. |
| Domínio | `src/lazylabel/domain/training/` | Qualidade confiável, partições, métricas, calibração, avaliação e gates de promoção/rollback. |
| Portas da aplicação | `src/lazylabel/application/ports/` | `analysis.py`, `labeling.py`, `projects.py`, `sources.py`, `training.py`, `workspace.py`. Protocolos consumidos pela aplicação. |
| Casos de uso | `src/lazylabel/application/use_cases/` | `analysis.py`, `labeling.py`, `monitoring.py`, `projects.py`, `training.py`, `workspace.py` e erros tipados. |
| Entrada | `src/lazylabel/adapters/inbound/cli/commands.py` | Argumentos, apresentação CLI e delegação à aplicação. |
| Entrada | `src/lazylabel/adapters/inbound/http/app.py` | FastAPI, rotas, validação de requests, CSRF/origin/Host, erros e entrega dos assets. |
| Saída: fontes | `src/lazylabel/adapters/outbound/sources/` | Contratos concretos da fonte e conectores CSV/SQLite read-only, inspeção e leitura de labels confiáveis. |
| Saída: persistência | `src/lazylabel/adapters/outbound/persistence/` | Projeto/workspace, queries do painel, runs, resultados, schemas, políticas, datasets, idempotência e registry. |
| Saída: modelos | `src/lazylabel/adapters/outbound/models/` | Backend de geração, planner, inferência de labeling e modelo ativo. |
| Saída: treino | `src/lazylabel/adapters/outbound/training/` | Runtime de PEFT/TRL, jobs, avaliação e efeitos do ciclo. |
| Composição | `src/lazylabel/bootstrap/` | `application.py` conecta portas/implementações; `cli.py` e `http.py` constroem cada entrypoint. |
| UI: porta e composição | `frontend/src/application/` | Contrato `LazyLabelClient`, contexto e provider injetado. |
| UI: adapters | `frontend/src/adapters/http/`, `frontend/src/adapters/in-memory/` | Cliente wire e implementação em memória de teste. |
| UI: apresentação | `frontend/src/pages/`, `frontend/src/components/` | Páginas, navegação e componentes React; sem transporte HTTP próprio. |
| UI: bootstrap | `frontend/src/main.tsx`, `frontend/src/App.tsx` | Criação do adapter HTTP, provider e seleção da rota/apresentação. |

## Fachadas públicas preservadas

As fachadas abaixo são intencionais. O import antigo continua válido, enquanto código novo deve usar o destino canônico à direita.

| Import legado | Destino canônico/estado |
| --- | --- |
| `lazylabel` e exports do pacote | Exports públicos cobertos pelo contrato de compatibilidade; implementação em `domain/projects`, `adapters/outbound/sources` e `adapters/outbound/persistence`. |
| `lazylabel.cli:main` | `bootstrap.cli` e adapter `adapters.inbound.cli`; entrypoint definido em `pyproject.toml`. |
| `lazylabel.web.app:create_app` | Adapter `adapters.inbound.http.app:create_app` e composição `bootstrap.http:create_app`. |
| `lazylabel.project`, `profile`, `monitor`, `review` | Adapters locais de persistência/fontes e valores de domínio correspondentes. |
| `lazylabel.analysis.*` | `domain.analysis`, casos de uso de análise, adapters de planner/fonte/persistência. |
| `lazylabel.labeling.*` | `domain.labeling`, caso de uso e adapters de tarefa, modelo e persistência. |
| `lazylabel.sources.*` | Contratos em `adapters.outbound.sources.base` e conectores concretos em `adapters.outbound.sources`. |
| `lazylabel.models.*` | `application.ports` para contratos e `adapters.outbound.models` para execução. |
| `lazylabel.training.*` | `domain.training`, `application.use_cases.training`, `adapters.outbound.training` ou `persistence`, conforme a responsabilidade. |

Compatibilidade é mantida sem prometer remoção futura. Algumas fachadas reexportam nomes; outras usam identidade de módulo para conservar monkeypatch/extensão histórica. Não importe uma fachada de dentro de um módulo novo e não adicione regras às fachadas. Qualquer remoção precisa de decisão/versionamento próprios e atualização explícita dos testes de compatibilidade.

## Baseline e estado de validação

| Verificação no baseline (Milestone 1) | Resultado |
| --- | --- |
| Python 3.12.14, suíte completa | 128 testes + 17 subtestes passaram |
| Frontend | 10 testes; build passou com aviso de chunk acima de 500 kB |
| Lint frontend | Exit 0 com cinco avisos React existentes |

O sistema tinha Python 3.9, abaixo de `requires-python >=3.10`; as verificações atuais devem usar um interpretador suportado. Os resultados finais da campanha, incluindo avisos do baseline, HTTP e browser QA, estão em [task-13-report.md](../../.superpowers/sdd/2026-10-26-lazylabel-clean-hexagonal/task-13-report.md).
