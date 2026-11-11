"""Amostra estratificada de 1000 registros da UCI Default of Credit Card Clients (E2).

Remove duplicatas exatas nas colunas de entrada, sorteia na prevalência original
com semente 42 e grava CSV com record_id e alvo `default`. Não altera o bruto. Uso:
  uv run --with pandas --with xlrd --with scikit-learn python codigo/experimento/preparar_default.py \
      "tcc/experimentos/default-real/dados/brutos/default of credit card clients.xls" \
      tcc/experimentos/default-real/dados/processados/default.csv
"""
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split


def main(src, dst, n=1000, seed=42):
    df = pd.read_excel(src, header=1)
    target = "default payment next month"
    inputs = [c for c in df.columns if c not in ("ID", target)]
    before = len(df)
    df = df.drop_duplicates(subset=inputs, keep=False)  # descarta grupos duplicados, inclusive contraditórios
    sample, _ = train_test_split(df, train_size=n, stratify=df[target], random_state=seed)
    sample = sample.sort_values("ID")
    out = pd.DataFrame({"record_id": "dccc-" + sample["ID"].astype(str)})
    for c in inputs:
        out[c] = sample[c].values
    out["default"] = sample[target].values
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dst, index=False)
    info = {"rows_raw": before, "rows_after_dedup": len(df), "sample": len(out),
            "positives": int(out["default"].sum()), "seed": seed,
            "sha256": hashlib.sha256(Path(dst).read_bytes()).hexdigest()}
    Path(dst).with_suffix(".json").write_text(json.dumps(info, indent=2))
    print(json.dumps(info))


if __name__ == "__main__":
    main(*sys.argv[1:3])
