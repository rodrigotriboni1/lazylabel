"""Lazy Hugging Face Transformers integration for local text generation."""

import json
from typing import Mapping, Optional, Protocol

from finlabel.labeling.prediction import Prediction
from finlabel.labeling.task import LabelTask


# v2 scores the tokenizer's joint prompt+JSON encoding. v1 concatenated two
# independently tokenized sequences; its calibration artifacts are incompatible.
RAW_SCORE_METHOD = "label_json_mean_log_likelihood_v2"


def render_model_prompt(prompt: str, tokenizer) -> str:
    """Use the model's chat template, or preserve plain text for base models without one."""
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
        )
    return prompt


class TextGenerationBackend(Protocol):
    def generate(self, prompt: str, *, max_new_tokens: int) -> str: ...


class PredictionBackend(Protocol):
    def predict(self, selected_values: Mapping, *, task: LabelTask,
                max_new_tokens: int) -> Prediction: ...


class TransformersTextGenerationBackend:
    def __init__(self, model_id: str, revision: Optional[str] = None, device: str = "auto",
                 adapter_path: Optional[str] = None, model_ref: Optional[str] = None,
                 generation_config: Optional[Mapping] = None):
        if not model_id or not model_id.strip():
            raise ValueError("model_id must be a non-empty local model reference.")
        self.model_id = model_id
        self.revision = revision
        self.device = device
        self.adapter_path = adapter_path
        self.model_ref = model_ref or ("{}@{}".format(model_id, revision) if revision else model_id)
        self.generation_config = dict(generation_config) if generation_config is not None else None
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is not None:
            return
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Install finlabel-local[models] to use local model inference.") from exc
        kwargs = {"revision": self.revision, "trust_remote_code": False}
        if self.device == "auto":
            kwargs["device_map"] = "auto"
            kwargs["torch_dtype"] = "auto"
        if self.adapter_path:
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.adapter_path, trust_remote_code=False, local_files_only=True
            )
        else:
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_id, **kwargs)
        self._model = AutoModelForCausalLM.from_pretrained(self.model_id, **kwargs)
        if self.adapter_path:
            try:
                from peft import PeftModel
            except ImportError as exc:
                raise RuntimeError("Install finlabel-local[train] to load a local PEFT adapter.") from exc
            self._model = PeftModel.from_pretrained(self._model, self.adapter_path, is_trainable=False)
        if self.device != "auto":
            self._model.to(self.device)
        self._model.eval()

    def generate(self, prompt: str, *, max_new_tokens: int) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")
        if max_new_tokens < 1 or max_new_tokens > 8192:
            raise ValueError("max_new_tokens must be between 1 and 8192.")
        if self.generation_config is not None and max_new_tokens != self.generation_config.get("max_new_tokens"):
            raise ValueError("Requested generation length does not match the verified model metadata.")
        self._load()
        if getattr(self._tokenizer, "chat_template", None):
            prompt = render_model_prompt(prompt, self._tokenizer)
            inputs = self._tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        else:
            inputs = self._tokenizer(prompt, return_tensors="pt")
        inputs = inputs.to(self._model.device)
        prompt_length = inputs["input_ids"].shape[1]
        import torch
        with torch.inference_mode():
            outputs = self._model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        return self._tokenizer.decode(outputs[0][prompt_length:], skip_special_tokens=True).strip()


    def _label_scores(self, prompt: str, labels) -> dict:
        """Raw mean log likelihood of exact JSON continuation tokens.

        v2 uses joint encoding and character offsets, excluding special tokens.
        A token spanning the prompt/JSON boundary has no exact continuation span;
        unsupported offsets or such a merge fail closed instead of approximating
        the evidence. These scores require their own v2 calibration artifact.
        """
        import torch

        has_template = bool(getattr(self._tokenizer, "chat_template", None))
        if has_template:
            prompt = render_model_prompt(prompt, self._tokenizer)
        boundary = len(prompt)
        scores = {}
        with torch.inference_mode():
            for label in labels:
                completion = json.dumps({"label": label}, ensure_ascii=False, separators=(",", ":"))
                joined = prompt + completion
                try:
                    encoded = self._tokenizer(
                        joined, return_tensors="pt", add_special_tokens=not has_template,
                        return_offsets_mapping=True,
                    )
                except (NotImplementedError, TypeError) as exc:
                    raise ValueError("Exact label scoring requires tokenizer character offsets.") from exc
                offsets = encoded.pop("offset_mapping", None)
                if offsets is None:
                    raise ValueError("Tokenizer did not supply exact label token offsets.")
                spans = offsets[0].tolist()
                if any(start < boundary < end for start, end in spans):
                    raise ValueError("Tokenizer merged the prompt and label scoring boundary.")
                indices = [index for index, (start, end) in enumerate(spans)
                           if start >= boundary and end > start]
                if (not indices or indices[0] == 0
                        or indices != list(range(indices[0], indices[-1] + 1))
                        or spans[indices[0]][0] != boundary
                        or spans[indices[-1]][1] != len(joined)):
                    raise ValueError("Tokenizer cannot isolate the complete label continuation.")
                encoded = encoded.to(self._model.device)
                ids = encoded["input_ids"]
                logits = self._model(**encoded).logits
                # Token j is predicted by logits at j-1; only JSON token IDs
                # from this same joint encoding are scored, never prompt/EOS.
                target = ids[:, indices[0]:indices[-1] + 1]
                token_log_probs = logits[:, indices[0] - 1:indices[-1], :].float().log_softmax(dim=-1)
                selected = token_log_probs.gather(-1, target.unsqueeze(-1)).squeeze(-1)
                scores[label] = float(selected.mean().item())
        return scores

    def predict(self, selected_values: Mapping, *, task: LabelTask,
                max_new_tokens: int) -> Prediction:
        from finlabel.labeling.service import _prompt
        from finlabel.labeling.suggestions import parse_prediction

        if self.model_id != task.model_id or self.revision != task.model_revision:
            raise ValueError("Backend model identity must match the configured task.")
        if not isinstance(selected_values, Mapping) or set(selected_values) != set(task.input_columns):
            raise ValueError("Prediction input must contain exactly the task-selected columns.")
        prompt = _prompt(task, dict(selected_values))
        raw = self.generate(prompt, max_new_tokens=max_new_tokens)
        # Reject malformed output before performing the more expensive scoring pass.
        parse_prediction(raw, valid_labels=task.labels)
        evidence = self._label_scores(prompt, task.labels)
        return parse_prediction(raw, valid_labels=task.labels, confidence_evidence=evidence,
                                confidence_method=RAW_SCORE_METHOD)

    def predict_prompt(self, prompt: str, *, task: LabelTask, max_new_tokens: int = 256) -> Prediction:
        """Score a frozen prompt with the same generation and exact v2 scoring path."""
        from finlabel.labeling.suggestions import parse_prediction
        raw = self.generate(prompt, max_new_tokens=max_new_tokens)
        parse_prediction(raw, valid_labels=task.labels)
        evidence = self._label_scores(prompt, task.labels)
        return parse_prediction(raw, valid_labels=task.labels, confidence_evidence=evidence,
                                confidence_method=RAW_SCORE_METHOD)
