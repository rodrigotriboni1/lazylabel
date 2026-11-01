# Roadmap de melhorias

- **Data:** 2026-10-31
- **Base:** leitura do repositório do TCC e de `codigo/finlabel` (branch `codex/finlabel-autonomous-mvp`, commit `257e90d`) e dos documentos citados. Nenhum teste foi reexecutado ao escrever este documento; itens marcados **(não verificado)** vêm de documentos, não de checagem direta.
- Relacionados: [PRD](prd/finlabel.md), [ADRs](adr/), [GLOSSARY](../GLOSSARY.md).

Ordem sugerida: P0 desbloqueia tudo, P1 sustenta a tese, P2 qualidade, P3 higiene.

## P0 — Desbloqueios

### 1. Consolidar o código do FinLabel numa branch única
- **Situação:** `main` de `codigo/finlabel` tem só o commit `33aa970` (7 arquivos). O trabalho está em 37 branches `codex/*` (26 com worktree em `.worktrees/`). `codex/finlabel-autonomous-mvp` é a mais completa; outras 23 branches têm commits que ela não contém **(não verificado se são trabalho novo ou linhagens paralelas)**.
- **Ação:** para cada branch "à frente", decidir: já coberta, descartar ou integrar. Depois fazer `main` = estado verificado, por PR. Remover worktrees obsoletas.
- **Risco se ignorar:** perda de trabalho, e a banca/orientador veem uma `main` quase vazia.

### 2. Fechar o recorte do TCC com o orientador
- **Situação:** README, `Agenda_semanal_TCC.md` e `Protocolo_experimental.md` ainda descrevem redes bayesianas; o software já é outro. Ver [ADR-0007](adr/0007-pivo-do-tcc-para-biblioteca-finlabel.md).
- **Ação:** levar as 6 perguntas de `planejamento/Proposta_fluxo_reutilizavel.md` ao orientador; registrar a resposta; passar ADR-0007 para Aceita ou Rejeitada; atualizar README, protocolo e agenda.
- **Também em aberto:** prazo oficial de entrega/defesa; regras do curso sobre declarar uso de IA (`planejamento/Uso_de_IA_no_TCC.md`).

## P1 — Evidência para a tese

### 3. Rodar o ciclo com dados reais (ou públicos reais)
- **Situação:** só há smoke sintético (24 exemplos); o ciclo de treino foi exercitado com stub.
- **Ação:** com South German Credit corrigida, definir tarefa, rótulos confiáveis, `training-gate.json`, política de rotulagem e `promotion-policies`; executar `finlabel run`; guardar `run-status` e `model-status` como evidência.

### 4. Baseline simples
- **Situação:** a própria proposta alerta que dados tabulares podem não justificar um LLM.
- **Ação:** comparar com regressão logística/regras no mesmo holdout; sem isso não dá para afirmar valor do fine-tuning.

### 5. Experimento de portabilidade e esforço
- **Ação:** segunda base (candidata UCI Default of Credit Card Clients, sujeita a aprovação); registrar passos de configuração vs. mudanças no núcleo; checar vazamento temporal. Definir tarefa de referência antes de alegar redução de tempo.

### 6. Reconciliar Semanas 2 e 3
- **Situação:** Rodrigo relatou conclusão; `codigo/`, `dados/`, `resultados/`, `referencias/` e `texto/` não contêm artefatos (as pastas `dados/`, `referencias/`, `resultados/`, `texto/` existem **vazias**). Ticket: `.scratch/proximas-etapas-tcc/issues/01-reconciliar-progresso-e-protocolo.md`.
- **Ação:** localizar e registrar os artefatos, ou declarar que foram substituídos pelo pivô.

## P2 — Qualidade do software

### 7. Resolver divergência entre documentos de verificação
- `docs/completion-verification-2026-10-26.md` cita 128 testes Python e 10 de frontend e diz que QA em 1440×900/390×844 foi feito; `entregas/Relatorio_final_do_projeto_FinLabel.md` cita 407 e 51 e diz que essas dimensões **não** foram verificadas. Provavelmente são commits diferentes **(não verificado)**.
- **Ação:** reexecutar testes e QA no commit final, e gravar um único relatório com commit, comandos e saída.

### 8. Avisos conhecidos
- Cinco avisos de lint no React (dois de exports de UI, três `set-state-in-effect` em Training, Labeling e Analysis). **Resolvido (issue #4).**
- Bundle principal de 710 kB (limite de aviso: 500 kB) — considerar code-splitting por rota. Code-splitting por rota feito: bundle principal 275,58 kB. **Resolvido (issue #18).**

### 9. Reprodutibilidade dos testes
- `docs/architecture/clean-hexagonal.md` manda usar `/tmp/finlabel-clean-hexagonal-venv/bin/python`, caminho que some. Trocar por `python -m venv .venv && pip install -e '.[web,models]'` (ou o extra de teste que existir) e documentar o comando de teste.

### 10. Decisões de versão
- Definir política de depreciação das fachadas legadas (ADR-0003) e fixar a versão do pacote (`0.1.0`).
- Garantir calibrador e política de exemplo versionados para que o fluxo autônomo não fique com cobertura zero por padrão.

## P3 — Higiene do repositório do TCC

- Dois diretórios para referências: `references/` (2 notas de pesquisa) e `referencias/` (vazio, citado no README). Unificar.
- `README.md` lista `codigo/finlabel/` como "primeiro incremento" que só inspeciona CSV; atualizar para o escopo atual e apontar para `docs/prd/finlabel.md` e `docs/adr/`.
- `codigo/finlabel` é um repositório git aninhado e não é rastreado pelo repo do TCC. Decidir: submódulo (com `.gitmodules`), remoção do aninhamento ou manter fora do versionamento, e documentar.
- ~2 GB de experimento (`.venv`, `model-cache`) em `.scratch/biblioteca-rotulagem-financeira/experiments/` estão no `.gitignore`; garantir que não entrem em backup/entrega por engano.
