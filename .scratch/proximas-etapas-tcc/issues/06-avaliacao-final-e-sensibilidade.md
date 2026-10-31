# 06: Executar avaliação final e análise de sensibilidade

**What to build:** Uma avaliação final reproduzível que compara modelos e políticas de decisão, mede sensibilidade às hipóteses e separa qualidade preditiva de utilidade simulada.

**Blocked by:** 03 — Construir e avaliar o baseline logístico; 04 — Implementar a rede bayesiana inicial; 05 — Implementar a seleção de ações por utilidade esperada.

**Status:** ready-for-agent

- [ ] Congelar configurações, métricas, limiares e cenários antes de consultar o teste final.
- [ ] Avaliar os modelos no teste final uma vez, conforme o protocolo confirmado, guardando previsões por caso.
- [ ] Comparar métricas de previsão e calibração e, separadamente, utilidade simulada, custos definidos e distribuição de ações.
- [ ] Executar os cenários de sensibilidade a custos, benefícios e evidências incompletas previstos no protocolo.
- [ ] Estimar incerteza das diferenças principais com procedimento pareado previamente definido.
- [ ] Registrar limitações, incluindo ausência de resultados contrafactuais para as ações.
