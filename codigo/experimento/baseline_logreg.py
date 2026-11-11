"""Baseline de regressão logística para o experimento real do LazyLabel.

Segue tcc/protocolo-experimental.md: divisão estratificada 80/20 com
semente 42 e índices salvos, validação cruzada de 5 partições só no
desenvolvimento, e o teste final só é aberto com --final.

Uso (scikit-learn não é dependência do projeto):
  uv run --with scikit-learn --with pandas python codigo/experimento/baseline_logreg.py \
      --csv dados/brutos/base.csv --target kredit --numeric laufzeit,hoehe,alter --positive 0 --id record_id --out resultados/baseline
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


def ece(confidence, correct, bins=10):
    """Erro de calibração top-label, 10 faixas de mesma largura (protocolo v0.2)."""
    total, n = 0.0, len(confidence)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidence) if lo < c <= hi or (b == 0 and c == 0)]
        if idx:
            total += len(idx) / n * abs(sum(correct[i] for i in idx) / len(idx) - sum(confidence[i] for i in idx) / len(idx))
    return total


def scores(model, x, y):
    prob = model.predict_proba(x)[:, 1]
    pred = (prob >= 0.5).astype(int)
    top = [max(p, 1 - p) for p in prob]
    correct = [int(a == b) for a, b in zip(pred, y)]
    return {
        "accuracy": accuracy_score(y, pred),
        "macro_f1": f1_score(y, pred, average="macro"),
        "brier": brier_score_loss(y, prob),
        # top-label: mesma definição de confiança do LazyLabel (probabilidade de acerto)
        "brier_top_label": sum((c - k) ** 2 for c, k in zip(top, correct)) / len(top),
        "ece_top_label": ece(top, correct),
    }


def per_case(model, x, y, ids):
    prob = model.predict_proba(x)[:, 1]
    return [{"record_id": str(i), "target": int(t), "pred": int(p >= 0.5), "confidence": float(max(p, 1 - p))}
            for i, t, p in zip(ids, y, prob)]


def risk_coverage(cases):
    """Acurácia mantendo só os x% de maior confiança."""
    ordered = sorted(cases, key=lambda c: -c["confidence"])
    curve = []
    for pct in range(5, 101, 5):
        kept = ordered[:max(1, round(len(ordered) * pct / 100))]
        curve.append({"coverage": pct / 100, "accuracy": sum(c["pred"] == c["target"] for c in kept) / len(kept),
                      "min_confidence": kept[-1]["confidence"]})
    return curve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--positive", default="1", help="valor do alvo tratado como classe positiva (y=1)")
    ap.add_argument("--numeric", default="", help="colunas numéricas, separadas por vírgula")
    ap.add_argument("--id", default=None, help="coluna de identificação (fica fora do modelo)")
    ap.add_argument("--splits-dir", default=None, help="grava dev.csv e teste.csv a partir da divisão")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument("--final", action="store_true", help="avalia o teste final (uma única vez, após congelar a configuração)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    if args.target not in df.columns:
        raise SystemExit("coluna-alvo ausente: {}".format(args.target))
    y = (df[args.target].astype(str) == args.positive).astype(int)
    ids = df[args.id] if args.id else df.index
    x = df.drop(columns=[args.target] + ([args.id] if args.id else []))
    numeric = [c for c in args.numeric.split(",") if c]
    unknown = [c for c in numeric if c not in x.columns]
    if unknown:
        raise SystemExit("colunas numéricas ausentes: {}".format(unknown))
    categorical = [c for c in x.columns if c not in numeric]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dev_idx, test_idx = train_test_split(range(len(df)), test_size=0.2, stratify=y, random_state=args.seed)
    (out / "split-indices.json").write_text(json.dumps({"seed": args.seed, "dev": sorted(dev_idx), "test": sorted(test_idx)}))

    if args.splits_dir:
        sd = Path(args.splits_dir)
        sd.mkdir(parents=True, exist_ok=True)
        df.iloc[sorted(dev_idx)].to_csv(sd / "dev.csv", index=False)
        df.iloc[sorted(test_idx)].to_csv(sd / "teste.csv", index=False)
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
        cases = per_case(model, x.iloc[test_idx], y.iloc[test_idx], ids[test_idx] if args.id else test_idx)
        (out / "test-predictions.json").write_text(json.dumps(cases, indent=1))
        result["risk_coverage"] = risk_coverage(cases)
    (out / "baseline.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "cv_folds"}, indent=2))


if __name__ == "__main__":
    main()
