# ADR-0001: Operação local-first, sem saída de dados

- **Status:** Aceita
- **Data:** 2026-10-31 (registra decisão vigente desde 2026-10-19)
- **Escopo:** FinLabel (`codigo/finlabel`)

## Contexto

Dados financeiros são sensíveis. O TCC propõe uma biblioteca que um desenvolvedor possa usar sem enviar registros a terceiros. A proposta inicial já exigia que "os dados de treino permaneçam na máquina" (`planejamento/Proposta_fluxo_reutilizavel.md`).

## Decisão

Toda execução ocorre na máquina do usuário:

- Modelos rodam localmente (Transformers; PEFT/LoRA/TRL para treino), como dependências **opcionais** (`.[models]`). Pesos só são baixados quando uma execução local explicitamente selecionada precisa deles; telemetria do trainer é desativada e adapters não são publicados.
- O planejador de análise recebe a pergunta e **nomes/tipos de colunas, nunca linhas**. O modelo de rotulagem recebe somente `input_columns` da tarefa.
- O painel faz bind apenas em loopback e valida `Host`, `Origin` e CSRF, com limite de requisições e de tamanho de resposta (100 linhas, 2.000 pontos, 1 MiB).
- Gráficos são HTML autocontido (sem CDN) e exibidos com CSP sandbox.
- Logs e evidências usam referências opacas e digests; não gravam linhas, prompts nem notas livres.

## Consequências

- (+) Privacidade verificável por inspeção do código e testes de privacidade ponta a ponta.
- (+) Sem dependência de API externa.
- (−) Qualidade limitada a modelos leves que cabem no hardware do usuário.
- (−) Download de pesos exige rede na primeira execução; licença e compatibilidade do modelo são responsabilidade do usuário.
- (−) A "fronteira de confiança" é o workspace de um único usuário: hashes detectam edição acidental, não um dono malicioso do workspace.

## Evidência

`README.md` e `docs/verified-training-cycle.md` (branch `codex/finlabel-autonomous-mvp`); `entregas/Relatorio_final_do_projeto_FinLabel.md` §4 (requisições chunked e hosts não confiáveis rejeitados, SHA-256 do CSV inalterado, em dados sintéticos).
