"""Fail-closed verification for locally trained adapters and their calibrators."""

import hashlib
import json
import math
from pathlib import Path


WEIGHT_SUFFIXES = (".safetensors", ".bin")
TOKENIZER_FILES = (
    "tokenizer_config.json", "tokenizer.json", "special_tokens_map.json",
    "added_tokens.json", "vocab.json", "merges.txt", "chat_template.jinja",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _aggregate_hash(paths, root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


def tokenizer_sha256(adapter_dir: Path) -> str:
    """Hash tokenizer/template files saved with the adapter, including names."""
    files = [adapter_dir / name for name in TOKENIZER_FILES if (adapter_dir / name).is_file()]
    if not files:
        raise ValueError("Adapter is missing tokenizer identity files.")
    return _aggregate_hash(files, adapter_dir)


def adapter_sha256(adapter_dir: Path) -> str:
    files = [path for path in adapter_dir.rglob("*") if path.is_file() and path.name.endswith(WEIGHT_SUFFIXES)]
    if not files:
        raise ValueError("Adapter is missing weight files.")
    return _aggregate_hash(files, adapter_dir)


def load_verified_adapter(adapter_dir, model_id: str, revision: str = None, *, calibrator_path=None) -> dict:
    """Verify adapter, tokenizer, base revision and calibrator before model load."""
    directory = Path(adapter_dir).expanduser().resolve()
    try:
        metadata = json.loads((directory / "finlabel-training.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read adapter metadata: {}".format(exc)) from exc
    if not isinstance(metadata, dict):
        raise ValueError("Adapter metadata must be a JSON object.")
    expected_ref = model_id + ("@" + revision if revision else "")
    if metadata.get("base_model_ref") != expected_ref:
        raise ValueError("Adapter base model identity does not match the requested base model and revision.")
    if metadata.get("adapter_sha256") != adapter_sha256(directory):
        raise ValueError("Adapter integrity hash does not match its weight files.")
    if metadata.get("tokenizer_sha256") != tokenizer_sha256(directory):
        raise ValueError("Adapter tokenizer/template identity does not match its saved tokenizer files.")
    generation = metadata.get("generation")
    if not isinstance(generation, dict) or generation.get("do_sample") is not False:
        raise ValueError("Adapter metadata is missing deterministic generation settings.")
    path = Path(calibrator_path).expanduser().resolve() if calibrator_path is not None else None
    if path is None:
        raise ValueError("A matching calibrator is required before adapter inference.")
    try:
        calibrator = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read calibrator artifact: {}".format(exc)) from exc
    if not isinstance(calibrator, dict):
        raise ValueError("Calibrator artifact must be a JSON object.")
    if calibrator.get("base_model_ref") != expected_ref or calibrator.get("adapter_sha256") != metadata["adapter_sha256"]:
        raise ValueError("Calibrator identity does not match the active model and adapter.")
    temperature = calibrator.get("temperature")
    threshold = calibrator.get("threshold")
    if (isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or
            not math.isfinite(temperature) or temperature <= 0 or
            isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or
            not math.isfinite(threshold) or not 0 <= threshold <= 1):
        raise ValueError("Calibrator temperature and threshold are invalid.")
    return {**metadata, "calibrator": calibrator, "calibrator_path": str(path)}


def calibrated_score(probability: float, verified_model: dict) -> float:
    """Apply temperature scaling to a probability using a verified calibrator."""
    if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("probability must be a finite number between zero and one.")
    calibrator = verified_model.get("calibrator") if isinstance(verified_model, dict) else None
    if not isinstance(calibrator, dict):
        raise ValueError("A verified calibrator is required to calculate calibrated scores.")
    temperature = calibrator.get("temperature")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("Calibrator temperature is invalid.")
    if probability in (0, 1):
        return float(probability)
    logit = math.log(probability / (1 - probability)) / temperature
    return 1 / (1 + math.exp(-logit))
