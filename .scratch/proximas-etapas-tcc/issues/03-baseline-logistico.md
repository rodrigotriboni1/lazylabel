# 03: Construir e avaliar o baseline logístico

**What to build:** Uma referência reproduzível de risco probabilístico com regressão logística, avaliada no desenvolvimento pelo protocolo aprovado.

**Blocked by:** 02 — Fixar a base e preparar os dados.

**Status:** ready-for-agent

- [ ] Ajustar a regressão logística usando o pipeline de pré-processamento definido.
- [ ] Avaliar Brier score como critério principal, junto de ROC-AUC, log loss e diagrama de calibração; reportar average precision como complemento.
- [ ] Comparar probabilidades brutas e calibração sigmoidal sem usar o teste final para ajustar escolhas.
- [ ] Registrar sementes, parâmetros, previsões por caso e resultados por partição.
- [ ] Escrever uma interpretação dos resultados sem presumir superioridade de qualquer modelo.
