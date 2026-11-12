#!/usr/bin/env bash
# Monta um projeto LazyLabel novo a partir de config/ e roda o ciclo só no dev.
# Uso: bash codigo/experimento/rodar_ciclo.sh tcc/experimentos/sgc-real kredit '{"0":"bad","1":"good"}' "UCI South German Credit, baixado em 10/11/2026"
set -euo pipefail
E="$1"; TARGET="$2"; MAP="$3"; PROV="$4"
L="$(dirname "$0")/../lazylabel/.venv/bin/lazylabel"
P="$E/projeto"
if [ -e "$P" ]; then echo "projeto já existe: $P (use um novo)"; exit 1; fi
"$L" project init "$P" >/dev/null
"$L" source add-csv dev "$E/dados/processados/dev.csv" --project "$P" >/dev/null
cp "$E/config/task.json" "$E/config/policy.json" "$P/"
"$L" task add "$P/task.json" --project "$P" >/dev/null
"$L" supervision add dev --task risco --label-column "$TARGET" --provenance "$PROV" \
  --trust-kind provided_ground_truth --label-map "$MAP" --project "$P" >/dev/null
mkdir -p "$P/.lazylabel/models/promotion-policies"
cp "$E/config/promotion-policy.json" "$P/.lazylabel/models/promotion-policies/risco.json"
cp "$E/config/training-gate.json" "$P/.lazylabel/training-gate.json"
mkdir -p "$E/resultados"
"$L" run --task risco --source dev --project "$P" > "$E/resultados/run.json" 2> "$E/resultados/run.log"
python3 -I -c "import json,sys;s=open(sys.argv[1]).read();d=json.loads(s[s.rfind(chr(10)+chr(123)+chr(10))+1:]);print(json.dumps({'labels':d['labels'],'training':d['training']},indent=1))" "$E/resultados/run.json"
