# ADR-0007: Pivô do TCC de redes bayesianas para a biblioteca FinLabel

- **Status:** **Proposta** — depende de aprovação formal do orientador
- **Data:** 2026-10-31
- **Escopo:** TCC (pergunta, objetivo e método)

## Contexto

- O tema submetido: redes bayesianas e utilidade esperada para *next best action* (`README.md`, `planejamento/Protocolo_experimental.md`, base South German Credit, regressão logística vs. redes bayesianas).
- Em 2026-10-19 Rodrigo relatou que o orientador gostou da visão de uma biblioteca open source reutilizável de rotulagem assistida e indicou **reutilização** como foco (`planejamento/Proposta_fluxo_reutilizavel.md`).
- Desde então o software evoluiu muito (ADR-0003 a 0006), mas a documentação acadêmica não foi reconciliada: o README ainda apresenta o tema antigo, e a própria proposta diz que não substitui o protocolo até aprovação.

## Decisão proposta

Adotar como contribuição central do TCC a biblioteca FinLabel, avaliada por **reutilização**:

> Até que ponto um fluxo configurável de rotulagem financeira, implementado como biblioteca local, pode ser reaplicado a diferentes tarefas e bases sem alterar seu núcleo, mantendo rastreabilidade e controles de qualidade?

Evidências de reuso: reconfigurar a mesma tarefa sem reescrever o núcleo e aplicar a uma segunda base (candidata: UCI Default of Credit Card Clients), registrando adaptações separadas de reescritas. A comparação regressão logística × rede bayesiana só permanece se servir a essa avaliação.

## Consequências

- (+) Alinha o TCC ao que foi construído e permite medir o que foi prometido.
- (−) Reescrever protocolo, cronograma e texto; riscos de prazo.
- (−) Afirmações como "reduz tempo de desenvolvimento" ou "funciona em qualquer base" **não são sustentadas** sem protocolo de medição.
- (−) Conflita com a proposta anterior de revisão humana como eixo (ver ADR-0004).

## Pendências para fechar

1. Orientador aprovar pergunta, escopo e uso de IA (README registra autorização verbal; falta registro formal).
2. Escolher baseline e métricas; decidir se fine-tuning é exigido ou comparado com inferência pré-treinada.
3. Aprovar a segunda base e checar vazamento temporal.
4. Atualizar `README.md`, `Protocolo_experimental.md` e `Agenda_semanal_TCC.md`.
