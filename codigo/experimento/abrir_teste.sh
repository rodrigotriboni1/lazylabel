#!/usr/bin/env bash
# Abre o teste final UMA vez: baseline --final, LazyLabel rotula teste.csv, avaliação conjunta.
# Uso: bash codigo/experimento/abrir_teste.sh <exp> <alvo> <mapa> <positivo-baseline> <colunas-numericas>
set -euo pipefail
E="$1"; TARGET="$2"; MAP="$3"; POS="$4"; NUM="$5"
X="$(dirname "$0")"; L="$X/../lazylabel/.venv/bin/lazylabel"; P="$E/projeto"
MARK="$E/resultados/TESTE-ABERTO"
if [ -e "$MARK" ]; then echo "teste já foi aberto em $(cat "$MARK")"; exit 1; fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$MARK"
uv run -q --with scikit-learn --with pandas python "$X/baseline_logreg.py" --csv "$E/dados/processados/$(basename "$E" | sed 's/-real//').csv" \
  --target "$TARGET" --positive "$POS" --id record_id --numeric "$NUM" --out "$E/resultados/baseline" --final > /dev/null
"$L" source add-csv teste "$E/dados/processados/teste.csv" --project "$P" >/dev/null
"$L" label teste --task risco --project "$P" > "$E/resultados/label-teste.json" 2> "$E/resultados/label-teste.log"
OUT=$(ls -td "$P"/.lazylabel/label-runs/*/ | head -1)outcomes.jsonl
python3 -I "$X/avaliar_teste.py" --teste "$E/dados/processados/teste.csv" --target "$TARGET" --label-map "$MAP" \
  --outcomes "$OUT" --baseline "$E/resultados/baseline/test-predictions.json" --baseline-positive "$POS" \
  --out "$E/resultados/final.json"
