# PRD: FinLabel Local

- **Estado:** Rascunho derivado do código e dos documentos existentes (2026-10-31). Não é uma especificação aprovada pelo orientador.
- **Baseline do código:** branch `codex/finlabel-autonomous-mvp`, commit `257e90d` (`main` do repositório `codigo/finlabel` está desatualizada; ver `docs/roadmap-melhorias.md`).
- **Decisões:** `docs/adr/`. **Termos:** `GLOSSARY.md`.

## 1. Problema

Equipes que lidam com dados financeiros querem analisar e rotular tabelas com modelos de linguagem leves, mas não podem enviar registros a terceiros, precisam de resultados numéricos exatos e de rastreabilidade do que foi aplicado, rejeitado e treinado. Hoje isso exige montar scripts ad hoc a cada base/tarefa.

## 2. Usuário

**Principal:** desenvolvedor/analista que conecta uma fonte local, configura uma tarefa reutilizável e opera por biblioteca Python, CLI ou painel local.
**Secundário:** orientador/banca do TCC, que avalia reutilização e rastreabilidade.

## 3. Objetivos

| # | Objetivo | Como se observa |
|---|---|---|
| G1 | Processar dados financeiros **sem sair da máquina** | ADR-0001; testes de privacidade; nenhuma chamada externa de dados |
| G2 | **Reutilizar** o mesmo fluxo em outra tarefa/base mudando só configuração | Experimento de portabilidade (ainda não feito) |
| G3 | Análises numéricas exatas e reproduzíveis | ADR-0006 |
| G4 | Rotular sem revisão por linha, **abstendo-se** quando não há evidência | ADR-0004; taxa de cobertura e motivos de quarentena |
| G5 | Melhorar o modelo só com evidência e poder reverter | ADR-0005 |
| G6 | Rastrear cada execução | Manifests, hashes, eventos de registry |

## 4. Escopo atual (construído)

Marcado conforme os documentos do commit `257e90d`; **não reexecutei a verificação**.

- Projeto e fontes CSV/SQLite somente leitura (`project init`, `source add-*`, `source set-type`).
- Captura de esquema, baseline e monitoramento (`schema capture`, `monitor`).
- Análise por plano JSON ou planejador local; gráficos offline; heatmap categoria × período; painel com KPIs.
- Tarefas declarativas (`task add`); rotulagem autônoma (`label`, `label-run`) com política, calibração e quarentena.
- Supervisão confiável (`supervision add`); ciclo `run` / `run-status` / `model-status`; promoção, rejeição, rollback.
- CLI e painel React/FastAPI local (`serve`) com rotas `/`, `/analysis`, `/monitor`, `/labeling`, `/training`.
- Arquitetura hexagonal com testes de camadas e de compatibilidade.

## 5. Fora de escopo

- Compliance ou adequação regulatória automática; decisão de concessão de crédito; afirmações causais ou de lucro.
- Detecção de PII e validação do significado da variável-alvo.
- Revisão humana por registro no fluxo normal (legado `ReviewLog` apenas legível).
- Fontes além de CSV/SQLite; escrita na origem; LLM externo; serviço daemon de treino contínuo.
- Distribuir pesos de modelos ou presumir licença/compatibilidade.
- Alegar suporte a "qualquer base" sem adaptação.

## 6. Requisitos funcionais (resumo)

| ID | Requisito | Origem |
|---|---|---|
| RF1 | Abrir CSV/SQLite somente leitura e nunca alterar a origem | ADR-0002 |
| RF2 | Mapear tipos explicitamente; baseline só salvo após confirmação | README |
| RF3 | Executar análise a partir de plano revisável e gravar plano, resultados, `chart.html` e hashes | ADR-0006 |
| RF4 | Enviar ao modelo apenas `input_columns` da tarefa | ADR-0001/0004 |
| RF5 | Aplicar rótulo só com política válida, regras satisfeitas, origem atual e confiança calibrada; senão quarentena com motivo codificado | ADR-0004 |
| RF6 | Treinar só com rótulos confiáveis em partições congeladas | ADR-0005 |
| RF7 | Promover somente se todos os gates passam; registrar rejeição e rollback | ADR-0005 |
| RF8 | Expor estado de execução e modelo na CLI e no painel sem controles por registro | ADR-0004 |
| RF9 | Painel somente em loopback, com validação de Host/Origin/CSRF | ADR-0001 |

## 7. Requisitos não funcionais

- **Privacidade:** referências opacas e digests; sem linhas, prompts ou notas livres em logs/evidências.
- **Falha segura:** ausência de política, rótulos, artefatos ou gates → não aplica/não promove.
- **Portabilidade de dependências:** núcleo sem dependências obrigatórias (`dependencies = []`); extras `[web]` e `[models]`; Python ≥ 3.10 (`pyproject.toml` do baseline).
- **Manutenibilidade:** regras de camada executáveis por teste.
- **Acessibilidade/layout:** sem overflow horizontal de documento em 1440×900 e 390×844 (verificação divergente entre documentos; ver roadmap).

## 8. Métricas de sucesso (propostas, ainda não medidas)

| Métrica | Definição | Estado |
|---|---|---|
| Cobertura | Aplicados ÷ total (quarentena no denominador) | Medida apenas em sintético |
| Qualidade do rótulo | Acurácia / macro-F1 no holdout contra rótulo confiável | Sintético: 70,83% / 0,7056 (24 exemplos) |
| Erro de calibração | Calibration error no holdout | Sem dado real |
| Reuso | Passos de configuração vs. alterações no núcleo ao mudar de base | Não medido |
| Esforço de adaptação | Passos/tempo observáveis, com tarefa de referência | Não medido; sem base para alegar economia |

## 9. Riscos e perguntas abertas

1. **Pergunta de pesquisa e escopo do TCC não aprovados** (ADR-0007).
2. **Sem validação em dados reais:** só experimento sintético com Qwen2.5-0.5B-Instruct (revisão `7ae5576…`, Apple MPS); ciclo de treino verificado com stub.
3. Dados tabulares podem não justificar um LLM; falta baseline simples (modelo tabular, regras).
4. Calibrador depende de política/rótulos que o usuário precisa produzir.
5. Escolha de modelo (família Gemma citada na proposta; Qwen usado nos testes), licença e hardware em aberto.
6. Segunda base candidata (UCI Default of Credit Card Clients) sem aprovação; risco de vazamento temporal.

## 10. Entregáveis relacionados

`entregas/Relatorio_final_do_projeto_FinLabel.md`, `docs/architecture/*` e `docs/verified-training-cycle.md` (branch do código), `.scratch/biblioteca-rotulagem-financeira/` (issues 01–19).
