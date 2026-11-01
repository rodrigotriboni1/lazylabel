# 06: Treinar somente a partição de treino com gate explícito

**Status:** ready-for-human

**Plano:** `docs/superpowers/plans/2026-10-20-supervised-training-lifecycle.md`, Task 3.

## Objetivo

Permitir fine-tuning local e explícito somente depois de revalidar bundle, integridade, consentimento exploratório, autorização do projeto e hashes, usando exclusivamente o arquivo de treino.

## Escopo

- `train_adapter(bundle: TrainingBundle, config: TrainingConfig, *, gate_path: PathLike, exploratory_confirmed: bool = False) -> TrainingResult`.
- Revalidar os hashes do dataset e do bundle, o relatório de qualidade persistido e o gate existente de autorização modelo/licença/hardware/política de dados/protocolo de avaliação antes de importar/carregar bibliotecas de ML.
- Bloqueios são não sobrescrevíveis. Avisos de qualidade exigem confirmação explícita `--confirm-exploratory` no comando `finlabel train BUNDLE_DIR ...`.
- O SFTTrainer recebe somente `bundle.train_path`; holdout nunca é carregado ou passado ao trainer.
- `TrainingResult` registra `adapter_sha256` e `split_sha256`. Artefatos locais de candidato não sobrescrevem diretórios existentes, incluem hash do dataset/split, parâmetros e versões, e mantêm telemetria/reporting/push desligados.

## Critérios de aceite manual

- Bundle, dataset, qualidade, confirmação e gate inválidos são rejeitados antes de importar `torch`, `transformers`, `peft`, `trl` ou `datasets`.
- Aviso sem confirmação explícita rejeita; bloqueio não pode ser substituído por confirmação.
- Backend de treino falso permite inspecionar o único dataset recebido: `train_path`; nenhuma leitura/acesso ao holdout.
- Diretório existente é preservado; candidato contém hashes e metadados locais.
- Fixtures somente sintéticas e backend falso. Não baixar pesos, não fazer fine-tuning real. Não adicionar nem executar testes automatizados.

## Limites

Esta etapa implementa caminho seguro e backend, mas não executa treinamento real. Escolha/licença do modelo, hardware, protocolo e autorização permanecem requisitos para uso com dados/modelos reais.

## Comments

### Implementação em `codex/training-backend` (2026-10-20)

- Arquivos alterados: `codigo/finlabel/src/finlabel/training/backend.py` e `codigo/finlabel/src/finlabel/cli.py`.
- `train_adapter` exige `TrainingBundle`. O CLI recebe diretório de bundle e `--confirm-exploratory`. Antes de importar bibliotecas opcionais de ML, a validação confere caminhos fixos, hashes do split/partições/dataset, manifesto original, relatório de qualidade refeito contra a fonte atual e gate explícito. Bloqueios de qualidade não são sobrescrevíveis; avisos exigem confirmação.
- Treino copia somente `train.jsonl` para um snapshot temporário privado, verifica que ele é byte a byte idêntico à partição de treino validada e fornece essa cópia ao carregador; o dataset resultante vai ao `SFTTrainer`. A cópia fecha a janela de alteração do arquivo original durante o carregamento do modelo; a API não promete identidade de caminho com `bundle.train_path`. Um segundo hash após o carregamento bloqueia mudanças na cópia antes de construir o trainer. O holdout é lido apenas em bytes para verificar seu hash; suas linhas não entram no carregador nem no trainer. O carregamento de pesos exige cache local (`local_files_only=True`). O candidato recusa diretório existente, salva digest do adapter, hash do split/dataset, parâmetros e versões, com reporting/push desligados.
- Evidência manual: `git diff --check`; `python3 -m py_compile src/finlabel/training/backend.py src/finlabel/cli.py`; `PYTHONPATH=src python3 -m finlabel.cli train --help`; `PYTHONPATH=src python3 /tmp/finlabel-task3-probe.py`. A sondagem temporária criou apenas fixtures sintéticas, substituiu o relatório de qualidade por um retorno controlado e injetou módulos falsos de `datasets`, `peft`, `transformers` e `trl`. Bloqueou gate, hash de treino, hash do dataset, aviso sem confirmação e diretório existente. Capturou `data_files={'train': '<snapshot temporário>/train.jsonl'}`, `report_to='none'`, `push_to_hub=False`, arquivo local de metadata e ambos os digests. Quando o arquivo original mudou durante o carregamento do modelo, o trainer recebeu o snapshot original. Quando o carregador alterou o snapshot, a verificação após carga bloqueou o trainer; snapshot e candidato incompleto foram removidos.
- Limite da sondagem: o vínculo real entre qualidade e fonte foi verificado por inspeção do caminho de código (`inspect_training_dataset`), não pela fixture isolada. Esta etapa não afirma compatibilidade de uma execução real de TRL/PEFT.
- Comandos não executados: `pytest`, suites automatizadas, `pip install -e '.[train]'`, downloads de pesos, treinamento real, upload ou push.

- Revisão independente: aprovada após correção da corrida TOCTOU; o loader recebe um snapshot temporário local byte a byte verificado do `train.jsonl` (e nunca holdout). O snapshot é validado antes e depois da leitura e removido.
- Nenhum treino real, download ou teste automatizado foi executado. A verificação usou backend falso e fixtures sintéticas.
