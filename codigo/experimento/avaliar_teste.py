"""Avaliação final (uma única vez) do LazyLabel e do baseline no mesmo teste.

Junta os outcomes do `lazylabel label teste` com o teste.csv pela record_ref
(sha256(fonte\\0fonte:linha)), calcula as métricas do protocolo v0.2 e um
bootstrap pareado estratificado (1000 reamostragens, semente 42). Uso:
  python3 codigo/experimento/avaliar_teste.py --teste teste.csv --target kredit \
      --label-map '{"0":"bad","1":"good"}' --outcomes outcomes.jsonl \
      --baseline test-predictions.json --baseline-positive 0 --out resultados/final.json
"""
import argparse
import csv
import hashlib
import json
import random
from pathlib import Path


def ece(conf, correct, bins=10):
    n, total = len(conf), 0.0
    for b in range(bins):
        idx = [i for i, c in enumerate(conf) if b / bins < c <= (b + 1) / bins or (b == 0 and c == 0)]
        if idx:
            total += len(idx) / n * abs(sum(correct[i] for i in idx) / len(idx) - sum(conf[i] for i in idx) / len(idx))
    return total


def macro_f1(pairs, labels):
    f = []
    for lab in labels:
        tp = sum(p == lab and t == lab for p, t in pairs)
        fp = sum(p == lab and t != lab for p, t in pairs)
        fn = sum(p != lab and t == lab for p, t in pairs)
        f.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return sum(f) / len(f)


def metrics(rows, labels):
    if not rows:
        return {"n": 0}
    pairs = [(r["pred"], r["target"]) for r in rows]
    correct = [int(p == t) for p, t in pairs]
    out = {"n": len(rows), "accuracy": sum(correct) / len(rows), "macro_f1": macro_f1(pairs, labels),
           "confusion": {f"{t}->{p}": sum(1 for a, b in pairs if a == p and b == t) for t in labels for p in labels}}
    if all(r.get("confidence") is not None for r in rows):
        conf = [r["confidence"] for r in rows]
        out["brier_top_label"] = sum((c - k) ** 2 for c, k in zip(conf, correct)) / len(rows)
        out["ece_top_label"] = ece(conf, correct)
    return out


def main():
    ap = argparse.ArgumentParser()
    for name in ("teste", "target", "label-map", "outcomes", "baseline", "baseline-positive", "out"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--source", default="teste")
    ap.add_argument("--thresholds", default=None,
                    help="EXPLORATÓRIO: reaplica limiares por rótulo às previsões salvas, ex. '{\"bad\":0.6,\"good\":0.8}'")
    a = ap.parse_args()
    label_map = json.loads(a.label_map)
    labels = sorted(set(label_map.values()))
    truth = {}
    with open(a.teste, encoding="utf-8") as handle:
        for n, row in enumerate(csv.DictReader(handle), start=1):
            ref = hashlib.sha256("{}\0{}:{}".format(a.source, a.source, n).encode()).hexdigest()
            truth[ref] = (row["record_id"], label_map[row[a.target]])
    outcomes = [json.loads(l) for l in open(a.outcomes, encoding="utf-8") if l.strip()]
    assert {o["record_ref"] for o in outcomes} == set(truth), "outcomes não cobrem exatamente o teste"
    lazy = []
    for o in outcomes:
        rid, target = truth[o["record_ref"]]
        applied = o["state"] == "applied"
        reason = o.get("reason_code")
        if a.thresholds and reason in (None, "below_threshold") and o.get("confidence") is not None:
            applied = o["confidence"] >= json.loads(a.thresholds)[o["predicted_label"]]
            reason = None if applied else "below_threshold"
        lazy.append({"record_id": rid, "target": target, "pred": o.get("predicted_label"),
                     "confidence": o.get("confidence"), "applied": applied, "reason": reason})
    neg = [l for l in labels if label_map[a.baseline_positive] != l][0]
    base = {}
    for c in json.load(open(a.baseline, encoding="utf-8")):
        to = lambda v: label_map[a.baseline_positive] if v == 1 else neg
        base[c["record_id"]] = {"record_id": c["record_id"], "target": to(c["target"]), "pred": to(c["pred"]),
                                "confidence": c["confidence"]}
    assert set(base) == {r["record_id"] for r in lazy}, "baseline e LazyLabel com registros diferentes"
    applied = [r for r in lazy if r["applied"]]
    scored = [r for r in lazy if r["pred"] is not None and r["confidence"] is not None]
    cov = len(applied) / len(lazy)
    base_all = list(base.values())
    base_same = [base[r["record_id"]] for r in applied]
    k = len(applied)
    base_top = sorted(base_all, key=lambda r: -r["confidence"])[:k]  # mesma cobertura
    result = {"n_test": len(lazy), "coverage": cov,
              "reasons": {str(x): sum(1 for r in lazy if r["reason"] == x) for x in {r["reason"] for r in lazy}},
              "lazylabel_applied": metrics(applied, labels),
              "lazylabel_all_scored": metrics(scored, labels),
              "baseline_all": metrics(base_all, labels),
              "baseline_same_records": metrics(base_same, labels),
              "baseline_same_coverage": metrics(base_top, labels)}
    if k:
        rng, diffs = random.Random(42), []
        strata = {lab: [r for r in applied if r["target"] == lab] for lab in labels}
        for _ in range(1000):
            sample = [rng.choice(s) for s in strata.values() if s for _ in s]
            diffs.append(sum(r["pred"] == r["target"] for r in sample) / len(sample)
                         - sum(base[r["record_id"]]["pred"] == r["target"] for r in sample) / len(sample))
        diffs.sort()
        result["accuracy_diff_same_records_ci95"] = [diffs[24], diffs[974]]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
