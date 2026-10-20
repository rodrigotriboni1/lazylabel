"""Lazy Hugging Face Transformers integration for local text generation."""

from typing import Optional, Protocol


class TextGenerationBackend(Protocol):
    def generate(self, prompt: str, *, max_new_tokens: int) -> str: ...


class TransformersTextGenerationBackend:
    def __init__(self, model_id: str, revision: Optional[str] = None, device: str = "auto"):
        if not model_id or not model_id.strip():
            raise ValueError("model_id must be a non-empty local model reference.")
        self.model_id = model_id
        self.revision = revision
        self.device = device
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
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id, **kwargs)
        self._model = AutoModelForCausalLM.from_pretrained(self.model_id, **kwargs)
        if self.device != "auto":
            self._model.to(self.device)
        self._model.eval()

    def generate(self, prompt: str, *, max_new_tokens: int) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")
        if max_new_tokens < 1 or max_new_tokens > 8192:
            raise ValueError("max_new_tokens must be between 1 and 8192.")
        self._load()
        inputs = self._tokenizer(prompt, return_tensors="pt")
        inputs = inputs.to(self._model.device)
        prompt_length = inputs["input_ids"].shape[1]
        outputs = self._model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        return self._tokenizer.decode(outputs[0][prompt_length:], skip_special_tokens=True).strip()
