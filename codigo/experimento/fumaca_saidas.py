"""Teste de fumaça: taxa de saídas válidas do modelo-base no prompt congelado.

Usa só registros do dev (nunca o teste). Uso:
  codigo/lazylabel/.venv/bin/python codigo/experimento/fumaca_saidas.py \
      tcc/experimentos/sgc-real/config/task.json tcc/experimentos/sgc-real/dados/processados/dev.csv 50
"""
import csv
import json
import sys
import time
from pathlib import Path

from lazylabel.adapters.outbound.models.text_generation import TransformersTextGenerationBackend
from lazylabel.adapters.outbound.persistence.datasets import _trusted_prompt
from lazylabel.adapters.outbound.persistence.tasks import load_task


def main(task_path, dev_csv, n):
    task = load_task(Path(task_path))
    backend = TransformersTextGenerationBackend(task.model_id, task.model_revision)
    rows = list(csv.DictReader(open(dev_csv, encoding="utf-8")))[: int(n)]
    valid = agree = 0
    labels = {}
    started = time.monotonic()
    for row in rows:
        features = {c: row[c] for c in task.input_columns}
        try:
            p = backend.predict_prompt(_trusted_prompt(task, features), task=task, max_new_tokens=256)
        except Exception:
            continue
        if p.label in task.labels:
            valid += 1
            labels[p.label] = labels.get(p.label, 0) + 1
            agree += p.label == max(task.labels, key=p.confidence_evidence.get)
    print(json.dumps({"n": len(rows), "valid": valid, "label_equals_score_winner": agree,
                      "predicted_labels": labels, "seconds": round(time.monotonic() - started, 1)}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
