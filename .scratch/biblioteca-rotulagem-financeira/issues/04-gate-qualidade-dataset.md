# 04: Validar integridade e cobertura do dataset de treino

**Status:** ready-for-human

**Plano:** `docs/superpowers/plans/2026-10-20-supervised-training-lifecycle.md`, Task 1.

## Objetivo

Criar a verificação determinística de dataset antes do fine-tuning. Integridade inválida bloqueia; cobertura por rótulo baixa/desbalanceada gera avisos. A verificação não baixa modelos nem importa bibliotecas de ML. O treino continua exigindo confirmação explícita para avisos e autorização do projeto.

## Escopo

- Campo opcional `min_examples_per_label` em configurações de tarefa, validado contra o conjunto de rótulos e compatível com tarefas JSON antigas.
- Serviço `inspect_training_dataset(project, dataset_path)` que valida JSONL/manifesto/hash/contagens/rótulos/proveniência/duplicatas/exclusões e compara snapshot da fonte CSV ou SQLite com a origem atual.
- Comando `finlabel dataset check DATASET` que mostra contagens, bloqueios, avisos e próximos passos, sem gravar consentimento ou criar artefatos de treino.
- Manter CSV/SQLite somente leitura, não mostrar valores de linhas por padrão e não importar torch/Transformers/PEFT/TRL.

## Critérios de aceite manual

- Dataset válido mostra estado e contagens por rótulo.
- Manifesto/hash/schema inválido, dataset vazio, rótulo desconhecido, proveniência duplicada, fonte alterada ou exclusões stale bloqueiam.
- Texto prompt/completion repetido, rótulo abaixo do mínimo ou desbalanceamento aparecem como aviso sem serem tratados como garantia de qualidade.
- Configuração de mínimo desconhecida, booleana, fracionária, zero ou negativa recebe erro claro; tarefa antiga sem mínimos segue carregando.
- `finlabel dataset check` funciona sem dependências de ML e não imprime prompts/valores de registros.
- O comando apenas verifica; nenhuma confirmação de treino é persistida.

## Limites da etapa

- Não criar split, não ajustar modelo, não avaliar adapter, não ativar modelo.
- Não adicionar nem executar testes automatizados, conforme `LOOP.md`; registrar comandos automatizados não executados.
- Executar somente verificações manuais com fixtures sintéticas locais.

## Comentários

### Implementação Task 1 — 2026-10-20

- Commit: `459ecde4ce7b394744f901a4636f7dd79b3d0fb6` (`codex/dataset-quality-gate`).
- Arquivos: `src/finlabel/labeling/task.py`, `src/finlabel/training/quality.py` (novo), `src/finlabel/cli.py`.
- Entregue: mínimos de exemplos por rótulo opcionais e compatíveis com JSON antigo; validação de chaves desconhecidas e valores booleanos, fracionários, zero e negativos; relatório de integridade/cobertura sem imports de ML; comando `dataset check` não persistente, sem impressão de registros, retornando próximo passo.
- Verificação manual com fixtures CSV sintéticas temporárias: dataset válido, vazio, hash divergente, snapshot stale, rótulo desconhecido, IDs de proveniência duplicados, conteúdo duplicado, rótulo ausente, abaixo do mínimo, tarefa antiga sem mínimos e mínimos inválidos. Todos os resultados esperados foram observados. Conteúdo duplicado e cobertura baixa/ausente produziram avisos; bloqueios de integridade tornaram `ready=false`.
- CLI conferida com `SECRET_ROW_VALUE` sintético: valor não apareceu na saída; `torch`, `transformers`, `peft` e `trl` não estavam em `sys.modules`; nenhuma autorização foi escrita.
- `git diff --check` passou.
- Testes automatizados não executados conforme `LOOP.md`: `python -m pytest`, `python -m unittest`, `pytest`.
- Auto-revisão: o checker usa leitura local de CSV/SQLite, bloqueia fonte não verificável e hash/schema/proveniência inconsistentes, e mantém avisos distintos de bloqueios. Revisão humana necessária antes do Task 2.
- Correção de revisão independente: `905ebbc6de255c376b3a4f2ddd913f53cc9a2ab1`; compartilhamento de contrato do manifesto, cobertura inclui rótulos com zero registros, e `null` explícito é inválido.
- Revisão independente e re-revisão: aprovada; findings resolvidos, nenhum problema novo no diff corretivo.
