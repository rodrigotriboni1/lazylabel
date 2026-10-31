# 11: Analytics, tendências, participação e monitoramento no painel

**Status:** ready-for-human

**Plano:** `docs/superpowers/plans/2026-10-20-finlabel-react-local-panel.md`, Task 2.

## Objetivo

Construir telas de análise e monitoramento que apresentem resultados determinísticos da API como gráficos acessíveis e explicáveis.

## Escopo

- Criar páginas overview/analysis/monitor React e integrar os endpoints existentes sem duplicar cálculos ou regras de negócio.
- Usar shadcn/ui e Recharts; suportar linha/tendência, comparação por grupo e composição/market share somente quando a API retorna dados compatíveis.
- Exibir definição, período/filtro, denominador, contagens excluídas e valores exatos em tabela ao lado/abaixo dos gráficos.
- Mostrar loading, sem dados, fonte indisponível, campo incompatível/ambíguo, pedido de esclarecimento, falha de plano/análise e findings estruturais determinísticos.
- Atualizar overview da shell para oferecer links e resumo seguro derivado de APIs.

## Critérios de aceite manual

- Conferir os valores exibidos nos gráficos e tabelas contra o JSON determinístico da API em dados sintéticos/local demo.
- Ambiguidade na definição de market share pede escolha explícita de numerador/denominador; falta de coluna temporal explica indisponibilidade de tendência.
- Falha da análise não produz gráfico ou resumo enganoso.
- Revisar monitoramento (severity/coluna) e viewports desktop/390 px no browser.
- Build produção passa; nenhum teste automatizado é adicionado/executado.

## Limites

Não inferir performance ou inadimplência a partir de snapshots sem histórico. Resumos de texto não podem inventar números; a fonte numérica é sempre o resultado determinístico.

Implementar em `codex/react-analytics` com base na integração `11c338e`; sem alterar branches laterais.

## Entrega React Task 2 — 2026-10-20

- Páginas de overview, análise e monitoramento adicionadas ao shell React; overview lista nomes e metadados de esquema sem exibir valores de registros.
- Endpoint metadata-only `GET /api/sources` adicionado para fornecer nomes, colunas, tipos mapeados/inferidos e contagens de ausência/preenchimento às telas.
- Análise usa `/api/plan` e `/api/analyze`, permite revisar campos, métrica, eixo temporal, séries e tipo de gráfico; participação exige seleção explícita de campo e confirmação do denominador total geral.
- Gráficos Recharts são derivados das linhas determinísticas da API. Valores originais, definição, período, filtros, denominador e contagens excluídas permanecem acessíveis na interface; esclarecimentos `422` são mostrados e o formulário manual permite escolha explícita. Falhas não deixam resultado antigo visível.
- Monitor apresenta severidade, código, coluna, esperado/observado e distingue esquema ausente de resultado sem divergências.
- Build: `cd frontend && npm run build` passou. Sem testes automatizados adicionados ou executados.
- Browser manual em fixture CSV sintética: `/analysis` renderizou soma por segmento; tabela e resposta `/api/analyze` coincidiram (`A=25.25`, `B=44.75`; 4 linhas válidas). `/monitor` mostrou os dois avisos estruturais esperados para baseline propositalmente divergente. Desktop foi inspecionado; viewport 390 px segue pendente para revisão humana.
- Limitações: proposta de plano em linguagem natural depende de backend local configurado; quando ausente, API informa isso e os campos podem ser montados manualmente. O gráfico usa apenas as linhas devolvidas naquela resposta; quando a API limita a página, a UI indica a quantidade exibida.
- Arquivos: `frontend/src/pages/{OverviewPage,AnalysisPage,MonitorPage}.tsx`, `frontend/src/lib/api.ts`, `frontend/src/App.tsx`, `frontend/package.json`, `frontend/package-lock.json`, `src/finlabel/web/app.py` e assets compilados `src/finlabel/web/static/app/assets/*`.

### Follow-up: revisão P1 — 2026-10-20

- O plano proposto agora é mantido como JSON completo editável; `/api/analyze` recebe o objeto parseado sem reconstruir métrica, filtros, dimensões, granularidade, eixo temporal ou denominador. Erros de JSON ficam visíveis antes de resultado.
- O serviço inclui `denominator_group_fields` em `formula_metadata`; a UI usa esse campo e o eixo temporal para descrever denominador por período (incluindo escopo dimensional) ou total geral para análise sem tempo.
- A identidade das séries combina todos os campos dimensionais que não são eixo X. Chaves internas são estáveis e rótulos compostos mostram cada campo e valor; os grupos do gráfico acompanham os grupos das linhas determinísticas.
- Verificação manual de proposta com backend local fixture: plano retornado com `dimensions=[region, product]`, filtro `region in [R1, R2]`, `time_axis.month/quarter`, `share_of_total`, `denominator_scope=[]` e `chart=line` permaneceu visível e foi ecoado integralmente no `result.json` após cálculo. 8 linhas válidas agregaram em 4 grupos trimestrais: `0.15 + 0.25 + 0.25 + 0.35 = 1.00`; metadados reportaram `denominator_group_fields=[month]` e a UI exibiu denominador por trimestre.
- Verificação manual em granularidade mensal com 2 dimensões: 8 linhas deram 8 grupos e quatro séries únicas (`region` + `product`); somas de cada mês foram `1.00` nos valores de participação. O gráfico exibiu as quatro linhas e a tabela preservou cada valor exato.
- Verificação manual sem eixo temporal: 8 linhas foram divididas em 4 grupos, valores de participação somaram `1.00`, e a UI indicou `total geral do conjunto filtrado`.
- `cd frontend && npm run build` passou após os ajustes. Nenhum teste automatizado foi adicionado ou executado.
