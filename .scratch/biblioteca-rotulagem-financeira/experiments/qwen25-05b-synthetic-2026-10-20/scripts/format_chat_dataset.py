import hashlib
import json
import os
from pathlib import Path

from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    source = ROOT / "data" / "reviewed-training.jsonl"
    source_manifest = source.with_suffix(source.suffix + ".manifest.json")
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION, trust_remote_code=False)
    output = ROOT / "data" / "qwen-chat-training.jsonl"
    rows = []
    with source.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if set(row) != {"prompt", "completion"}:
                raise ValueError("Unexpected training schema on line {}".format(line_number))
            prompt = tokenizer.apply_chat_template(
                [{"role": "user", "content": row["prompt"]}], tokenize=False, add_generation_prompt=True,
            )
            rows.append({"prompt": prompt, "completion": row["completion"]})
    output.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    manifest.update({
        "path": str(output), "row_count": len(rows), "dataset_sha256": sha256(output),
        "source_dataset_path": str(source), "source_dataset_sha256": sha256(source),
        "prompt_format": "Qwen2.5 tokenizer chat template; single user message and assistant generation prefix",
        "prompt_formatter_model": MODEL_ID, "prompt_formatter_revision": REVISION,
    })
    output.with_suffix(output.suffix + ".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(rows), "dataset_sha256": manifest["dataset_sha256"],
                      "source_dataset_sha256": manifest["source_dataset_sha256"],
                      "path": str(output), "prompt_format": manifest["prompt_format"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
