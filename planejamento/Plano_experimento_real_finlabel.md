# Plano do primeiro experimento real do FinLabel

- **Data:** 2026-11-01
- **Estado:** rascunho, não executado. Depende da aprovação do orientador para o escopo (ADR-0007) e para a base e o baseline (perguntas 1–4 de [Proposta_fluxo_reutilizavel.md](Proposta_fluxo_reutilizavel.md)).
- **Objetivo:** produzir a primeira evidência com dados reais: o ciclo `finlabel run` com rótulos confiáveis reais, comparado a um baseline simples no mesmo recorte. Hoje só existe experimento sintético (24 exemplos) e o ciclo de treino só foi exercitado com stub.
- **Base:** South German Credit corrigida, conforme [Protocolo_experimental.md](Protocolo_experimental.md): 1000 registros, 20 variáveis, alvo `kredit` (0 = ruim, 1 = bom), amostra estratificada de 300 ruins e 700 bons.

## O que já está pronto

- Baseline: `codigo/experimento/baseline_logreg.py`. Faz a divisão 80/20 com semente 42 e salva os índices, roda validação cruzada de 5 partições só no desenvolvimento e só abre o teste final com `--final`. Foi testado apenas com dados sintéticos gerados para este plano; não foi executado na base real.
- Ciclo do FinLabel: `finlabel project init`, `source add-csv`, `task add`, `supervision add`, `run`, `run-status`, `model-status` (ver `codigo/finlabel/README.md` e `docs/verified-training-cycle.md`).

## O que falta e só você pode fazer

1. **Obter a base** na página da UCI citada no protocolo e guardar o original em `dados/brutos/`, sem alterar. Registrar fonte, data, hash SHA-256, número de linhas e dicionário (o protocolo já pede isso). Não baixei nada.
2. **Escolher o modelo, verificar a licença e o hardware.** O `training-gate.json` exige `model_id`, `license`, `hardware`, `data_policy`, `evaluation_protocol` e `authorized: true`. Sem isso o ciclo não treina.
3. **Definir os limiares.** O FinLabel não presume nenhum: política de rotulagem (`min_calibrated_confidence`, regras) e política de promoção (`required_metrics`, `minimum_coverage`, `max_calibration_error`, `min_holdout_count`). Defina-os antes de ver resultados e registre a data.
4. **Rodar o treino**, que precisa dos extras `models`/`train` (torch) na sua máquina.

## Desenho para evitar vazamento

O ciclo do FinLabel cria suas próprias partições de treino, calibração e holdout a partir da fonte de rótulos confiáveis. O protocolo exige também um teste final intocado. Por isso:

1. Rode o baseline sem `--final` para gerar `split-indices.json`.
2. Escreva dois CSVs a partir desses índices: `dev.csv` (80%) e `teste.csv` (20%). Só `dev.csv` vira fonte do FinLabel.
3. Rode o ciclo do FinLabel só em `dev.csv` (rotulagem + rótulos confiáveis + treino + holdout interno).
4. Congele a configuração do baseline e a do FinLabel, registre-as, e só então avalie `teste.csv` **uma única vez** com os dois (`--final` no baseline).
5. Compare no mesmo teste: acurácia, macro-F1, Brier, erro de calibração e cobertura. Cobertura só existe para o FinLabel, porque ele pode se abster; compare também o baseline restrito aos mesmos registros aplicados.

Se algo exigir repetir o teste final, registre a correção e não o apresente como intocado depois disso (regra do protocolo).

## Comandos (modelo, a ajustar)

```bash
# 1. baseline (não abre o teste)
uv run --with scikit-learn --with pandas python codigo/experimento/baseline_logreg.py \
  --csv dados/brutos/<arquivo>.csv --target kredit --numeric <colunas-numericas> --out resultados/baseline

# 2. projeto FinLabel só com dev.csv
finlabel project init ./projeto-sgc
finlabel source add-csv dev ./dados/processados/dev.csv --project ./projeto-sgc
finlabel task add ./tarefa-risco.json --project ./projeto-sgc
finlabel supervision add dev --task risco --label-column kredit \
  --provenance <origem-registrada> --trust-kind provided_ground_truth \
  --label-map '{"0":"bad","1":"good"}' --project ./projeto-sgc
finlabel run --task risco --source dev --project ./projeto-sgc
finlabel run-status RUN_ID --project ./projeto-sgc
finlabel model-status risco --project ./projeto-sgc
```

`finlabel quickstart` gera um projeto de exemplo com arquivos iniciais de tarefa e política, que servem de modelo para `tarefa-risco.json` e para a política.

## Riscos

- A coluna de rótulo confiável nunca pode estar em `input_columns` da tarefa.
- Dados tabulares podem não justificar um LLM: se o baseline empatar ou vencer, esse é o resultado e deve ser reportado como tal.
- Antes da primeira promoção, toda previsão pode ficar em quarentena (`uncalibrated`). A pergunta ao orientador em [pergunta-orientador-calibracao-modelo-base.md](../docs/pergunta-orientador-calibracao-modelo-base.md) trata disso; o resultado do ciclo pode ser "cobertura zero" até haver promoção.
- South German Credit não permite afirmar nada sobre carteiras brasileiras nem sobre inadimplência em horizonte definido.
