import argparse
import csv
import json
import os
from pathlib import Path
import time

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from finlabel.labeling.service import _prompt
from finlabel.labeling.task import load_task
from finlabel.labeling.suggestions import parse_suggestion

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"


def metrics(labels, expected, predicted):
    columns = tuple(labels) + ("invalid",)
    confusion = {label: {other: 0 for other in columns} for label in labels}
    correct = 0
    for gold, guess in zip(expected, predicted):
        if guess in labels:
            confusion[gold][guess] += 1
        else:
            confusion[gold]["invalid"] += 1
        if gold == guess:
            correct += 1
    f1_values = []
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in labels if other != label)
        fn = sum(confusion[label][other] for other in columns if other != label)
        denom = (2 * tp) + fp + fn
        f1_values.append(2 * tp / denom if denom else 0.0)
    return {
        "count": len(expected), "valid_predictions": sum(guess in labels for guess in predicted),
        "valid_prediction_rate": sum(guess in labels for guess in predicted) / len(predicted) if predicted else 0.0,
        "exact_accuracy": correct / len(expected) if expected else 0.0,
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else 0.0,
        "confusion_matrix": confusion,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--chat-template", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    task = load_task(ROOT / "project" / ".finlabel" / "tasks" / "natureza_movimentacao_sintetica.json")
    test_path = ROOT / "data" / "heldout.csv"
    refs = [json.loads(line) for line in (ROOT / "data" / "reference.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = [item["label"] for item in refs if item["split"] == "heldout"]
    with test_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != len(expected):
        raise ValueError("Held-out examples and references have different lengths.")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, revision=REVISION, torch_dtype=torch.float32, trust_remote_code=False,
    ).to(device)
    if args.adapter:
        model = PeftModel.from_pretrained(model, str(args.adapter), is_trainable=False)
    model.eval()

    raw_rows = []
    predicted = []
    start = time.monotonic()
    for index, (row, gold) in enumerate(zip(rows, expected)):
        prompt = _prompt(task, {"historico": row["historico"]})
        if args.chat_template:
            prompt = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True,
            )
        encoded = tokenizer(prompt, return_tensors="pt").to(device)
        with torch.inference_mode():
            output = model.generate(**encoded, max_new_tokens=64, do_sample=False)
        text = tokenizer.decode(output[0][encoded["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
        try:
            guess, rationale = parse_suggestion(text, valid_labels=set(task.labels))
        except ValueError:
            guess, rationale = None, None
        predicted.append(guess)
        raw_rows.append({
            "index": index, "description": row["historico"], "gold": gold,
            "prediction": guess, "rationale": rationale, "raw_output": text,
        })
    elapsed = time.monotonic() - start
    result = {
        "model_id": MODEL_ID, "model_revision": REVISION,
        "adapter": str(args.adapter) if args.adapter else None, "device": device,
        "prompt_format": "model_chat_template" if args.chat_template else "plain_text",
        "generation": {"do_sample": False, "max_new_tokens": 64},
        "metrics": metrics(task.labels, expected, predicted),
        "elapsed_seconds": round(elapsed, 3), "predictions": raw_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: value for key, value in result.items() if key != "predictions"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
