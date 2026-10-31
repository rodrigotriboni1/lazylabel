# 19: Calibrar e treinar modelos somente com rótulos confiáveis

**Status:** ready-for-human

**Conclusão integrada (26/10/2026):** branch `codex/finlabel-autonomous-mvp`; evidências de treino, calibração, holdout, gates de promoção e rollback estão cobertas pela suíte completa. O smoke do adapter histórico cobre somente inferência sintética e não constitui elegibilidade de promoção. Relatório: `.scratch/biblioteca-rotulagem-financeira/completion/verification-report.md`.

**Plano:** `docs/superpowers/plans/2026-10-21-finlabel-trusted-training.md`.

**Especificação:** `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md`.

## Objetivo

Fornecer proveniência confiável e partições de treino/calibração/holdout para o ciclo autônomo. Permitir que uma calibração válida alimente a política de rotulagem e que candidatos sejam promovidos automaticamente somente após avaliação e gates configurados para a tarefa.

## Escopo

- Registrar fontes locais somente leitura com coluna de referência, mapeamento de rótulos e proveniência explícita.
- Excluir a coluna de rótulos dos campos enviados à inferência.
- Rejeitar previsões do modelo como referência de verdade, além de IDs ausentes/duplicados, snapshots alterados e rótulos desconhecidos.
- Dividir referências confiáveis em treino, calibração e holdout congelado antes do fine-tuning.
- Ajustar e persistir calibrador compatível com o método de score do modelo e validar identidade da tarefa, política e modelo.
- Treinar candidato isolado, avaliar contra modelo ativo no mesmo holdout e promover/rejeitar por gates versionados; manter ativo anterior em falha e permitir rollback configurado.
- Adicionar comando one-shot que executa rotulagem e então avalia elegibilidade de treino; não criar daemon.

## Critérios de aceite

- Somente fontes de referência explicitamente configuradas e validadas entram no treino/calibração/holdout.
- Prompts nunca recebem a coluna de rótulo confiável.
- Dados de holdout não aparecem no treino e a origem da calibração é persistida.
- Ausência de cobertura/proveniência/gates bloqueia treino ou promoção com motivo explícito.
- Promoção só ocorre após gates congelados por tarefa; falha preserva modelo ativo.
- Resumos e manifestos não expõem linhas financeiras brutas por padrão.
- Não adicionar nem executar testes automatizados sem pedido explícito; registrar verificações manuais sintéticas.

## Limites

- Não carregar base real do usuário nem alegar performance financeira/causal.
- Não usar previsões autônomas como rótulos confiáveis ou verdade de avaliação.
- Não afirmar compatibilidade universal de calibração entre métodos ou modelos.
