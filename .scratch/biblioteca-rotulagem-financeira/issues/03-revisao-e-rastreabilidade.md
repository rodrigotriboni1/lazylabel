# 03: Registrar revisão humana e proveniência dos rótulos

**Status:** wontfix

**What to build:** Implementar uma API local append-only para registrar sugestão de rótulo, decisão humana (aceita/corrigida/rejeitada) e rótulo final, sem armazenar os dados da linha. Guardar identificador opaco, horário UTC e versão do esquema. Ver `.scratch/biblioteca-rotulagem-financeira/LOOP.md`.

## Bloqueadores de decisão

- Política de retenção e identificadores dos registros.
- O primeiro formato será JSONL, usando apenas a biblioteca padrão do Python.
- O identificador da linha é fornecido pelo chamador e deve ser opaco; não registrar conteúdo bruto.
- Não incluir notas livres no primeiro incremento para reduzir risco de gravar dados pessoais por engano.
- Retenção, acesso multiusuário e compliance normativo ficam fora do escopo deste ticket.

## Critérios de aceite

- Registrar decisão append-only em arquivo local JSONL.
- Tipos de decisão: aceita, corrigida ou rejeitada.
- Validar coerência: aceita mantém rótulo sugerido; corrigida exige rótulo final diferente; rejeitada não define rótulo final.
- Cada evento inclui versão do esquema, identificador opaco do registro, rótulo sugerido, decisão, rótulo final quando aplicável e timestamp UTC.
- Não serializar texto da linha, prompt ou outros campos da base.
- API de leitura retorna eventos estruturados e falha com mensagem clara em JSONL inválido.

## Comments

- 19/10/2026: Implementado `ReviewLog` em `codigo/finlabel/src/finlabel/review.py`, com validação das transições de revisão e leitura/escrita JSONL local. Não foram adicionadas nem executadas verificações automatizadas nesta etapa.
- 21/10/2026: O escopo aprovado remove a revisão humana obrigatória por registro. Este ticket não será continuado como fluxo operacional; eventos antigos permanecem como histórico e não viram rótulos confiáveis automaticamente. Ver `docs/superpowers/specs/2026-10-21-finlabel-autonomous-labeling-design.md` e o ticket 18.
