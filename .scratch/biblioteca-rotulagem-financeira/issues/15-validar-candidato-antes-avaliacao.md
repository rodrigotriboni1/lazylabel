# 15: Validar artefatos do candidato antes da avaliação web

**Status:** ready-for-human

**Origem:** revisão cumulativa final do issue 13.
**Branch:** `codex/evaluation-integrity-fix`, base `ec701e3` (`codex/finlabel-lifecycle`).

## Objetivo

Impedir que a avaliação carregue ou execute um adapter/bundle modificado depois do registro do candidato.

## Escopo

- Validar adapter, metadados e partições do bundle contra os hashes imutáveis do registro antes de enfileirar avaliação.
- Revalidar dentro do worker imediatamente antes de chamar o avaliador, fechando a janela entre enqueue e execução.
- Em caso de divergência, persistir falha do job e manter candidato em `awaiting_evaluation`; não carregar adapter nem publicar/registrar resultado.

## Critério de aceite manual

- Com candidato sintético válido, confirmação e avaliação fake: validação passa e o caminho chega ao avaliador.
- Depois de alterar bytes do adapter ou bundle, ambos os pontos de validação recusam antes do avaliador; job permanece/torna `failed`, sem evento de avaliação ou mudança de estado do registry.
- `py_compile` e `git diff --check`; nenhum teste automatizado, download, inferência ou treino real.

## Implementação

Worktree: `codigo/finlabel/.worktrees/evaluation-integrity-fix`.

## Implementação e revisão

- Commit `59f6205` na branch `codex/evaluation-integrity-fix`, integrada por fast-forward em `codex/finlabel-lifecycle` após aprovação independente.
- `ModelRegistry` valida novamente o digest canônico do manifesto e hashes de partições, adapter e metadados; o enqueue valida antes de criar job e o worker repete a validação imediatamente antes do avaliador.
- Probe sintético: adapter adulterado antes do enqueue foi rejeitado sem job; partição/manifesto adulterados após enqueue resultaram em job `failed`, sem chamar evaluator nem registrar avaliação; candidato íntegro atingiu evaluator falso e foi registrado.
- `py_compile` e `git diff --check` passaram. Sem testes automatizados, pesos, treino ou inferência reais.
- Revisão independente aprovou sem achados; cumulativo avançado para `59f6205`.

**Status:** ready-for-human

### Implementação e evidências (2026-10-20)

- `ModelRegistry._validate_intact` recalcula o hash canônico do manifesto do bundle e o compara ao split imutável no registro; os hashes declarados de `train.jsonl` e `holdout.jsonl` passam a estar efetivamente vinculados ao registro, além de conferir os bytes das duas partições.
- `TrainingJobManager.submit_evaluation` valida adapter, metadados e bundle antes de criar o job. O worker recarrega a versão e repete a validação imediatamente antes da chamada de `evaluate_candidate`.
- Probe manual: `PYTHONPATH=src /tmp/finlabel-task4-venv/bin/python /tmp/finlabel_issue15_probe.py`.
  - Alteração sintética no adapter antes do enqueue: recusada; nenhum job criado; versão permaneceu `awaiting_evaluation`.
  - Alteração sintética da partição e do hash declarado depois do enqueue: worker persistiu `failed`; avaliador fake não foi chamado; nenhum evento `evaluated`; versão permaneceu `awaiting_evaluation`.
  - Candidato íntegro: avaliador fake chamado; relatório sintético registrado; versão passou para `awaiting_approval`.
- `python3.12 -m py_compile src/finlabel/training/jobs.py src/finlabel/training/registry.py`: passou.
- `git diff --check`: passou.
- Nenhum teste automatizado, peso, inferência ou treino real foi usado.
- Brief de implementação: `.superpowers/sdd/2026-10-20-supervised-training-lifecycle/integrity-fix-brief.md`.
