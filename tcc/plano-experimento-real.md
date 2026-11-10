# Plano do primeiro experimento real do LazyLabel

- **Atualizado:** 09/11/2026 (rascunho anterior: 01/11/2026)
- **Estado:** não executado. O tema (decisão 7) ainda depende do orientador; a base e o baseline estão nas perguntas 3 e 4 de [perguntas-orientador.md](perguntas-orientador.md).
- **Objetivo:** a primeira evidência com dados reais. O ciclo `lazylabel run` com rótulos confiáveis reais, comparado a um baseline simples no mesmo teste final. Hoje só existe o experimento sintético (24 exemplos, em [experimentos/sintetico-qwen-0.5b/](experimentos/sintetico-qwen-0.5b/)), e o ciclo de treino só rodou com stub.
- **Base:** South German Credit corrigida (UCI), conforme o [protocolo](protocolo-experimental.md): 1000 registros, 20 variáveis, alvo `kredit` (0 = ruim, 1 = bom), 300 ruins e 700 bons.

## Pergunta e hipóteses

**Pergunta:** nos registros em que o LazyLabel aplica um rótulo, ele acerta tanto quanto um baseline simples? E em quantos registros ele aplica?

Escreva as hipóteses e os limiares abaixo **antes** de ver qualquer resultado, com a data. Mudar depois invalida a comparação.

| | Hipótese | Como medir |
|---|---|---|
| H1 | Nos registros aplicados, a acurácia do LazyLabel é ≥ à do baseline nesses mesmos registros | Acurácia e macro-F1 no teste final, restritas aos aplicados |
| H2 | Depois de um ciclo com promoção, a cobertura é maior que zero | Cobertura = aplicados ÷ total do teste |
| H3 | A confiança do LazyLabel é calibrada | Erro de calibração e Brier no teste final |

Se o baseline empatar ou vencer, esse é o resultado e deve ser reportado assim: dados tabulares podem não justificar um modelo de linguagem.

## Limiares (preencher antes de rodar)

O LazyLabel não presume nenhum valor. Registre os escolhidos e a data:

| Arquivo | Campo | Valor | Data |
|---|---|---|---|
| política de rotulagem | `min_calibrated_confidence` | | |
| política de promoção | `required_metrics` | | |
| política de promoção | `minimum_coverage` | | |
| política de promoção | `max_calibration_error` | | |
| política de promoção | `min_holdout_count` | | |

## Modelo

- **Rotulagem e treino: modelo local.** A rotulagem precisa da probabilidade de cada rótulo para calibrar a confiança, e o Vercel AI Gateway não fornece isso. Candidato: `Qwen/Qwen2.5-0.5B-Instruct`, o mesmo do experimento sintético. Precisa dos extras `models` e `train` (torch).
- **Nuvem:** autorizada pela decisão 8, mas fora deste experimento. Ela entra quando a rotulagem pela nuvem existir (opção a ser escolhida em [proximos-passos.md](proximos-passos.md)).
- O `training-gate.json` exige `model_id`, `license`, `hardware`, `data_policy`, `evaluation_protocol` e `authorized: true`. Sem ele, o ciclo não treina.

## Desenho contra vazamento

O LazyLabel cria as próprias partições (treino, calibração, holdout) a partir dos rótulos confiáveis. O protocolo exige, além disso, um teste final intocado:

1. Rode o baseline **sem** `--final`. Ele grava a divisão 80/20 (semente 42) em `split-indices.json` e faz validação cruzada só no desenvolvimento.
2. A partir desses índices, gere `dev.csv` (80%) e `teste.csv` (20%). Só `dev.csv` vira fonte do LazyLabel.
3. Rode o ciclo do LazyLabel só em `dev.csv`.
4. Congele e registre as duas configurações. Só então avalie `teste.csv` **uma única vez** com os dois (`--final` no baseline).
5. Compare no mesmo teste: acurácia, macro-F1, Brier, erro de calibração e cobertura. Compare também o baseline restrito aos registros que o LazyLabel aplicou.

Se algo exigir repetir o teste final, registre a correção e não apresente mais o teste como intocado.

## Checklist

| # | Passo | Quem |
|---|---|---|
| 1 | Aprovar base e baseline com o orientador (perguntas 3 e 4) | Você |
| 2 | Baixar a base da UCI e guardar o original sem alterar em `tcc/experimentos/sgc-real/dados/brutos/`, com fonte, data, SHA-256, número de linhas e dicionário | Você |
| 3 | Preencher hipóteses e limiares acima, com data | Você |
| 4 | Escolher modelo, conferir licença e hardware; escrever `training-gate.json` | Você |
| 5 | Rodar o baseline sem `--final` e gerar `dev.csv` e `teste.csv` | Claude |
| 6 | Escrever `tarefa-risco.json` e as políticas, a partir do `lazylabel quickstart` | Claude |
| 7 | Rodar o ciclo do LazyLabel em `dev.csv` e guardar `run-status` e `model-status` | Você (precisa de torch) |
| 8 | Avaliar o teste final uma vez com os dois e preencher a tabela de resultados | Claude |

## Comandos

```bash
E=tcc/experimentos/sgc-real

# 5. baseline (não abre o teste)
uv run --with scikit-learn --with pandas python codigo/experimento/baseline_logreg.py \
  --csv $E/dados/brutos/<arquivo>.csv --target kredit --numeric <colunas-numericas> --out $E/resultados/baseline

# 7. LazyLabel só com dev.csv
lazylabel project init $E/projeto
lazylabel source add-csv dev $E/dados/processados/dev.csv --project $E/projeto
lazylabel task add $E/tarefa-risco.json --project $E/projeto
lazylabel supervision add dev --task risco --label-column kredit \
  --provenance "UCI South German Credit, baixado em <data>" --trust-kind provided_ground_truth \
  --label-map '{"0":"bad","1":"good"}' --project $E/projeto
lazylabel run --task risco --source dev --project $E/projeto
lazylabel run-status <RUN_ID> --project $E/projeto
lazylabel model-status risco --project $E/projeto

# 8. teste final (uma única vez)
uv run --with scikit-learn --with pandas python codigo/experimento/baseline_logreg.py \
  --csv $E/dados/brutos/<arquivo>.csv --target kredit --numeric <colunas-numericas> --out $E/resultados/baseline --final
```

Detalhes do ciclo de treino: [codigo/lazylabel/docs/verified-training-cycle.md](../codigo/lazylabel/docs/verified-training-cycle.md).

## Resultados (preencher no passo 8)

| Métrica (teste final) | Baseline (todos) | Baseline (só aplicados) | LazyLabel |
|---|---|---|---|
| Acurácia | | | |
| Macro-F1 | | | |
| Brier | | | |
| Erro de calibração | | | |
| Cobertura | 100% | | |

## Riscos

- A coluna `kredit` nunca pode estar em `input_columns` da tarefa.
- Antes da primeira promoção, toda previsão pode ir para quarentena (`uncalibrated`), e o resultado pode ser "cobertura zero". Ver a pergunta 8 em [perguntas-orientador.md](perguntas-orientador.md).
- Com 800 registros de desenvolvimento divididos em três partições, o holdout interno fica pequeno; `min_holdout_count` precisa ser compatível com isso.
- A South German Credit não permite afirmar nada sobre carteiras brasileiras nem sobre inadimplência num horizonte definido.
