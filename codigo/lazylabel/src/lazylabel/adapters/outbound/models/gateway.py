"""Text generation through the Vercel AI Gateway (OpenAI-compatible chat API).

Selected with a model id prefixed by ``gateway:``, e.g. ``gateway:anthropic/claude-haiku-4.5``.
Cloud use is authorized by decision 8 (tcc/decisoes.md). The key comes only from
the ``AI_GATEWAY_API_KEY`` environment variable and is never logged or stored.
"""
import json
import os
import urllib.request

PREFIX = "gateway:"
GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"


def is_gateway_model(model_id) -> bool:
    return isinstance(model_id, str) and model_id.startswith(PREFIX)


class GatewayTextGenerationBackend:
    def __init__(self, model_id: str, *, api_key=None, opener=urllib.request.urlopen, timeout=60):
        model = model_id[len(PREFIX):] if is_gateway_model(model_id) else model_id
        if not model.strip():
            raise ValueError("gateway model id must name a provider/model, e.g. gateway:anthropic/claude-haiku-4.5")
        self.model = model
        self.model_ref = PREFIX + model
        self.model_id = self.model_ref  # read by the analysis planner for run provenance
        self._api_key = api_key if api_key is not None else os.environ.get("AI_GATEWAY_API_KEY", "")
        self._opener = opener
        self._timeout = timeout

    def generate(self, prompt: str, *, max_new_tokens: int, system=None) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string.")
        if max_new_tokens < 1 or max_new_tokens > 8192:
            raise ValueError("max_new_tokens must be between 1 and 8192.")
        if not self._api_key:
            raise RuntimeError("Set AI_GATEWAY_API_KEY to use a gateway: model.")
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        body = json.dumps({"model": self.model, "messages": messages,
                           "max_tokens": max_new_tokens, "temperature": 0}).encode("utf-8")
        request = urllib.request.Request(GATEWAY_URL, data=body, method="POST", headers={
            "Authorization": "Bearer " + self._api_key, "Content-Type": "application/json"})
        with self._opener(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        try:
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ValueError("AI Gateway returned no message content.") from exc
