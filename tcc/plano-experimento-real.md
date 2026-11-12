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
| política de rotulagem | `min_calibrated_confidence` | 0,80 | 10/11/2026 |
| política de promoção | `required_metrics` | `{"macro_f1": 0.55}` | 10/11/2026 |
| política de promoção | `minimum_coverage` | 0,10 | 10/11/2026 |
| política de promoção | `max_calibration_error` | 0,12 | 10/11/2026 |
| política de promoção | `min_holdout_count` | 100 | 10/11/2026 |
| política de promoção | `allowed_per_label_regression` | `{"bad": 0.10, "good": 0.10}` | 10/11/2026 |
| política de promoção | `rollback_monitor_limits` | `{"macro_f1": 0.50, "calibration_error": 0.20}` | 10/11/2026 |

Justificativas:
- **0,80:** prever sempre `good` acerta 70%, e 0,80 fica 10 pontos acima disso.
- **macro-F1 0,55:** prever sempre `good` dá cerca de 0,41.
- **ECE 0,12:** simulando um modelo perfeitamente calibrado com n = 120, o percentil 95 do ECE é cerca de 0,107.
- **Holdout de 100:** a partição real fica em torno de 120 (70/15/15 de 800).
- **Mudar limiar depois:** exige projeto novo, porque o calibrador colide (`calibration_artifact_collision`).

**Desfechos pré-registrados:** "sem promoção" e "cobertura zero" são resultados válidos e serão reportados como tais.

**Hipóteses refinadas (10/11/2026), substituem as da tabela acima:**
- **H1 (descritiva):** a acurácia nos aplicados não fica mais de 5 pontos abaixo da do baseline na mesma cobertura (curva risco-cobertura). Os intervalos são declarados largos.
- **H2:** o ciclo promove um modelo e a cobertura no teste é de pelo menos 0,10.
- **H3:** ECE e Brier são medidos em todas as previsões do teste, não só nos aplicados, como confiança no rótulo previsto (top-label) nos dois sistemas.
- **Também reportar** a matriz de confusão nos aplicados.

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
| 7b | Teste de fumaça: taxa de saídas válidas do modelo-base em 50 registros do dev, registrada antes do congelamento | Claude |
| 8 | Avaliar o teste final uma vez com os dois (LazyLabel: `source add-csv teste` + `lazylabel label`, junção por `record_ref`) e preencher a tabela de resultados | Claude |

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

Teste final aberto uma única vez em 11/11/2026 (`resultados/TESTE-ABERTO`), 200 registros. Fonte: `experimentos/sgc-real/resultados/final.json`.

| Métrica (teste final) | Baseline (todos) | Baseline (mesmos registros) | Baseline (mesma cobertura) | LazyLabel (aplicados) | LazyLabel (todas as previsões) |
|---|---|---|---|---|---|
| n | 200 | 104 | 104 | 104 | 200 |
| Acurácia | 0,740 | 0,817 | 0,837 | 0,837 | 0,740 |
| Macro-F1 | 0,662 | 0,450 | 0,694 | 0,455 | 0,615 |
| Brier (top-label) | 0,179 | 0,144 | 0,137 | 0,136 | 0,179 |
| ECE (top-label) | 0,068 | 0,059 | 0,072 | 0,010 | 0,020 |
| Cobertura | 100% | — | 52% | 52% | — |

- **Ciclo:** o candidato LoRA foi promovido. No holdout interno (120 registros), teve acurácia 0,758, macro-F1 0,658, ECE 0,087 e cobertura 0,44, contra 0,667, 0,479 e cobertura 0 do modelo-base.
- **H1:** sustentada. Na mesma cobertura, as acurácias são iguais (0,837 e 0,837). Nos mesmos registros, o IC 95% pareado da diferença de acurácia é [0,000; 0,048].
- **H2:** sustentada. Houve promoção, e a cobertura no teste foi de 0,52, acima de 0,10.
- **H3:** favorável. O ECE do LazyLabel em todas as previsões é 0,020, contra 0,068 do baseline; o Brier é igual (0,179). Não havia limite fixado para H3 no teste.
- **Achado principal:** os 104 registros aplicados são todos `good`, e nenhum `bad` passou do limiar. O LazyLabel só automatiza a classe majoritária; dos 60 `bad` do teste, 17 foram aplicados errado como `good` e 43 ficaram em quarentena (17 deles com a previsão `bad` correta, mas abaixo do limiar). Por isso o macro-F1 nos aplicados é baixo (0,455), mesmo com acurácia alta.

## Riscos

- A coluna `kredit` nunca pode estar em `input_columns` da tarefa.
- Antes da primeira promoção, toda previsão pode ir para quarentena (`uncalibrated`), e o resultado pode ser "cobertura zero". Ver a pergunta 8 em [perguntas-orientador.md](perguntas-orientador.md).
- Com 800 registros de desenvolvimento divididos em três partições, o holdout interno fica pequeno; `min_holdout_count` precisa ser compatível com isso.
- A South German Credit não permite afirmar nada sobre carteiras brasileiras nem sobre inadimplência num horizonte definido.

## E1b — limiar por rótulo (exploratório, 11/11/2026)

**Exploratório.** O teste do E1 já tinha sido aberto. Aqui as mesmas 200 previsões salvas são reclassificadas com os limiares da decisão 10 (`bad` 0,60, `good` 0,80), sem inferência nova. Fonte: `experimentos/sgc-real/resultados/e1b-exploratorio.json`.

| | LazyLabel (aplicados) | Baseline (mesma cobertura) |
|---|---|---|
| n (cobertura) | 116 (58%) | 116 |
| Acurácia | 0,828 | 0,836 |
| Macro-F1 | 0,685 | 0,719 |
| `bad` aplicados (certos) | 12 (9) | 14 (11) |
| ECE | 0,015 | 0,072 |

O limiar por rótulo passa a aplicar a classe `bad`: a precisão nela foi de 75% e o macro-F1 nos aplicados subiu de 0,455 para 0,685, com a acurácia praticamente igual. A confirmação fica para o teste do E2, que ainda está fechado.
