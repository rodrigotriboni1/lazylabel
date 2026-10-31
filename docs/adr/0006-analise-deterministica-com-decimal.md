# ADR-0006: Análises determinísticas com Decimal; modelo só planeja

- **Status:** Aceita
- **Data:** 2026-10-31 (decisão de 2026-10-19)
- **Escopo:** FinLabel

## Contexto

Números financeiros precisam ser exatos e reproduzíveis. Um LLM pode ajudar a transformar uma pergunta em um plano de análise, mas não deve calcular nem ver os dados.

## Decisão

- Um **plano** JSON revisável define a análise. Pode ser escrito à mão (`--plan`, sem modelo) ou proposto por um modelo local (`--model-id`).
- O planejador recebe pergunta e nomes/tipos de colunas, **nunca linhas**.
- O motor calcula em `Decimal` (contagem, soma, média, distintos, participação). Share exige medida, dimensão e escopo de denominador explícitos.
- Cada execução grava `.finlabel/analyses/<run_id>/` com plano, resultados, `chart.html` sem CDN e hashes. A tabela é a referência numérica; o gráfico é derivado.
- O painel limita exibição (100 linhas, 2.000 pontos, 1 MiB por JSON).

## Consequências

- (+) Mesma entrada → mesmos números; auditável.
- (+) Funciona sem modelo.
- (−) Só operações suportadas pelo motor; perguntas fora delas exigem estender o domínio.
- (−) Tipos precisam de mapeamento explícito do usuário.

## Evidência

README (Análises e gráficos); `src/finlabel/domain/analysis/` na branch `codex/finlabel-autonomous-mvp`; `docs/superpowers/specs/2026-10-25-finlabel-analytics-dashboard-design.md`.
