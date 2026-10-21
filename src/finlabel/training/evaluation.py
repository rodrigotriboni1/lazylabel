"""Local, hash-bound comparison of a base model and a PEFT candidate."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

from finlabel.labeling.suggestions import parse_suggestion
from finlabel.labeling.task import LabelTask
from finlabel.models.text_generation import TransformersTextGenerationBackend
from finlabel.training.backend import _json_object, _sha256
from finlabel.training.dataset import _prompt
from finlabel.training.split import TrainingBundle


PathLike = Union[str, Path]
MAX_NEW_TOKENS = 96
INVALID = "__invalid__"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_PROMPT_SUFFIX = "\nReturn one JSON object with a configured label and optional short rationale."
_SUGGESTION_ID = re.compile(r"[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class LabelMetrics:
    label: str
    support: int
    precision: Optional[float]
    recall: Optional[float]
    f1: Optional[float]
    model: str = "candidate"


@dataclass(frozen=True)
class EvaluationReport:
    base_model_ref: str
    adapter_path: Path
    adapter_sha256: str
    dataset_sha256: str
    split_sha256: str
    overall: Mapping[str, object]
    per_label: Sequence[LabelMetrics]
    confusion: Mapping[str, Mapping[str, Mapping[str, int]]]
    error_ids: Sequence[str]
    warnings: Sequence[str]


def _require_hash(value, name: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError("{} is missing or invalid.".format(name))
    return value


def _adapter_digest(directory: Path) -> str:
    weights = sorted(path for path in directory.rglob("*")
                     if path.is_file() and path.name.endswith((".safetensors", ".bin")))
    if not weights:
        raise ValueError("Candidate adapter has no local weight files.")
    digest = hashlib.sha256()
    for path in weights:
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


def _validate_bundle(bundle: TrainingBundle, task: LabelTask) -> tuple[dict, list[tuple[str, str]], tuple[str, ...]]:
    if not isinstance(bundle, TrainingBundle):
        raise TypeError("Evaluation requires a TrainingBundle.")
    manifest_path = Path(bundle.manifest_path).expanduser().resolve()
    directory = manifest_path.parent
    train_path, holdout_path = directory / "train.jsonl", directory / "holdout.jsonl"
    if (manifest_path.name != "manifest.json" or Path(bundle.train_path).expanduser().resolve() != train_path
            or Path(bundle.holdout_path).expanduser().resolve() != holdout_path):
        raise ValueError("Bundle paths do not match the manifest location.")
    manifest = _json_object(manifest_path, "bundle manifest")
    stable = {key: value for key, value in manifest.items()
              if key not in {"dataset_path", "dataset_manifest_path", "split_sha256"}}
    digest = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    if (manifest.get("split_sha256") != digest or bundle.split_sha256 != digest
            or manifest.get("task_id") != task.task_id):
        raise ValueError("Bundle split identity or task does not match.")
    if (manifest.get("train_count") != bundle.train_count or manifest.get("holdout_count") != bundle.holdout_count
            or not isinstance(bundle.holdout_count, int) or isinstance(bundle.holdout_count, bool)
            or bundle.holdout_count < 1):
        raise ValueError("Bundle partition counts do not match.")
    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("holdout"), dict):
        raise ValueError("Bundle holdout provenance is missing.")
    suggestion_ids = provenance["holdout"].get("suggestion_ids")
    if (not isinstance(suggestion_ids, list) or len(suggestion_ids) != bundle.holdout_count
            or any(not isinstance(item, str) or _SUGGESTION_ID.fullmatch(item) is None for item in suggestion_ids)
            or len(set(suggestion_ids)) != len(suggestion_ids)):
        raise ValueError("Bundle holdout suggestion IDs are invalid or do not match its count.")
    if (_sha256(train_path) != _require_hash(manifest.get("train_sha256"), "Train hash")
            or _sha256(holdout_path) != _require_hash(manifest.get("holdout_sha256"), "Holdout hash")):
        raise ValueError("Bundle partition hash mismatch.")
    dataset_hash = _require_hash(manifest.get("dataset_sha256"), "Dataset hash")
    dataset_path = Path(manifest.get("dataset_path", "")).expanduser().resolve()
    if not dataset_path.is_file() or _sha256(dataset_path) != dataset_hash:
        raise ValueError("Reviewed dataset hash mismatch.")
    dataset_manifest_path = dataset_path.with_suffix(dataset_path.suffix + ".manifest.json")
    dataset_manifest = _json_object(dataset_manifest_path, "dataset manifest")
    task_model_ref = task.model_id + ("@" + task.model_revision if task.model_revision else "")
    if (Path(manifest.get("dataset_manifest_path", "")).expanduser().resolve() != dataset_manifest_path
            or dataset_manifest.get("dataset_sha256") != dataset_hash
            or dataset_manifest.get("task_id") not in {None, task.task_id}
            or dataset_manifest.get("model_ref") not in {None, "", task_model_ref}):
        raise ValueError("Reviewed dataset manifest mismatch.")
    rows = []
    prompt_template = _prompt(task, {})
    prompt_prefix = prompt_template[:-len("{}" + _PROMPT_SUFFIX)]
    try:
        with holdout_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if not isinstance(row, dict) or set(row) != {"prompt", "completion"}:
                    raise ValueError("Invalid holdout row.")
                prompt, completion = row["prompt"], row["completion"]
                if not isinstance(prompt, str) or not isinstance(completion, str):
                    raise ValueError("Invalid holdout row.")
                if not prompt.startswith(prompt_prefix) or not prompt.endswith(_PROMPT_SUFFIX):
                    raise ValueError("Holdout prompt differs from the selected task schema.")
                selected = json.loads(prompt[len(prompt_prefix):-len(_PROMPT_SUFFIX)])
                if (not isinstance(selected, dict) or set(selected) != set(task.input_columns)
                        or prompt != _prompt(task, selected)):
                    raise ValueError("Holdout prompt differs from the selected task schema.")
                label, _ = parse_suggestion(completion, valid_labels=set(task.labels))
                rows.append((prompt, label))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not validate holdout rows.") from exc
    if len(rows) != bundle.holdout_count:
        raise ValueError("Holdout row count mismatch.")
    return manifest, rows, tuple(suggestion_ids)


def _candidate_metadata(adapter: Path, manifest: dict, task: LabelTask) -> tuple[str, str]:
    if not adapter.is_dir():
        raise ValueError("Candidate adapter directory is missing.")
    metadata = _json_object(adapter / "finlabel-training.json", "candidate metadata")
    model_ref = task.model_id + ("@" + task.model_revision if task.model_revision else "")
    if (metadata.get("base_model_ref") != model_ref or metadata.get("task_id") != task.task_id
            or metadata.get("dataset_sha256") != manifest["dataset_sha256"]
            or metadata.get("split_sha256") != manifest["split_sha256"]
            or metadata.get("train_sha256") != manifest.get("train_sha256")):
        raise ValueError("Candidate model, task or bundle identity is incompatible.")
    recorded = _require_hash(metadata.get("adapter_sha256"), "Candidate adapter hash")
    if _adapter_digest(adapter) != recorded:
        raise ValueError("Candidate adapter hash mismatch.")
    config_path = adapter / "adapter_config.json"
    if config_path.is_file():
        config = _json_object(config_path, "adapter config")
        configured_base = config.get("base_model_name_or_path")
        if configured_base and configured_base not in {task.model_id, model_ref}:
            raise ValueError("Adapter config base model is incompatible.")
    return model_ref, recorded


def _metrics(labels: Sequence[str], actual: Sequence[str], predicted: Sequence[str], model: str):
    if INVALID in labels:
        raise ValueError("The reserved invalid prediction marker cannot be a task label.")
    confusion = {label: {candidate: 0 for candidate in (*labels, INVALID)} for label in labels}
    for truth, guess in zip(actual, predicted):
        confusion[truth][guess] += 1
    per_label = []
    defined_f1 = []
    for label in labels:
        tp = confusion[label][label]
        support = sum(confusion[label].values())
        predicted_count = sum(confusion[truth][label] for truth in labels)
        precision = tp / predicted_count if predicted_count else None
        recall = tp / support if support else None
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else (0.0 if precision is not None and recall is not None else None)
        per_label.append(LabelMetrics(label, support, precision, recall, f1, model))
        if f1 is not None:
            defined_f1.append(f1)
    count = len(actual)
    overall = {"count": count, "correct": sum(truth == guess for truth, guess in zip(actual, predicted)),
               "invalid_count": predicted.count(INVALID),
               "accuracy": sum(truth == guess for truth, guess in zip(actual, predicted)) / count if count else None,
               "macro_f1": sum(defined_f1) / len(defined_f1) if len(defined_f1) == len(labels) else None}
    return overall, per_label, confusion


def _publish_report(report: EvaluationReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    payload["adapter_path"] = str(report.adapter_path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent,
                                         prefix=".finlabel-evaluation-", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def evaluate_candidate(bundle: TrainingBundle, task: LabelTask, adapter_path: PathLike, *,
                       output_path: PathLike) -> EvaluationReport:
    """Evaluate on one immutable holdout; invalid predictions remain in all denominators.

    Precision is undefined without predicted positives; recall is undefined without
    actual support. Macro-F1 is null if any configured class has undefined F1.
    """
    output = Path(output_path).expanduser()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Refusing to overwrite an existing evaluation report.")
    output = output.absolute()
    manifest, rows, suggestion_ids = _validate_bundle(bundle, task)
    adapter = Path(adapter_path).expanduser().resolve()
    base_ref, adapter_hash = _candidate_metadata(adapter, manifest, task)
    prompts = tuple(prompt for prompt, _ in rows)
    actual = tuple(label for _, label in rows)
    backends = {
        "base": TransformersTextGenerationBackend(task.model_id, task.model_revision),
        "candidate": TransformersTextGenerationBackend(task.model_id, task.model_revision, adapter_path=adapter),
    }
    overall, per_label, confusion = {}, [], {}
    errors = set()
    for model_name, backend in backends.items():
        predicted = []
        for index, prompt in enumerate(prompts):
            raw = backend.generate(prompt, max_new_tokens=MAX_NEW_TOKENS)
            try:
                label, _ = parse_suggestion(raw, valid_labels=set(task.labels))
            except ValueError:
                label = INVALID
                errors.add(index)
            predicted.append(label)
        overall[model_name], label_metrics, confusion[model_name] = _metrics(task.labels, actual, predicted, model_name)
        per_label.extend(label_metrics)
    error_ids = tuple(suggestion_ids[index] for index in sorted(errors))
    warnings = list(manifest.get("warnings", ()))
    if any(overall[model]["invalid_count"] for model in backends):
        warnings.append("Malformed or unknown predictions counted as incorrect; see invalid_count and confusion.")
    report = EvaluationReport(base_ref, adapter, adapter_hash, manifest["dataset_sha256"],
                              manifest["split_sha256"], overall, tuple(per_label), confusion,
                              error_ids, tuple(dict.fromkeys(warnings)))
    final_manifest, _, final_suggestion_ids = _validate_bundle(bundle, task)
    if (final_manifest != manifest or final_suggestion_ids != suggestion_ids
            or _candidate_metadata(adapter, final_manifest, task) != (base_ref, adapter_hash)):
        raise ValueError("Evaluation inputs changed during inference; no report was published.")
    _publish_report(report, output)
    return report
