# 09: Integrar fluxo completo na CLI e documentar ciclo local

**Status:** ready-for-human

**Conclusão integrada (26/10/2026):** `codex/finlabel-autonomous-mvp`; CLI oferece o ciclo autônomo compartilhado com o painel, `run-status` e `model-status`. Validação registrada em `.scratch/biblioteca-rotulagem-financeira/completion/verification-report.md`. Testes completos da integração: 128 testes e 17 subtestes Python passaram.

**Plano:** `docs/superpowers/plans/2026-10-20-supervised-training-lifecycle.md`, Task 6.

## Objetivo

Deixar o ciclo de preparação, validação, split, treino explícito, avaliação, decisão de versão e rollback executável e compreensível pela CLI, mantendo validações nos serviços de domínio.

## Escopo

- Harmonizar `finlabel dataset prepare/check/split`, `finlabel train` e `finlabel model register/evaluate/activate/reject/rollback/versions/active`.
- `train` continua aceitando apenas bundle e explica como gerar o split se usuário fornecer o caminho antigo de dataset.
- Saída default informa caminhos, hashes, contagens, cobertura, avisos e estado atual sem imprimir valores de registros/prompts.
- README descreve comandos em sequência, estratégias de split, mínimos/avisos/consentimento, métricas, versões/rollback, política local e limites acadêmicos.
- Corrigir caminhos legados de CLI sem alterar lógica de domínio nem enfraquecer os gates.

## Critérios de aceite manual

- Executar help e comandos com fixtures sintéticas/fakes; validar a sequência completa e as mensagens de ordenação inválida.
- Treino sem consentimento, hashes inconsistentes, candidate incompatível e rollback inválido não mudam estado ativo.
- Saída e documentação não expõem valores de linhas/prompt por default.
- Sem teste automatizado, pesos, downloads ou treino real; registrar comandos não executados.

## Limites

Esta etapa integra a experiência de CLI e documentação; não comprova compatibilidade de execução de treino real com pesos ou hardware específicos.

## Comments

- Implementar em branch própria depois da revisão e integração da Task 5.
- Task 6 implementada em `codex/lifecycle-cli-docs` sobre `fe2751d`; ver `.superpowers/sdd/2026-10-20-supervised-training-lifecycle/task-6-implementer-report.md`.
- CLI passou por `--help`, `model --help`, `py_compile`, `git diff --check` e probe sintético de rejeição de caminho legado; a mensagem orientou `dataset check`/`dataset split`, status 2, ponteiro ativo ausente.
- Aceitação manual sintética executou `model register/evaluate/activate/reject/rollback` e registro por `train` com trainer/avaliador monkeypatchados. Ordem inválida, `--confirm` ausente, hash de adapter alterado e rollback para alvo adulterado retornaram status 2 e preservaram o ponteiro ativo; v3 permaneceu ativo após falha de rollback.
- Probe: `PYTHONPATH=src python3 /tmp/task6_manual_acceptance.py` (com Python bundled do workspace); cria projeto, bundle, task, adapters e relatório sintéticos sob diretório temporário, chama `finlabel.cli.main()`, e remove os fixtures ao sair. Ver comando expandido, observações e limites em `task-6-implementer-report.md`.
- Nenhum teste automatizado, peso/download, inferência real ou treino real; métricas fake não atestam comportamento do modelo. Hash do relatório e incompatibilidade de identidade do candidato não foram injetados separadamente.
