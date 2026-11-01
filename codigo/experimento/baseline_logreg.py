"""Baseline de regressão logística para o experimento real do FinLabel.

Segue planejamento/Protocolo_experimental.md: divisão estratificada 80/20 com
semente 42 e índices salvos, validação cruzada de 5 partições só no
desenvolvimento, e o teste final só é aberto com --final.

Uso (scikit-learn não é dependência do projeto):
  uv run --with scikit-learn --with pandas python codigo/experimento/baseline_logreg.py \
      --csv dados/brutos/base.csv --target kredit --numeric laufzeit,hoehe,alter --out resultados/baseline
"""
import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, f1_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def build(numeric, categorical):
    # shortcut: colunas não listadas em --numeric são tratadas como categóricas; revisar o dicionário da base.
    pre = ColumnTransformer(
        [("num", StandardScaler(), numeric), ("cat", OneHotEncoder(handle_unknown="ignore"), categorical)]
    )
    return make_pipeline(pre, LogisticRegression(max_iter=1000))


def scores(model, x, y):
    prob = model.predict_proba(x)[:, 1]
    pred = (prob >= 0.5).astype(int)
    return {
        "accuracy": accuracy_score(y, pred),
        "macro_f1": f1_score(y, pred, average="macro"),
        "brier": brier_score_loss(y, prob),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--positive", default="1", help="valor do alvo tratado como classe positiva (y=1)")
    ap.add_argument("--numeric", default="", help="colunas numéricas, separadas por vírgula")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument("--final", action="store_true", help="avalia o teste final (uma única vez, após congelar a configuração)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    if args.target not in df.columns:
        raise SystemExit("coluna-alvo ausente: {}".format(args.target))
    y = (df[args.target].astype(str) == args.positive).astype(int)
    x = df.drop(columns=[args.target])
    numeric = [c for c in args.numeric.split(",") if c]
    unknown = [c for c in numeric if c not in x.columns]
    if unknown:
        raise SystemExit("colunas numéricas ausentes: {}".format(unknown))
    categorical = [c for c in x.columns if c not in numeric]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dev_idx, test_idx = train_test_split(range(len(df)), test_size=0.2, stratify=y, random_state=args.seed)
    (out / "split-indices.json").write_text(json.dumps({"seed": args.seed, "dev": sorted(dev_idx), "test": sorted(test_idx)}))

    xd, yd = x.iloc[dev_idx], y.iloc[dev_idx]
    folds = []
    for tr, va in StratifiedKFold(5, shuffle=True, random_state=args.seed).split(xd, yd):
        folds.append(scores(build(numeric, categorical).fit(xd.iloc[tr], yd.iloc[tr]), xd.iloc[va], yd.iloc[va]))
    result = {
        "rows": len(df),
        "positive_rate": float(y.mean()),
        "cv_mean": {k: sum(f[k] for f in folds) / len(folds) for k in folds[0]},
        "cv_folds": folds,
    }
    if args.final:
        model = build(numeric, categorical).fit(xd, yd)
        result["test"] = scores(model, x.iloc[test_idx], y.iloc[test_idx])
    (out / "baseline.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "cv_folds"}, indent=2))


if __name__ == "__main__":
    main()
