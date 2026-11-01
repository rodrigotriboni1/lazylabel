# 17: Ajustar apresentação visual da visão geral

**Status:** ready-for-human
**Label:** ready-for-human

**Origem:** QA visual manual do painel local, 2026-10-21.
**Base:** `codex/finlabel-lifecycle` (`59f6205`).
**Branch:** `codex/visual-qa-overview`, commit `c2e9a85`.

## Objetivo

Corrigir os problemas de hierarquia visual encontrados na visão geral em desktop e celular.

## Achados

- O título “Seu espaço de trabalho” e o texto introdutório aparecem duas vezes porque o shell e a página de visão geral renderizam cabeçalhos equivalentes.
- No desktop sem fontes configuradas, o cartão “Fontes de dados” estica para acompanhar toda a coluna de atalhos, deixando um grande espaço vazio.

## Critérios de aceite

- A visão geral mostra um único título principal e mantém o atalho “Nova análise”.
- O cartão de fontes conserva altura coerente com seu conteúdo vazio, sem distorcer os atalhos laterais.
- O resultado permanece legível em 1440×900 e 390×844, sem overflow horizontal.
- Conferir visualmente `/` e navegar dos atalhos para `/analysis` e `/monitor`.

## Implementação e revisão

- Removido o cabeçalho redundante do shell; a página de visão geral mantém o único título principal e o atalho funcional “Nova análise”.
- O grid agora alinha os cartões pelo topo, evitando que o cartão de fontes vazio se estique.
- Assets React empacotados atualizados com `npm run build`; build concluído. `git diff --check` passou.
- QA visual manual aprovada em desktop e celular; navegação e refresh revisados. Revisão independente aprovou sem achados bloqueantes.
- Evidências: `../../finlabel-visual-qa-2026-10-21/qa-report.md` e `../../finlabel-visual-qa-2026-10-21/evidence/`.
- Nenhum teste automatizado foi executado.

## Guardrails

- Não adicionar nem executar testes automatizados; esta correção será revisada visualmente.
- Não usar dados reais, modelo, treino ou inferência.
- Manter a branch de integração sem alterações diretas; implementar em branch separada e registrar revisão.
