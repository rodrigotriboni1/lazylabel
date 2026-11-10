import json
import os
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from finlabel.labeling.service import suggest_labels
from finlabel.labeling.task import load_task
from finlabel.project import load_project, open_source

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"


class ChatTemplateBackend:
    model_id = MODEL_ID
    revision = REVISION

    def __init__(self):
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, revision=REVISION, device_map="auto", torch_dtype="auto", trust_remote_code=False,
        ).eval()

    def generate(self, prompt, *, max_new_tokens):
        messages = [{"role": "user", "content": prompt}]
        rendered = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(rendered, return_tensors="pt").to(self.model.device)
        with torch.inference_mode():
            output = self.model.generate(**inputs, max_new_tokens=min(max_new_tokens, 64), do_sample=False)
        return self.tokenizer.decode(output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip()


def main():
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    project = load_project(ROOT / "project")
    source = open_source(project, "synthetic_train")
    task = load_task(project.workspace_dir / "tasks" / "natureza_movimentacao_sintetica.json",
                     available_columns=tuple(column.name for column in source.columns()))
    run = suggest_labels(source, task, ChatTemplateBackend(), workspace_dir=project.workspace_dir)
    print(json.dumps({
        "run_id": run.run_id, "source": run.source_name, "task": run.task_id,
        "model_ref": run.model_ref, "suggestions": run.row_count, "invalid": run.invalid_count,
        "suggestion_file": str(run.suggestion_path), "max_new_tokens": 64,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
