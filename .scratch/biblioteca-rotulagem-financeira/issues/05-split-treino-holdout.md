# 05: Separar dataset em treino e holdout reproduzíveis

**Status:** ready-for-human

**Plano:** `docs/superpowers/plans/2026-10-20-supervised-training-lifecycle.md`, Task 2.

## Objetivo

Criar uma divisão local, determinística e auditável entre exemplos usados no ajuste e exemplos reservados para avaliação, sem permitir vazamento de proveniência.

## Escopo

- `SplitConfig(strategy, holdout_fraction, seed, group_column=None, time_column=None)` com estratégias explícitas `stratified_random`, `temporal` e `group`; nunca inferir coluna temporal/grupo.
- `TrainingBundle` com caminhos train/holdout/manifest, relatório do gate, contagens, hash do split e avisos.
- `create_training_bundle(project, dataset_path, task, config, output_dir)` revalida a qualidade e o snapshot da origem; resolve manifesto/run/task; reconstitui as linhas em ordem de proveniência e confere digests antes de extrair apenas a chave de split selecionada.
- Artefatos de treino/holdout usam somente `prompt`/`completion`. Manifesto registra dataset hash, estratégia, seed, contagens, distribuição por rótulo e IDs opacos de sugestão/evento; não persistir valores brutos de colunas temporal/grupo.
- CLI `finlabel dataset split DATASET --strategy ... --holdout-fraction ... --seed ... --output ... [--time-column ...] [--group-column ...]`.

## Critérios de aceite manual

- Configuração inválida, chaves incompatíveis, valores faltantes na chave, digests alterados, tipos não suportados e diretório de saída existente falham com mensagem clara.
- Estratificação é determinística e falha se suporte de uma classe não puder existir nas duas partições.
- Temporal ordena explicitamente por tempo, com desempate estável por ID; grupo mantém cada grupo inteiro numa partição e ordena grupos com seed.
- IDs de sugestão/evento nunca atravessam partições. Estratégias temporal/grupo que não preservem classes avisam sem fallback para aleatório.
- Repetição com a mesma seed gera hashes idênticos; seed diferente pode mudar a partição. Manifesto não contém valores crus de grupo/tempo.
- Somente fixtures sintéticas; não adicionar nem executar testes automatizados. Não treinar nem baixar pesos.

## Limites

O split nunca autoriza fine-tuning; a etapa seguinte revalidará todos os artefatos antes de qualquer import de ML.

## Comments

### Implementação em 2026-10-20

- Branch `codex/training-split`, commit `f48b6eef6cc1836562084b3d3718bec986ce048b` (base `905ebbc6de255c376b3a4f2ddd913f53cc9a2ab1`). Arquivos: `src/finlabel/training/split.py`, `src/finlabel/training/dataset.py`, `src/finlabel/cli.py`.
- Entregue: configuração validada; split estratificado, temporal com tipo e coluna explícitos, e por grupo sem separar grupos; revalidação do gate, dataset, run, sugestões, revisão, digests e prompts; JSONL local com `prompt`/`completion`; manifesto com hashes, qualidade, distribuição e IDs opacos. Nenhum valor bruto da chave temporal/de grupo é escrito no manifesto.
- Fixture sintética local em `/var/folders/v8/34yccs6d38751np_xl1m240h0000gn/T/finlabel-task2-manual-xd080qft`: oito linhas CSV, quatro por rótulo, datas de 2026-01-01 a 2026-01-08 e quatro grupos de duas linhas. Criada com script ad hoc via `PYTHONPATH=src python3 - <<'PY'`; `PYTHONPATH=src python3 -m finlabel.cli dataset prepare 071aa874330b437c86392134f3ebf26f --output <fixture>/dataset.jsonl --project <fixture>` produziu oito linhas e SHA-256 `c2ceb002668a52c7b92a9f1a81e82de6b7776c5d503dd09418f4ecc82e93b0df`.
- Comando manual de split: `PYTHONPATH=src python3 -m finlabel.cli dataset split <fixture>/dataset.jsonl --strategy stratified_random --holdout-fraction 0.25 --seed 17 --output <fixture>/split-a --project <fixture>`. Resultado: 6 treino, 2 holdout, hash `3f4223e6a60164e1ebc113c2c1245ff98b1c079664649f98380ed03d97f7ce97`. Repetição em `split-b` deu o mesmo hash. Seed 19 em `split-d` mudou holdout de casos 0/3 para 5/6 e hash para `a28820cb6959ba6fc6477cd6bd4c4465fd223278eeda6ede6a1e916b3b0de37c`.
- Com os mesmos parâmetros e `--strategy temporal --time-column when`, holdout contém casos 6/7, os mais recentes; `--strategy group --group-column group` contém casos 0/1, ambos do mesmo grupo. Inspeção ad hoc dos JSONL/manifestos mostrou apenas `prompt`/`completion`, zero interseção de IDs de sugestão/evento e ausência dos valores `group-` e `2026-01-` nos manifestos.
- Rejeições observadas pelo CLI (código 2): fração 0; coluna temporal ausente; grupo e tempo simultâneos; coluna temporal sem tipo explícito; diretório de saída já existente; chave temporal vazia; snapshot de origem alterado; digest da linha alterado mesmo após atualizar manualmente o snapshot de fixture. Chamadas ad hoc a `_partition` confirmaram falha para classe com um exemplo e avisos quando grupo separa totalmente classes; `_selected_key` rejeitou bytes e NaN.
- Verificação de integridade do commit: `git diff --cached --check` sem problemas antes de `git commit`. Comando `dataset split` executado novamente após a revisão de código, com hash idêntico `3f4223e6...`. Nenhuma fonte CSV/SQLite do usuário foi modificada; as mutações descritas foram somente na fixture temporária.
- Não executados: testes automatizados, `pytest`, build, downloads de modelo, importação de ML e treinamento real, conforme `LOOP.md` e restrição do ticket. Limite: a confirmação é manual e com dados sintéticos; o backend de treino deve revalidar o manifesto e os hashes antes de carregar ML.

### Correção após revisão independente

- Commit adicional `4fb30ef5996e9def07a81d3f5cd01efe7d2fa17a`: IDs numéricos de grupo equivalentes, como `1` e `1.0`, agora geram a mesma chave canônica; a string `'1'` continua distinta. A conversão exata de floats evita agrupar aproximações numéricas diferentes.
- Prova manual via `PYTHONPATH=src python3 - <<'PY'` com grupos `[1, 1.0, 2, 2.0, '1', '1', 3, 3.0]`: índices 0/1 ficaram ambos no holdout, 2/3 ambos no treino; execução repetida com seed 17 produziu partições idênticas. Não foram adicionados nem executados testes automatizados.

### Segunda correção após revisão

- Commit `fc5d06642ac766cd6b2fe496ad6d2c6f69e4c3ac`: removido `Decimal.normalize()`, que podia arredondar IDs inteiros grandes no contexto Decimal ativo. O valor numérico exato agora é preservado.
- Prova manual: `1`/`1.0` equivalentes e na mesma partição; `10**30`/`10**30+1` distintos; float aproximado `1e23` distinto do inteiro exato `10**23`; string `'1'` distinta do número; partição com seed 17 idêntica em duas execuções. Detalhes no relatório de Task 2. Sem testes automatizados, download ou treino.

- Re-revisão independente: correção para equivalência numérica aprovada; sem novos achados. Commits finais `4fb30ef` e `fc5d066`.
