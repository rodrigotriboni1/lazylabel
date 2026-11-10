# LazyLabel — TCC de Rodrigo Mialichi Triboni

Biblioteca para analisar e rotular dados financeiros, com linha de comando e painel web. Roda com modelos locais ou na nuvem pelo Vercel AI Gateway. É também o objeto do TCC (Engenharia de Controle e Automação, UFU).

> **Tema em aprovação.** O tema submetido foi redes bayesianas para *next best action*; a direção atual é o LazyLabel. Falta o aval do orientador para o tema ([decisão 7](tcc/decisoes.md)); o uso da nuvem já foi autorizado pelo coordenador ([decisão 8](tcc/decisoes.md)).

## Comece aqui

1. **Onde estou e o que fazer agora:** [tcc/proximos-passos.md](tcc/proximos-passos.md)
2. **O que levar ao orientador:** [tcc/perguntas-orientador.md](tcc/perguntas-orientador.md)
3. **Como usar o LazyLabel:** [codigo/lazylabel/README.md](codigo/lazylabel/README.md) e [guia rápido](codigo/lazylabel/docs/quickstart.md)

## Estado atual (09/11/2026)

**Funciona**
- CLI `lazylabel`: fontes CSV/SQLite só leitura, monitoramento de esquema, análises exatas, rotulagem com quarentena, treino com gates, promoção e rollback.
- Painel web com 6 telas feitas em JSON ([json-render](https://github.com/vercel-labs/json-render) + shadcn), modo claro e escuro: Visão geral, **Perguntar**, Análises, Monitoramento, Rotulagem e Treinamento.
- **Perguntar:** você faz uma pergunta, revisa o plano, o LazyLabel calcula os números de forma exata e a IA só monta a tela com eles. Telas com números que não vieram do cálculo são descartadas.
- Modelos na nuvem: qualquer id `gateway:<provedor>/<modelo>` usa o Vercel AI Gateway.
- Testes: 436 Python e 57 do painel passando (`bash factory/checks.sh`).

**Falta**
- Testar a nuvem com uma chave real (`AI_GATEWAY_API_KEY`).
- Rotulagem pela nuvem: hoje ela usa só modelo local, porque precisa da probabilidade de cada rótulo para calibrar a confiança.
- Evidência para a tese: experimento com dados reais, baseline e segunda base ([próximos passos](tcc/proximos-passos.md)).

## Onde está cada coisa

| Pasta | O que tem |
|---|---|
| `codigo/lazylabel/` | A biblioteca: backend Python, painel (`frontend/`), testes |
| `codigo/lazylabel/frontend/src/specs/` | As telas do painel, uma por arquivo JSON |
| `codigo/experimento/` | Script do baseline (regressão logística) |
| `tcc/` | Tudo do TCC: decisões, produto, protocolo, glossário, perguntas |
| `tcc/experimentos/` | Experimentos executados, com dados e resultados |
| `tcc/pesquisa/` | Notas de pesquisa (fontes de dados de crédito, painéis) |
| `tcc/entregas/` | Documentos já entregues (.docx) |
| `factory/` | Automação que transforma issues do GitHub em PRs |

## No dia a dia

```bash
bash factory/checks.sh                                        # roda todos os testes; use antes de cada commit
cd codigo/lazylabel
.venv/bin/lazylabel quickstart ./demo --model-id <modelo>      # projeto de exemplo com dados sintéticos
.venv/bin/lazylabel serve --project ./demo                     # painel em http://127.0.0.1:8765
```

Para usar a nuvem (análises e Perguntar):

```bash
export AI_GATEWAY_API_KEY=...                                  # criada no painel da Vercel, ou: vercel env pull
export LAZYLABEL_UI_MODEL=gateway:anthropic/claude-haiku-4.5   # opcional; modelo que monta as telas
```

- **Mudar uma tela:** edite o JSON dela em `frontend/src/specs/`.
- **Mudança no código:** abra uma issue no GitHub com o label `factory` e rode `/factory run` (ver `AGENTS.md`).
- **Decisão nova:** acrescente em [tcc/decisoes.md](tcc/decisoes.md).
- **Termo novo:** acrescente em [tcc/glossario.md](tcc/glossario.md).
- **Projeto antigo em `.finlabel/`:** continua funcionando; projetos novos usam `.lazylabel/`.
