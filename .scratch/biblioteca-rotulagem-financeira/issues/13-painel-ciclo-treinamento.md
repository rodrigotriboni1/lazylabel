# 13: Painel do ciclo supervisionado de treinamento

**Status:** ready-for-human

**Escopo atualizado (26/10/2026):** o diagrama mantém sete etapas — verificar dados, dividir, treinar, avaliar, decidir, promover/rejeitar, monitorar/reverter — e o painel mostra estado e métricas do ciclo autônomo, sem ações manuais de promoção. Integração em `codex/finlabel-autonomous-mvp`; capturas e verificações em `.scratch/biblioteca-rotulagem-financeira/completion/verification-report.md`.

**Plano:** `docs/superpowers/plans/2026-10-20-finlabel-react-local-panel.md`, Task 4.
**Branch:** `codex/react-training`, base `c080413` (`codex/finlabel-lifecycle`).

## Objetivo

Permitir acompanhar e operar o ciclo supervisionado de treinamento pela interface React local, usando os mesmos serviços/estado da CLI e exibindo um diagrama legível do fluxo.

## Escopo

- Quality gate e preview/configuração do split do dataset.
- Início explícito do treino com confirmação dos avisos e estado/status de job.
- Avaliação do candidato no holdout; exibir métricas por rótulo, suporte, erros/indefinições e warnings.
- Histórico/estado de versões; ativar, rejeitar e rollback com confirmação explícita.
- API web compatível com os contratos Python atuais, revalidando estado no servidor. Operações estritamente dentro do projeto/workspace local.
- Diagrama no próprio ciclo de treinamento: preparar/verificar dados → dividir → treinar somente partição de treino → avaliar holdout → decisão → ativar/rejeitar → rollback. Realçar estágio atual e oferecer sequência textual acessível.

## Critérios de aceite manual

- Executar com projeto sintético e backend de treino/avaliação falso: check → split → fake train → fake eval → activate/reject → rollback.
- Confirmar que blocker/ausência de consentimento impede trabalho, erros de job não aparecem como sucesso e transições inválidas não alteram o active pointer.
- Verificar que o CLI observa as mesmas versões/estado que o painel após ações.
- Inspecionar desktop e viewport estreita quando o host permitir; build frontend e verificar `py_compile`/`git diff --check`.
- Nenhum teste automatizado, download de pesos, inferência ou treino real.
- Revisão independente solicitou duas correções antes da aprovação: executar avaliação em job assíncrono (não bloquear a API local) e preservar histórico/diagnóstico quando a versão ativa estiver corrompida ou ausente.
- Re-revisão confirmou essas correções e apontou um último P2: falha na importação lazy do worker pode deixar o job de avaliação em `running`; registrar também erros de setup como `failed`.

## Guardrails

- Fonte permanece somente leitura. Dados e exemplos rotulados não saem do host.
- Model downloads/weights e treino real estão fora desta tarefa.
- Preservar os controles Host/Origin/CSRF e limites dos endpoints já existentes.
- Usar fixture sintética e stubs em memória/temporários para aceitação manual.

## Implementação

Branch/worktree: `codex/react-training`, `codigo/finlabel/.worktrees/react-training`.

### Entrega e verificação (2026-10-20)

- Tela `/training` com quality gate, configuração e criação de split, consentimentos explícitos, acompanhamento de job, avaliação base/candidato por rótulo, avisos, histórico, ativação, rejeição e rollback.
- Diagrama visível em sete etapas, com estágio atual destacado e sequência textual acessível; o fluxo preserva a fronteira entre `train` e `holdout`.
- API web alinhada a `TrainingBundle`, gate, avaliação e `ModelRegistry`; job concluído registra candidato inativo. A API revalida contratos e mantém o limite de resposta, CSRF e operações sob o workspace.
- `npm ci` (frontend): concluído pelo lockfile; sem vulnerabilidades reportadas.
- `npm run build` (frontend): passou em 2026-10-20. O Vite reportou apenas o aviso de bundle JS > 500 kB.
- `python3.12 -m py_compile src/finlabel/web/app.py src/finlabel/training/jobs.py`: passou.
- `git diff --check`: passou.
- Smoke API manual em projeto temporário sintético: `GET /training` = 200; `GET /api/train/overview` = 200; POST sem token CSRF = 403; caminho de dataset inválido = 400.
- Aceitação manual sintética por `PYTHONPATH=src /tmp/finlabel-task4-venv/bin/python - <<'PY'` com fixture temporária e stubs locais: quality check pronto; split 12 treino / 4 holdout; dois jobs falsos concluídos e registrados; duas avaliações sintéticas gravadas; segunda versão ativada e rollback para a primeira refletido no ponteiro ativo.
- Nenhum teste automatizado foi adicionado ou executado. Nenhum peso foi baixado; os adapters e relatórios eram fixtures falsos, sem inferência ou treino real.
- Inspeção visual no navegador e viewport estreito não foi feita nesta etapa; o build e os probes HTTP não substituem a QA visual.

### Revisão independente: correções e evidência sintética (2026-10-20)

- A avaliação no holdout agora é um job local persistido, executado em worker separado. `POST /api/train/evaluate` exige confirmação explícita e retorna `202`; `GET /api/train/evaluations/{job_id}` acompanha o job. Treino e avaliação compartilham a proteção de uma operação de modelo ativa por vez. Jobs `queued`/`running` encontrados após reinício são persistidos como `failed` e não são retomados.
- A tela acompanha o job, exibe falhas, só apresenta conclusão após o relatório estar no registro, e mostra diagnósticos do ponteiro/artefatos. Versões com integridade inválida não oferecem ações. Quando o estado ativo é inválido, uma versão anterior verificada pode ser recuperada com confirmação; o servidor também exige um diagnóstico real antes de permitir recuperação.
- `registry.inspect_history()` lê as versões individualmente, preservando as partes íntegras do histórico e associando erros a cada versão. Os endpoints `/api/train/overview` e `/api/train/versions` deixam de depender de `registry.active()` bem-sucedido para listar histórico.
- Probe manual sintético temporário (`/tmp/finlabel_review_probe.py`, ambiente `/tmp/finlabel-task4-venv`): `GET /api/train/overview` e `GET /api/train/versions` retornaram 200 com duas entradas e diagnóstico após corromper o adapter apontado como ativo; recuperação selecionou a versão anterior íntegra e manteve o registro inválido visível.
- O mesmo probe confirmou avaliação persistida em `queued`, job observado em `running`, conclusão `succeeded` somente depois do relatório sintético estar registrado, e estado `failed` em erro simulado mantendo o candidato em `awaiting_evaluation`. Um job `running` remanescente após reiniciar o manager foi marcado `failed` sem retomar execução.
- Verificação: `npm run build` passou (Vite reportou aviso de bundle JavaScript acima de 500 kB); `/tmp/finlabel-task4-venv/bin/python -m py_compile src/finlabel/web/app.py src/finlabel/training/jobs.py src/finlabel/training/registry.py` passou; `git diff --check` passou.
- Não foram executados testes automatizados nem inferência/treino real. A sondagem usou artifacts, pesos, candidatos e relatórios sintéticos; a inspeção visual no navegador continua pendente.
- Follow-up de revisão: imports lazy, transição inicial para `running` e setup agora ocorrem dentro do bloco protegido do worker; exceções comuns nessa fase são persistidas como `failed`. Probe temporário injetou `ImportError` sintético em `finlabel.training.evaluation` e confirmou status `failed` persistido, sem conclusão falsa. `/tmp/finlabel-task4-venv/bin/python -m py_compile src/finlabel/training/jobs.py` e `git diff --check` passaram; nenhum teste automatizado foi executado.
- Revisão independente final aprovou o follow-up `d639e2b`; branch `codex/react-training` integrada por fast-forward no cumulativo `codex/finlabel-lifecycle`, agora em `d639e2b`.
