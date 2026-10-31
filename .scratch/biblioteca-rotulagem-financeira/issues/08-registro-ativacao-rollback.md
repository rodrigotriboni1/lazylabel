# 08: Registro local de modelos, ativação explícita e rollback

**Status:** ready-for-human

**Plano:** `docs/superpowers/plans/2026-10-20-supervised-training-lifecycle.md`, Task 5.

## Objetivo

Manter adapters candidatos locais e imutáveis, registrar avaliações e decisões append-only, e permitir ativação e rollback explícitos sem perder o modelo ativo em caso de falha.

## Escopo

- Criar `src/finlabel/training/registry.py` com `ModelVersion` e `ModelRegistry(workspace_dir)`.
- Diretórios em `.finlabel/models/versions/<version_id>/manifest.json`, eventos append-only em `events.jsonl` e ponteiro ativo em `.finlabel/models/active.json`.
- Estados derivados dos eventos: `awaiting_evaluation`, `awaiting_approval`, `rejected`, `active`, `superseded`.
- Operações: registrar candidato completo, registrar avaliação vinculada aos hashes adapter/dataset/split, rejeitar com motivo, listar/consultar versões, ativar candidato avaliado e rollback explícito.
- Ativação valida os artefatos, exige confirmação explícita, escreve ponteiro temporário e substitui atomicamente o ponteiro ativo.
- CLI `finlabel model versions|active|evaluate|activate|reject|rollback ...`; nesta etapa, implementar os comandos da registry e conectar `evaluate` ao serviço da Task 4. Sem duplicar as transições da camada de domínio.

## Critérios de aceite manual

- Registrar fake candidate íntegro e observar `awaiting_evaluation`; report de avaliação com hashes incompatíveis não transiciona estado.
- Avaliação compatível transiciona para `awaiting_approval`; rejeição exige motivo e confirmação e jamais altera o ativo.
- Ativação sem confirmação falha; ativação confirmada troca o ponteiro. Falha de escrita/validação mantém ponteiro anterior.
- Ativar uma segunda versão marca a anterior como `superseded`; rollback para versão íntegra registra evento e reativa sem alterar manifests imutáveis.
- Candidato corrompido, ausente, links/path externos ou saída inválida são bloqueados; eventos e artefatos permanecem locais.
- Usar somente fixtures/adapters falsos e comandos manuais; não executar testes automatizados, não baixar pesos e não treinar modelo real.

## Limites

Essa etapa não ativa automaticamente após avaliação e não afirma qualidade, segurança regulatória ou compatibilidade de treino real. Toda transição deve preservar histórico local verificável.

## Comments

- Implementação designada ao branch `codex/training-registry`, criado sobre o integration revisado `b544031`. Evidência e comandos não executados serão anexados após revisão.

## Implementação e evidência manual (2026-10-20)

- Branch: `codex/training-registry`; commit registrado no relatório do implementador.
- Arquivos: `src/finlabel/training/registry.py` e `src/finlabel/cli.py`.
- Entregue: registro imutável com eventos append-only, avaliação condicionada aos hashes do adapter/dataset/split, rejeição, listagem, consulta do ativo, ativação explícita e rollback. A CLI oferece `model register|versions|active|evaluate|activate|reject|rollback`; mutações decisórias exigem `--confirm`, rejeição também exige `--reason`.
- Aceite manual sintético, workspace temporário: candidato íntegro registrado como `awaiting_evaluation`; hash de avaliação incompatível recusado sem transição; relatório compatível levou a `awaiting_approval`; ativação; segunda ativação marcou a primeira `superseded`; rollback reativou a primeira; rejeição não moveu o ativo; adapter corrompido bloqueou rollback e preservou o ativo; path externo e reutilização de ID foram recusados. Estado final observado: `one=active`, `two=superseded`, `reject=rejected`.
- Verificações permitidas executadas: `python3 -m py_compile src/finlabel/training/registry.py src/finlabel/cli.py`; `PYTHONPATH=src python3 -m finlabel.cli --help`; `PYTHONPATH=src python3 -m finlabel.cli model --help`; `git diff --check`.
- Não executados conforme LOOP: testes automatizados (`pytest` ou suíte equivalente), pesos reais e treinamento real. Nenhum peso foi baixado.
- Limite: avaliação CLI completa com modelos reais não foi executada; o contrato de avaliação foi exercitado com relatório sintético.

### Revisão do implementador (2026-10-20)

- Corrigidos os comandos `model versions` e `model active` para aceitar `--project`.
- Avaliação agora é copiada para um snapshot da versão, com SHA-256 gravado no evento append-only. Integridade verifica esse hash antes de tratar a versão ativa, ativar ou fazer rollback; edição do relatório original não altera a avaliação registrada.
- Falha depois de publicar o evento de ativação gera `activation_failed`: uma nova ativação retorna a `awaiting_approval`; falha de rollback retorna a `superseded`. A falha sintética após `os.replace` restaurou o ponteiro anterior e a ativação foi repetida com sucesso.
- Contenção rejeita componentes symlink em entradas e nos caminhos internos de registry, adapter, bundle, partições e relatórios. Aberturas finais usam `O_NOFOLLOW` onde disponível; criação do snapshot é exclusiva e o ponteiro segue sendo substituído atomicamente.
- Probes manuais: flags de projeto em `versions/active`; relatório fonte editado sem afetar snapshot; snapshot de métricas alterado bloqueado; falha de ponteiro depois do replace preserva o ativo anterior e mantém candidato retryable; bloqueio de symlink em componente, conteúdo de adapter, relatório, partição e diretório registry.
- Verificação permitida: `python3 -m py_compile src/finlabel/training/registry.py src/finlabel/cli.py`; `PYTHONPATH=src python3 -m finlabel.cli model versions --help`; `PYTHONPATH=src python3 -m finlabel.cli model active --help`; `git diff --check`.
- Testes automatizados, pesos reais e treinamento real continuam não executados.
- Commit das correções de revisão: `fe2751dd6219cbae52686f8d5167b3a10015beaa` (`Harden model registry integrity and retries`). O relatório do implementador registra a fronteira residual de TOCTOU para substituição concorrente de diretório ancestral; o workspace local é considerado privado ao usuário.
- Revisão independente da rodada de correções: aprovada, quatro achados resolvidos, sem findings bloqueadores. O revisor confirmou as correções da CLI, hash/snapshot do relatório, ativação retryable após falha e recusa de caminhos symlink. Limite de TOCTOU por substituição hostil concorrente de ancestral permanece documentado.
