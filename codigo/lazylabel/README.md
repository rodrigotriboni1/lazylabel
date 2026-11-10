# LazyLabel

Biblioteca para analisar e rotular dados financeiros, com linha de comando e painel web. Lê CSV e SQLite só para leitura, monitora o esquema, calcula análises exatas, rotula com quarentena e treina modelos com gates de promoção e rollback. Roda com modelos locais ou na nuvem pelo Vercel AI Gateway.

English quickstart: [docs/quickstart.md](docs/quickstart.md)

## Instalação

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e '.[web]'      # CLI + painel
uv pip install --python .venv/bin/python -e '.[models]'   # inferência local (torch)
uv pip install --python .venv/bin/python -e '.[train]'    # treino LoRA (torch)
```

## Início rápido

```bash
lazylabel quickstart ./demo --model-id Qwen/Qwen2.5-0.5B-Instruct   # projeto com 40 linhas sintéticas
lazylabel serve --project ./demo                                    # painel em http://127.0.0.1:8765
```

O `quickstart` não baixa modelo: só grava o id em `task.json`. Os valores da política de exemplo são ilustrativos, e toda previsão vai para a quarentena até existir calibração.

## Comandos principais

| Para… | Comando |
|---|---|
| Criar um projeto | `lazylabel project init ./meu-projeto` |
| Registrar uma fonte | `lazylabel source add-csv <nome> <arquivo.csv>` ou `source add-sqlite <nome> <banco.db> --table … --id-column …` |
| Mapear tipos | `lazylabel source set-type <fonte> <coluna> decimal` |
| Capturar e monitorar o esquema | `lazylabel schema capture <fonte> --output esquema.json` · `lazylabel monitor <fonte> --baseline esquema.json` |
| Calcular uma análise | `lazylabel analyze <fonte> --question "…" --plan plano.json` (ou `--model-id` para o modelo propor o plano) |
| Registrar uma tarefa | `lazylabel task add tarefa.json` |
| Registrar rótulos confiáveis | `lazylabel supervision add <fonte> --task <tarefa> --label-column <coluna> --provenance … --trust-kind provided_ground_truth` |
| Rotular | `lazylabel label <fonte> --task <tarefa>` · resumo: `lazylabel label-run <RUN_ID>` |
| Rotular e treinar | `lazylabel run --task <tarefa> --source <fonte>` · `run-status <RUN_ID>` · `model-status <tarefa>` |

Todos aceitam `--project <pasta>`. A configuração fica em `.lazylabel/project.json`; projetos antigos em `.finlabel/` continuam funcionando.

## Como funciona

1. **Fonte:** CSV ou SQLite, sempre só leitura. Tudo o que o LazyLabel produz vai para `.lazylabel/`.
2. **Análise:** um plano JSON revisável, executado com `Decimal`. O modelo que propõe o plano vê só nomes e tipos de colunas, nunca as linhas.
3. **Rotulagem:** o modelo vê só as colunas da tarefa. Um rótulo só é aplicado com saída válida, regras satisfeitas, fonte atual e confiança calibrada acima do limite; o resto vai para a quarentena com o motivo.
4. **Treino:** só com rótulos confiáveis, em partições congeladas. O candidato é promovido se passar em todos os gates no mesmo holdout do modelo atual, e há rollback automático se a saúde piorar.

Detalhes: [docs/rotulagem.md](docs/rotulagem.md) (tarefa, política e contrato de previsão) e [docs/treino.md](docs/treino.md) (rótulos confiáveis, `training-gate.json` e ciclo).

## Painel

`lazylabel serve --project <pasta>` abre o painel só em `127.0.0.1`, com checagem de Host, Origin e CSRF. São seis telas: Visão geral, **Perguntar**, Análises, Monitoramento, Rotulagem e Treinamento.

Cada tela é um arquivo JSON em `frontend/src/specs/`, renderizado com [json-render](https://github.com/vercel-labs/json-render) e shadcn. Para mudar uma tela, edite o JSON. Depois de mudar o frontend, rode `npm --prefix frontend run build` para atualizar `src/lazylabel/web/static/app`.

## Modelos na nuvem (Vercel AI Gateway)

Um id de modelo com prefixo `gateway:` usa o Vercel AI Gateway (decisão 8 em `tcc/decisoes.md`):

```bash
export AI_GATEWAY_API_KEY=...                                  # criada no painel da Vercel
export LAZYLABEL_UI_MODEL=gateway:anthropic/claude-haiku-4.5   # opcional: modelo que monta as telas do Perguntar
lazylabel analyze <fonte> --question "…" --model-id gateway:anthropic/claude-haiku-4.5
```

- **Onde vale:** no planejador de análise e na tela Perguntar.
- **Perguntar:** você revisa o plano, o LazyLabel calcula os números de forma exata e o modelo só monta o layout, com um catálogo de exibição. Telas com números que não vieram do cálculo são descartadas.
- **Rotulagem:** continua local, porque precisa da probabilidade de cada rótulo para calibrar a confiança.

## Desenvolvimento

```bash
bash ../../factory/checks.sh    # pytest, oxlint, vitest e tsc
```

Arquitetura em camadas (`domain` ← `application` ← `adapters` ← `bootstrap`): [docs/architecture/clean-hexagonal.md](docs/architecture/clean-hexagonal.md).
