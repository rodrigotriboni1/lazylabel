# 05: Implementar a seleção de ações por utilidade esperada

**What to build:** Uma camada demonstrativa que calcula e ordena ações por utilidade esperada a partir das probabilidades de risco, deixando explícitas as hipóteses e limites da simulação.

**Blocked by:** 01 — Reconciliar progresso e fechar o protocolo; 03 — Construir e avaliar o baseline logístico.

**Status:** ready-for-agent

- [ ] Documentar ações admissíveis e a matriz de utilidade aprovada ou explicitamente hipotética.
- [ ] Implementar EU(a|x) = soma_y P(y|x) U(a,y), registrando a hipótese simplificadora sobre o estado y.
- [ ] Produzir ação recomendada, ranking, segunda melhor ação e diferença de utilidade.
- [ ] Definir desempate determinístico e conferir os cálculos com exemplos manuais.
- [ ] Comparar a política de limiar com a política de utilidade sob as mesmas hipóteses.
- [ ] Descrever resultados como simulação, sem inferir efeito causal ou lucro real.
