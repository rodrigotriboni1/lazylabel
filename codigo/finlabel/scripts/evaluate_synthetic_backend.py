#!/usr/bin/env python3
"""Reproduce the local FinLabel backend smoke using the saved synthetic holdout."""

import argparse
import csv
import json
import time
from pathlib import Path

from finlabel.labeling.service import _prompt
from finlabel.labeling.suggestions import parse_suggestion
from finlabel.labeling.task import task_from_dict
from finlabel.models.text_generation import TransformersTextGenerationBackend


def _metrics(labels, expected, predicted):
    columns = tuple(labels) + ("invalid",)
    confusion = {label: {other: 0 for other in columns} for label in labels}
    for gold, guess in zip(expected, predicted):
        confusion[gold][guess if guess in labels else "invalid"] += 1
    f1 = []
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in labels if other != label)
        fn = sum(confusion[label][other] for other in columns if other != label)
        denominator = 2 * tp + fp + fn
        f1.append(2 * tp / denominator if denominator else 0.0)
    valid = sum(item in labels for item in predicted)
    return {
        "count": len(expected),
        "valid_predictions": valid,
        "valid_prediction_rate": valid / len(expected) if expected else 0.0,
        "exact_accuracy": sum(gold == guess for gold, guess in zip(expected, predicted)) / len(expected) if expected else 0.0,
        "macro_f1": sum(f1) / len(f1) if f1 else 0.0,
        "confusion_matrix": confusion,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True,
                        help="Existing synthetic Qwen experiment directory.")
    parser.add_argument("--output", type=Path, required=True,
                        help="Path for the JSON evaluation record.")
    parser.add_argument("--device", default="auto", help="Transformers device, such as mps or cpu.")
    args = parser.parse_args()
    experiment = args.experiment.expanduser().resolve()
    task = task_from_dict(json.loads((experiment / "task.json").read_text(encoding="utf-8")))
    references = [json.loads(line) for line in (experiment / "data/reference.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = [row["label"] for row in references if row["split"] == "heldout"]
    with (experiment / "data/heldout.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(expected) or not rows:
        raise ValueError("Held-out examples and references must have the same non-zero row count.")

    backend = TransformersTextGenerationBackend(task.model_id, task.model_revision,
                                                  device=args.device,
                                                  adapter_path=str(experiment / "adapter"))
    predicted, records = [], []
    started = time.monotonic()
    for index, (row, gold) in enumerate(zip(rows, expected)):
        if set(task.input_columns) != {"historico"}:
            raise ValueError("This saved synthetic experiment expects only the historico feature.")
        prompt = _prompt(task, {"historico": row["historico"]})
        raw = backend.generate(prompt, max_new_tokens=64)
        try:
            label, _ = parse_suggestion(raw, valid_labels=set(task.labels))
        except ValueError:
            label = None
        predicted.append(label)
        records.append({"index": index, "gold": gold, "prediction": label})

    result = {
        "model_id": task.model_id,
        "model_revision": task.model_revision,
        "adapter": str((experiment / "adapter").resolve()),
        "device": args.device,
        "prompt_format": "TransformersTextGenerationBackend.chat_template",
        "generation": {"do_sample": False, "max_new_tokens": 64},
        "metrics": _metrics(task.labels, expected, predicted),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "predictions": records,
        "limitations": (
            "Synthetic-only holdout. The historical adapter is evaluated directly; it is not eligible "
            "for active promotion because it lacks current adapter/calibrator identity artifacts."
        ),
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "predictions"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
