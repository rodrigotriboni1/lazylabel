import csv
import json
from pathlib import Path
import sys

from finlabel.labeling.task import load_task
from finlabel.project import load_project, open_source
from finlabel.review import ReviewAction, ReviewLog

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "project"
TRAIN_CSV = ROOT / "data" / "train.csv"
REFERENCE = ROOT / "data" / "reference.jsonl"


def main(run_id):
    project = load_project(PROJECT)
    metadata_path = project.workspace_dir / "runs" / run_id / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    suggestions_path = metadata_path.parent / "suggestions.jsonl"
    suggestions = [json.loads(line) for line in suggestions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    train_rows = list(csv.DictReader(TRAIN_CSV.open(encoding="utf-8", newline="")))
    reference_rows = [json.loads(line) for line in REFERENCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    train_labels = [item["label"] for item in reference_rows if item["split"] == "train"]
    source = open_source(project, metadata["source_name"])
    task = load_task(project.workspace_dir / "tasks" / (metadata["task_id"] + ".json"),
                     available_columns=tuple(column.name for column in source.columns()))
    record_to_index = {}
    for index, record in enumerate(source.iter_records(task.input_columns)):
        record_to_index[record.record_id] = index

    log = ReviewLog(project.workspace_dir / "review.jsonl")
    existing = {
        (event.run_id, event.suggestion_id): event
        for event in log.read()
        if event.run_id and event.suggestion_id
    }
    matched = corrected = unavailable = 0
    for item in suggestions:
        index = record_to_index.get(item["record_id"])
        if index is None or index >= len(train_labels):
            unavailable += 1
            continue
        gold = train_labels[index]
        action = ReviewAction.ACCEPTED if item["label"] == gold else ReviewAction.CORRECTED
        event_key = (run_id, item["suggestion_id"])
        previous = existing.get(event_key)
        if previous is not None:
            if (previous.record_id != item["record_id"] or previous.suggested_label != item["label"]
                    or previous.action != action or previous.final_label != gold):
                raise ValueError("Existing synthetic review event conflicts with the current suggestion/oracle.")
            matched += action is ReviewAction.ACCEPTED
            corrected += action is ReviewAction.CORRECTED
            continue
        matched += action is ReviewAction.ACCEPTED
        corrected += action is ReviewAction.CORRECTED
        event = log.record(
            item["record_id"], item["label"], action, gold, item["model_ref"],
            run_id=run_id, source_name=metadata["source_name"], task_id=task.task_id,
            input_digest=item["input_digest"], suggestion_id=item["suggestion_id"],
        )
        existing[event_key] = event
    print(json.dumps({
        "run_id": run_id, "source_rows": len(train_rows), "valid_suggestions": len(suggestions),
        "accepted_equal_to_oracle": matched, "corrected_to_oracle": corrected,
        "unavailable_or_invalid": unavailable, "review_events": matched + corrected,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: review_synthetic.py RUN_ID")
    main(sys.argv[1])
