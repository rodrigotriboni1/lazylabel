# ADR-0002: Fontes CSV e SQLite somente leitura

- **Status:** Aceita
- **Data:** 2026-10-31
- **Escopo:** FinLabel

## Contexto

A biblioteca precisa ler dados da pessoa usuária sem arriscar alterá-los. O MVP inicial apenas perfilava CSV; o escopo cresceu para análise, monitoramento e rotulagem.

## Decisão

- Conectores `CsvSource` e `SqliteSource` (`adapters/outbound/sources/`) abrem a origem **somente leitura**. O contrato `DataSource` descreve IDs, leitura, streaming e seleção de colunas.
- Resultados, rótulos aplicados, quarentena e proveniência são gravados em artefatos **separados** em `.finlabel/`.
- Tipos são inferências; datas e números exigem mapeamento explícito (`source set-type`). Nenhum limite de qualidade é presumido: o baseline é confirmado pelo usuário.
- Novas fontes entram por: porta em `application/ports/sources.py` → adapter → seleção em `bootstrap/application.py`, com teste de contrato provando que a origem não muda.

## Consequências

- (+) A origem nunca é alvo de efeitos colaterais; o hash do CSV permanece igual (verificado em dados sintéticos).
- (+) Fácil estender para outras fontes sem tocar domínio ou casos de uso.
- (−) Sem escrita de volta: o usuário precisa consumir os artefatos de saída.
- (−) Apenas duas fontes hoje; não há PII detection nem validação do significado da coluna-alvo.

## Evidência

README (seção Projeto e fontes), `docs/architecture/clean-hexagonal.md` ("Adicionar uma fonte de dados"), relatório final §4.
