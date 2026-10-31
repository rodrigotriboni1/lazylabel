# 07: Avaliar adapter candidato no holdout reservado

**Status:** ready-for-human

**Plano:** `docs/superpowers/plans/2026-10-20-supervised-training-lifecycle.md`, Task 4.

## Objetivo

Comparar o modelo-base e um adapter candidato nos mesmos prompts do holdout, com métricas por classe e artefato local vinculado aos hashes do bundle.

## Escopo

- Estender `TransformersTextGenerationBackend` com `adapter_path` opcional; carregar PEFT de forma lazy e manter comportamento base-only.
- `LabelMetrics(label, support, precision, recall, f1)` e `EvaluationReport` com referências, hashes do adapter/dataset/split, métricas globais, métricas por rótulo, matriz de confusão, IDs opacos de erros e avisos.
- `evaluate_candidate(bundle, task, adapter_path, output_path)` valida adapter, tarefa, bundle e hashes; passa prompts idênticos na mesma ordem ao modelo-base e candidato; salva relatório local sem prompts/valores dos registros.
- Métricas: acurácia, macro-F1, precision/recall/F1/support por classe. Predições inválidas/desconhecidas são contabilizadas explicitamente. Métricas indefinidas são JSON `null`.

## Critérios de aceite manual

- Fakes determinísticos confirmam prompts e ordem idênticos para base e adapter e que holdout/hash não muda.
- Fixture inclui melhora global com regressão em uma classe e o relatório mostra ambos por classe; saídas malformadas contam como inválidas e entram no denominador documentado.
- Adapter ou tarefa incompatível, hash de adapter/split/holdout divergente e output existente falham sem sobrescrever nada.
- Relatório contém apenas métricas, avisos, hashes e IDs opacos; sem prompts nem valores de registros.
- Não carregar pesos reais, não baixar modelos e não executar fine-tuning; não adicionar nem executar testes automatizados.

## Comments

### Implementação de 2026-10-20

- Arquivos de código: `src/finlabel/models/text_generation.py` e `src/finlabel/training/evaluation.py`, no branch `codex/training-evaluation`. A avaliação valida hashes do bundle e do adapter, identidade da tarefa/modelo/revisão e prompts contra o esquema atual; usa o mesmo modelo-base, tokenizer, ordem e `max_new_tokens=96` determinístico. O backend PEFT é lazy e local (`local_files_only=True`, sem `trust_remote_code`). O comando CLI canônico ficará para o Task 5, quando existir versão registrada.
- Evidência manual: script inline com dez registros sintéticos e backends injetados; ambos receberam os mesmos dez prompts na mesma ordem e com as mesmas opções. A acurácia passou de `0.70` (base) para `0.80` (candidato), enquanto o recall da classe B caiu de `1.0` para `0.3333333333333333`. Uma saída malformada contou em `invalid_count=1`, na célula B → `__invalid__` e no denominador de dez registros. O hash do holdout ficou igual. O JSON salvo não continha os valores sintéticos `SECRET_ROW_` nem o campo `prompt`.
- Bloqueios manuais: output existente gerou `FileExistsError`; tarefa incompatível, peso alterado e holdout alterado geraram `ValueError`. Nenhum dos três outputs bloqueados foi criado. O código também revalida o bundle e o adapter antes de publicar o relatório.
- Limites: não houve carregamento de pesos reais, download, inferência Transformers/PEFT real, fine-tuning nem execução de testes automatizados. `python` não estava no PATH; o script manual foi executado com `python3`. Não foram executados `pytest`, `unittest`, `python -m unittest`, comandos `finlabel train` ou `finlabel model evaluate`.

### Correções após revisão independente

- Falhas `ValueError` do backend agora interrompem a avaliação; apenas saída gerada malformada vira predição inválida. O parser do holdout usa o prefixo exato da tarefa, inclusive quando as instruções contêm `Selected input JSON:`. O output é checado antes da normalização do path, bloqueando symlink pendente. `error_ids` aponta para IDs opacos de sugestões no holdout, validados em quantidade, formato e unicidade.
- Evidência manual adicional com dez registros sintéticos: os prompts/opções continuaram idênticos; acurácia `0.7 → 0.8`, recall B `1.0 → 0.3333333333333333`, uma predição inválida, ID de erro igual ao ID de sugestão da linha correspondente e hash do holdout inalterado. Instruções contendo o marcador de prompt foram aceitas. `ValueError` do gerador impediu a criação do relatório; symlink pendente gerou `FileExistsError` e foi preservado. Nenhum teste automatizado ou modelo real foi executado.
- Revisão independente da rodada de correções: aprovada; os quatro apontamentos foram resolvidos e nenhum problema novo foi encontrado. Sem testes executados.
