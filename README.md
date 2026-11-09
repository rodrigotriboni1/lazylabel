# LazyLabel — TCC de Rodrigo Mialichi Triboni

Biblioteca para analisar e rotular dados financeiros com modelos leves, com linha de comando e painel web. É também o objeto do TCC (Engenharia de Controle e Automação, UFU).

> **Tema em aprovação.** O tema submetido foi redes bayesianas para *next best action*; a direção atual é o LazyLabel. Falta o aval do orientador ([decisões 7 e 8](tcc/decisoes.md)).

## Comece aqui

1. **Onde estou e o que fazer agora:** [tcc/proximos-passos.md](tcc/proximos-passos.md)
2. **O que levar ao orientador:** [tcc/perguntas-orientador.md](tcc/perguntas-orientador.md)
3. **Como usar o LazyLabel:** [codigo/lazylabel/README.md](codigo/lazylabel/README.md) e [guia rápido](codigo/lazylabel/docs/quickstart.md)

## Onde está cada coisa

| Pasta | O que tem |
|---|---|
| `codigo/lazylabel/` | A biblioteca: backend Python, painel React, testes |
| `codigo/experimento/` | Script do baseline (regressão logística) |
| `tcc/` | Tudo do TCC: decisões, produto, protocolo, glossário, perguntas |
| `tcc/experimentos/` | Experimentos executados, com dados e resultados |
| `tcc/pesquisa/` | Notas de pesquisa (fontes de dados de crédito, painéis) |
| `tcc/entregas/` | Documentos já entregues (.docx) |
| `factory/` | Automação que transforma issues do GitHub em PRs |

## No dia a dia

```bash
bash factory/checks.sh                  # roda todos os testes; use antes de cada commit
cd codigo/lazylabel
.venv/bin/lazylabel quickstart ./demo --model-id <modelo>   # projeto de exemplo
.venv/bin/lazylabel serve                # abre o painel
```

- **Mudança no código:** abra uma issue no GitHub com o label `factory` e rode `/factory run` (ver `AGENTS.md`).
- **Decisão nova:** acrescente em [tcc/decisoes.md](tcc/decisoes.md).
- **Termo novo:** acrescente em [tcc/glossario.md](tcc/glossario.md).
