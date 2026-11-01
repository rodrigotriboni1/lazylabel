"""Failed adapter initialization must never publish a usable base-model cache."""
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace
import sys

import pytest

from finlabel.adapters.outbound.models.text_generation import TransformersTextGenerationBackend


class TokenIds:
    shape = (1, 2)


class Inputs(dict):
    def to(self, device):
        return self


class Tokenizer:
    chat_template = None

    def __call__(self, prompt, *, return_tensors):
        return Inputs(input_ids=TokenIds())

    def decode(self, tokens, *, skip_special_tokens):
        return '{"label":"low"}'


class BaseModel:
    device = 'cpu'

    def generate(self, **kwargs):
        raise AssertionError('Uninitialized base model was used as the promoted adapter.')


class AdapterModel(BaseModel):
    def __init__(self, state):
        self.state = state
        self.evaluated = False
        self.placed_on = None

    def to(self, device):
        if self.state.failure == 'device':
            raise RuntimeError('fixture device placement failed')
        self.placed_on = device
        return self

    def eval(self):
        if self.state.failure == 'eval':
            raise RuntimeError('fixture eval failed')
        self.evaluated = True
        return self

    def generate(self, **kwargs):
        assert self.evaluated
        assert self.placed_on == 'cpu'
        return [[1, 2, 3]]


def install_dependencies(monkeypatch, state):
    transformers = ModuleType('transformers')
    class AutoTokenizer:
        @staticmethod
        def from_pretrained(path, **kwargs):
            assert path == '/local/adapter'
            assert kwargs == {'trust_remote_code': False, 'local_files_only': True}
            return Tokenizer()
    class AutoModelForCausalLM:
        @staticmethod
        def from_pretrained(path, **kwargs):
            assert path == 'local/model'
            assert kwargs == {'revision': 'r1', 'trust_remote_code': False}
            return BaseModel()
    transformers.AutoTokenizer = AutoTokenizer
    transformers.AutoModelForCausalLM = AutoModelForCausalLM
    peft = ModuleType('peft')
    class PeftModel:
        @staticmethod
        def from_pretrained(base, path, *, is_trainable):
            assert isinstance(base, BaseModel)
            assert path == '/local/adapter'
            assert is_trainable is False
            if state.failure == 'adapter_load':
                raise RuntimeError('fixture adapter load failed')
            return AdapterModel(state)
    peft.PeftModel = PeftModel
    monkeypatch.setitem(sys.modules, 'transformers', transformers)
    monkeypatch.setitem(sys.modules, 'peft', None if state.failure == 'missing_peft' else peft)
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(inference_mode=nullcontext))
    return peft


@pytest.mark.parametrize('entrypoint', ['_load', 'generate'])
@pytest.mark.parametrize('failure, message', [
    ('missing_peft', r'Install finlabel-local\[train\]'),
    ('adapter_load', 'fixture adapter load failed'),
    ('device', 'fixture device placement failed'),
    ('eval', 'fixture eval failed'),
])
def test_repeated_initialization_failures_never_cache_a_partial_model_and_allow_retry(monkeypatch, entrypoint, failure, message):
    state = SimpleNamespace(failure=failure)
    peft = install_dependencies(monkeypatch, state)
    backend = TransformersTextGenerationBackend('local/model', 'r1', device='cpu',
        adapter_path='/local/adapter', model_ref='local/model@r1+peft:' + 'a'*64)
    def invoke():
        if entrypoint == '_load':
            return backend._load()
        return backend.generate('Classify the record', max_new_tokens=16)

    for _ in range(2):
        with pytest.raises(RuntimeError, match=message):
            invoke()
    assert backend._model is None
    assert backend._tokenizer is None

    state.failure = None
    monkeypatch.setitem(sys.modules, 'peft', peft)
    value = invoke()
    assert isinstance(backend._model, AdapterModel)
    assert isinstance(backend._tokenizer, Tokenizer)
    assert backend._model.evaluated
    assert backend._model.placed_on == 'cpu'
    assert backend.model_ref == 'local/model@r1+peft:' + 'a'*64
    if entrypoint == 'generate':
        assert value == '{"label":"low"}'
