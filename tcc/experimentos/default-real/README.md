# Experimento E2 — Default of Credit Card Clients (reutilização)

- **Fonte:** UCI, dataset 350 (https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients), obtido em 10/11/2026.
- **Arquivos brutos:**
  - `default_of_credit_card_clients.zip`, SHA-256 `56c885f8…a602`, guardado no git;
  - o `.xls` extraído, SHA-256 `30c6be3a…0933`, fica fora do git e é recriado ao descompactar o zip.
- **Amostra:** `codigo/experimento/preparar_default.py`.
  - Dos 30.000 registros, ficam 29.892 após remover duplicatas exatas nas entradas.
  - Desses, são sorteados 1000 estratificados (221 inadimplentes), com semente 42.
  - Detalhes em `dados/processados/default.json`.
- **Divisão:** a mesma 80/20 do E1, com semente 42.
- **Medida de reutilização:** `alteracoes-config.diff` compara a configuração do E1 com esta. Até aqui, só a configuração mudou e nenhum código em `codigo/lazylabel/src/`.
- **Baseline:** validação cruzada só no dev, com acurácia 0,816 e macro-F1 0,688. O teste segue fechado.
