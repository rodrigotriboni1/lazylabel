# 18: Aplicar rótulos automaticamente e colocar casos incertos em quarentena

**Status:** ready-for-human

**Conclusão integrada (26/10/2026):** `codex/finlabel-autonomous-mvp`; CLI e painel compartilham o ciclo, com quarentena na ausência de política/calibração e sem revisão humana por registro. Testes e limites estão no relatório `.scratch/biblioteca-rotulagem-financeira/completion/verification-report.md`.

**Plano:** `docs/superpowers/plans/2026-10-21-finlabel-autonomous-labeling.md`.

**Especificação:** `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md`.

## Objetivo

Substituir a fila de revisão humana por registro por um serviço local de rotulagem autônoma. Aplicar automaticamente somente resultados válidos segundo uma política de tarefa calibrada; registrar casos incertos, inválidos, conflitantes ou stale em quarentena, sem bloquear o processamento dos demais registros.

## Escopo

- Política declarativa específica da tarefa com rótulos, regras, referência de calibração e limites explícitos.
- Contrato normalizado de previsão; justificativa textual não conta como confiança.
- Artefatos locais imutáveis com estado `applied` ou `quarantined`, proveniência e códigos de motivo.
- CSV e SQLite permanecem somente leitura; não registrar valores de linha ou prompts por padrão.
- `finlabel label` executa e reporta o fluxo sem depender de `finlabel review`.
- Artefatos de revisão legados permanecem históricos e não são supervisão confiável por padrão.

## Critérios de aceite

- Política ausente, confiança não calibrada, saída inválida, label desconhecido, conflito ou fonte stale nunca resultam em rótulo aplicado.
- Cada registro recebe no máximo um estado terminal por execução; retries não duplicam eventos.
- Uma falha recuperável em um registro não impede o restante do lote.
- Resumo CLI/API e JSONL não expõem valores selecionados nem prompt.
- Execução sintética sem calibrador coloca previsões estruturalmente válidas em quarentena por `uncalibrated`; a fonte original não muda. Aplicação automática só será demonstrada depois que o ticket 19 fornecer evidência de calibração validada.

## Limites

- A implementação deste ticket não cria supervisão confiável, não treina nem promove modelos; isso pertence ao ticket 19.
- Não usar confidence autorreportada pelo LLM nem inventar threshold universal.
- Não acrescentar ou executar testes automatizados sem pedido explícito; registrar evidência de inspeção manual sintética.


## Comments

### 2026-10-21 — Implementação revisável pronta

Concluídos os commits da branch `codex/finlabel-autonomous-labeling`: política com regras determinísticas, contrato de previsão com score bruto explicitamente não calibrado, outcomes atômicos aplicados/quarentena com digest e proveniência, e CLI `label` / `label-run`. Branch de integração `codex/finlabel-autonomous-mvp` recebeu a etapa revisada até `a3c28f0`.

Revisão independente apontou e levou à correção de: score com tokenização conjunta, avaliação real das regras, semântica de staleness por registro, aviso de política ausente em fonte vazia e clareza do digest do lote. Limite restante documentado: CSV/SQLite não são bloqueados entre a releitura final e a publicação; consumidores devem comparar `input_digest` antes de usar um resultado com a linha atual.

Inspeção sintética manual da CLI: três linhas terminaram em quarentena (`invalid_output`, `rule_conflict`, `uncalibrated`); o CSV permaneceu igual; saída e artefatos não expuseram valores nem justificativa sentinela. Nenhum teste automatizado foi executado. O fluxo de aplicação será demonstrado no ticket de calibração quando houver calibrador validado.
