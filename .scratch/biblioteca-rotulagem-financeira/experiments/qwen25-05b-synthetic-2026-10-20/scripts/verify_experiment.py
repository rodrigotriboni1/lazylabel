import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def recompute_metrics(labels, predictions):
    columns = tuple(labels) + ("invalid",)
    confusion = {label: {other: 0 for other in columns} for label in labels}
    for item in predictions:
        gold, guess = item["gold"], item["prediction"]
        assert gold in labels
        confusion[gold][guess if guess in labels else "invalid"] += 1
    f1_values = []
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in labels if other != label)
        fn = sum(confusion[label][other] for other in columns if other != label)
        denominator = 2 * tp + fp + fn
        f1_values.append(2 * tp / denominator if denominator else 0.0)
    valid = sum(item["prediction"] in labels for item in predictions)
    count = len(predictions)
    return {
        "count": count,
        "valid_predictions": valid,
        "valid_prediction_rate": valid / count if count else 0.0,
        "exact_accuracy": sum(item["prediction"] == item["gold"] for item in predictions) / count if count else 0.0,
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else 0.0,
        "confusion_matrix": confusion,
    }


def assert_metrics_match(saved, computed):
    for key in ("count", "valid_predictions", "confusion_matrix"):
        assert saved[key] == computed[key], "Saved metric does not match predictions: {}".format(key)
    for key in ("valid_prediction_rate", "exact_accuracy", "macro_f1"):
        assert math.isclose(saved[key], computed[key], rel_tol=0, abs_tol=1e-12), (
            "Saved metric does not match predictions: {}".format(key))


def main():
    generation = json.loads((ROOT / "data" / "generation-manifest.json").read_text())
    train = ROOT / "data" / "train.csv"
    heldout = ROOT / "data" / "heldout.csv"
    assert sha(train) == generation["train_sha256"]
    assert sha(heldout) == generation["heldout_sha256"]
    with train.open(encoding="utf-8", newline="") as f:
        train_rows = list(csv.DictReader(f))
    with heldout.open(encoding="utf-8", newline="") as f:
        heldout_rows = list(csv.DictReader(f))
    assert not ({row["historico"] for row in train_rows} & {row["historico"] for row in heldout_rows})
    references = [json.loads(line) for line in (ROOT / "data" / "reference.jsonl").read_text().splitlines() if line.strip()]
    heldout_labels = [item["label"] for item in references if item["split"] == "heldout"]
    assert len(heldout_rows) == len(heldout_labels) == 24

    export = ROOT / "data" / "reviewed-training.jsonl"
    manifest = json.loads(export.with_suffix(export.suffix + ".manifest.json").read_text())
    data = ROOT / "data" / "qwen-chat-training.jsonl"
    chat_manifest = json.loads(data.with_suffix(data.suffix + ".manifest.json").read_text())
    training = [json.loads(line) for line in data.read_text().splitlines() if line.strip()]
    assert len(training) == manifest["row_count"] == chat_manifest["row_count"] == 72
    assert sha(export) == manifest["dataset_sha256"] == chat_manifest["source_dataset_sha256"]
    assert sha(data) == chat_manifest["dataset_sha256"]
    assert manifest["model_ref"] == chat_manifest["model_ref"] == (
        "Qwen/Qwen2.5-0.5B-Instruct@7ae557604adf67be50417f59c2c2f167def9a775")
    assert all("SYNTH-TRAIN" not in row["prompt"] and "referencia_interna" not in row["prompt"] for row in training)
    assert all(row["completion"] in [json.dumps({"label": label}, ensure_ascii=False, separators=(",", ":"))
                                     for label in ("receita", "despesa_operacional", "custo_financeiro")]
               for row in training)

    run_path = ROOT / "project" / ".finlabel" / "runs" / json.loads((ROOT / "results" / "base-label-run.json").read_text())["run_id"]
    run_meta = json.loads((run_path / "run.json").read_text())
    assert sha(run_path / "suggestions.jsonl") == run_meta["suggestions_sha256"]
    suggestions = [json.loads(line) for line in (run_path / "suggestions.jsonl").read_text().splitlines() if line.strip()]
    assert len(suggestions) == 72
    assert all("SYNTH-TRAIN" not in line and "referencia_interna" not in line for line in (run_path / "suggestions.jsonl").read_text().splitlines())
    review_events = [json.loads(line) for line in (ROOT / "project" / ".finlabel" / "review.jsonl").read_text().splitlines() if line.strip()]
    run_events = [item for item in review_events if item.get("run_id") == run_meta["run_id"]]
    assert len(run_events) == 72
    assert len({item["suggestion_id"] for item in run_events}) == 72
    review_counts = {
        "accepted": sum(item["action"] == "accepted" for item in run_events),
        "corrected": sum(item["action"] == "corrected" for item in run_events),
    }
    review_summary = json.loads((ROOT / "results" / "synthetic-review-summary.json").read_text())
    assert review_counts == {"accepted": 38, "corrected": 34}
    assert review_summary["review_events"] == len(run_events)
    assert review_summary["accepted_equal_to_oracle"] == review_counts["accepted"]
    assert review_summary["corrected_to_oracle"] == review_counts["corrected"]

    base = json.loads((ROOT / "results" / "base-heldout-chat.json").read_text())
    tuned = json.loads((ROOT / "results" / "finetuned-heldout-chat.json").read_text())
    labels = json.loads((ROOT / "task.json").read_text())["labels"]
    assert base["model_id"] == tuned["model_id"]
    assert base["model_revision"] == tuned["model_revision"]
    assert base["prompt_format"] == tuned["prompt_format"] == "model_chat_template"
    assert base["generation"] == tuned["generation"]
    assert len(base["predictions"]) == len(tuned["predictions"]) == 24
    for index, (base_item, tuned_item, row, gold) in enumerate(zip(
        base["predictions"], tuned["predictions"], heldout_rows, heldout_labels
    )):
        assert base_item["index"] == tuned_item["index"] == index
        assert base_item["description"] == tuned_item["description"] == row["historico"]
        assert base_item["gold"] == tuned_item["gold"] == gold
    base_metrics = recompute_metrics(labels, base["predictions"])
    tuned_metrics = recompute_metrics(labels, tuned["predictions"])
    assert_metrics_match(base["metrics"], base_metrics)
    assert_metrics_match(tuned["metrics"], tuned_metrics)
    assert base_metrics["exact_accuracy"] == 9 / 24
    assert tuned_metrics["exact_accuracy"] == 17 / 24
    assert sum(a["prediction"] != a["gold"] and b["prediction"] == b["gold"]
               for a, b in zip(base["predictions"], tuned["predictions"])) == 10
    assert sum(a["prediction"] == a["gold"] and b["prediction"] != b["gold"]
               for a, b in zip(base["predictions"], tuned["predictions"])) == 2

    training_metadata = json.loads((ROOT / "adapter" / "finlabel-training.json").read_text())
    assert training_metadata["dataset_sha256"] == sha(data)
    assert training_metadata["telemetry"] == "disabled" and training_metadata["hub_upload"] is False
    adapter = ROOT / "adapter" / "adapter_model.safetensors"
    assert adapter.is_file() and adapter.stat().st_size > 0
    report = {
        "source_hashes_match_generation_manifest": True,
        "no_exact_train_test_description_overlap": True,
        "reviewed_and_formatted_rows": len(training),
        "unselected_reference_markers_absent_from_prompt_and_suggestions": True,
        "suggestion_hash_matches_run_metadata": True,
        "review_events_reconciled": len(run_events),
        "review_counts": review_counts,
        "heldout_predictions_aligned_to_source_and_reference": True,
        "metrics_recomputed_from_saved_predictions": True,
        "base_valid_predictions": base_metrics["valid_predictions"],
        "finetuned_valid_predictions": tuned_metrics["valid_predictions"],
        "base_accuracy": base_metrics["exact_accuracy"],
        "finetuned_accuracy": tuned_metrics["exact_accuracy"],
        "base_macro_f1": base_metrics["macro_f1"],
        "finetuned_macro_f1": tuned_metrics["macro_f1"],
        "net_correct_predictions": 8,
        "improved_examples": 10,
        "regressed_examples": 2,
        "adapter_file_present": adapter.is_file() and adapter.stat().st_size > 0,
        "adapter_bytes": adapter.stat().st_size,
        "adapter_sha256": sha(adapter),
    }
    (ROOT / "results" / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
