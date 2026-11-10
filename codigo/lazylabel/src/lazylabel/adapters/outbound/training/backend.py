"""Explicit TRL SFT + PEFT/LoRA training, protected by a project gate."""

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union


PathLike = Union[str, Path]
GATE_FIELDS = ("model_id", "license", "hardware", "data_policy", "evaluation_protocol")


@dataclass(frozen=True)
class TrainingConfig:
    model_id: str
    model_revision: Optional[str]
    output_dir: Path
    epochs: int = 1
    batch_size: int = 1
    learning_rate: float = 0.0002
    lora_rank: int = 8
    seed: int = 42

    def __post_init__(self):
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be a non-empty string.")
        if self.model_revision is not None and not isinstance(self.model_revision, str):
            raise ValueError("model_revision must be a string when provided.")
        if isinstance(self.epochs, bool) or not isinstance(self.epochs, int) or not 1 <= self.epochs <= 100:
            raise ValueError("epochs must be an integer from 1 to 100.")
        if isinstance(self.batch_size, bool) or not isinstance(self.batch_size, int) or not 1 <= self.batch_size <= 1024:
            raise ValueError("batch_size must be an integer from 1 to 1024.")
        if isinstance(self.learning_rate, bool) or not isinstance(self.learning_rate, (int, float)) or not math.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("learning_rate must be a finite positive number.")
        if isinstance(self.lora_rank, bool) or not isinstance(self.lora_rank, int) or not 1 <= self.lora_rank <= 256:
            raise ValueError("lora_rank must be an integer from 1 to 256.")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer.")
        object.__setattr__(self, "output_dir", Path(self.output_dir).expanduser().resolve())


@dataclass(frozen=True)
class TrainingResult:
    output_dir: Path
    base_model_ref: str
    dataset_sha256: str
    adapter_files: Sequence[Path]
    final_metrics: Mapping[str, float]
    artifact_sha256: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


TRAINING_METADATA_NAMES = ("lazylabel-training.json", "finlabel-training.json")


def read_training_metadata(directory: Path) -> dict:
    """Adapter metadata; adapters trained before the rename carry the legacy file name."""
    for name in TRAINING_METADATA_NAMES:
        path = Path(directory) / name
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(Path(directory) / TRAINING_METADATA_NAMES[0])


def _artifact_tree_sha256(root: Path) -> str:
    """Hash adapter artifacts by relative path and content, excluding only root metadata."""
    entries = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()
                        and item.relative_to(root).as_posix() not in TRAINING_METADATA_NAMES),
                       key=lambda item: item.relative_to(root).as_posix()):
        entries.append({"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)})
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def format_training_example(row: Mapping, tokenizer) -> dict:
    """Format user input with the selected tokenizer while keeping its target separate."""
    if not isinstance(row, Mapping) or set(row) != {"prompt", "completion"}:
        raise ValueError("Training example must contain prompt and completion.")
    prompt, completion = row["prompt"], row["completion"]
    if not isinstance(prompt, str) or not prompt.strip() or not isinstance(completion, str) or not completion.strip():
        raise ValueError("Training prompt and completion must be non-empty strings.")
    if getattr(tokenizer, "chat_template", None):
        from lazylabel.adapters.outbound.models.text_generation import render_model_prompt
        prompt = render_model_prompt(prompt, tokenizer)
    return {"prompt": prompt, "completion": completion}


def validate_training_request(dataset_path: PathLike, config: TrainingConfig, *, gate_path: PathLike,
                              train_dataset_path: Optional[PathLike] = None,
                              trusted_dataset_manifest=None, expected_task_id: Optional[str] = None) -> dict:
    """Validate dataset and project authorization without importing ML libraries."""
    dataset = Path(dataset_path).expanduser().resolve()
    if config.output_dir.exists():
        raise FileExistsError("Refusing to overwrite training output: {}".format(config.output_dir))
    if not dataset.is_file():
        raise FileNotFoundError("Training dataset does not exist: {}".format(dataset))
    trusted_manifest_path = getattr(trusted_dataset_manifest, "manifest_path", None)
    if trusted_dataset_manifest is not None:
        if (trusted_manifest_path is None or not isinstance(getattr(trusted_dataset_manifest, "manifest_sha256", None), str)
                or not isinstance(getattr(trusted_dataset_manifest, "task_id", None), str)
                or not expected_task_id or trusted_dataset_manifest.task_id != expected_task_id):
            raise ValueError("Trusted training requires the prepared dataset object and its exact task identity.")
    manifest_path = (Path(trusted_manifest_path).expanduser().resolve() if trusted_manifest_path is not None
                     else dataset.with_suffix(dataset.suffix + ".manifest.json"))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Dataset manifest must be a JSON object.")
        row_count = 0
        with dataset.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict) or set(row) != {"prompt", "completion"}:
                    raise ValueError("Training rows must contain exactly prompt and completion fields.")
                if not isinstance(row["prompt"], str) or not row["prompt"].strip() or not isinstance(row["completion"], str) or not row["completion"].strip():
                    raise ValueError("Training prompt and completion must be non-empty strings (line {}).".format(line_number))
                row_count += 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not validate training dataset: {}".format(exc)) from exc
    if not row_count:
        raise ValueError("Training dataset must contain at least one example.")
    dataset_hash = _sha256(dataset)
    trusted = trusted_manifest_path is not None
    if trusted:
        manifest_digest = _sha256(manifest_path)
        if (manifest_digest != trusted_dataset_manifest.manifest_sha256
                or manifest.get("manifest_sha256") not in (None, manifest_digest)):
            raise ValueError("Trusted dataset manifest changed after preparation.")
        if manifest.get("kind") != "trusted_reference_dataset" or manifest.get("schema_version") != 1:
            raise ValueError("Trusted training requires a trusted-reference manifest.")
        partitions = manifest.get("partitions")
        train_partition = partitions.get("train") if isinstance(partitions, dict) else None
        if not isinstance(train_partition, dict):
            raise ValueError("Trusted manifest has no frozen train partition.")
        if (train_partition.get("path") != dataset.name or train_partition.get("dataset_sha256") != dataset_hash
                or train_partition.get("count") != row_count):
            raise ValueError("Training dataset does not match the trusted train partition in its manifest.")
        if (manifest.get("task_id") != expected_task_id
                or not isinstance(manifest.get("task_spec_sha256"), str)
                or manifest.get("task_spec_sha256") != getattr(trusted_dataset_manifest, "task_spec_sha256", None)):
            raise ValueError("Trusted training manifest is missing task identity.")
    elif manifest.get("dataset_sha256") != dataset_hash or manifest.get("row_count") != row_count:
        raise ValueError("Training dataset does not match its manifest hash or row count.")
    manifest_model = manifest.get("model_ref")
    if manifest_model and not trusted:
        manifest_model_id, separator, manifest_revision = manifest_model.partition("@")
        expected_revision = manifest_revision if separator else None
        if manifest_model_id != config.model_id:
            raise ValueError("Training model must match the model recorded in the reviewed dataset manifest.")
        if config.model_revision != expected_revision:
            raise ValueError("Training model revision must match the revision recorded in the reviewed dataset manifest.")
    gate_file = Path(gate_path).expanduser()
    try:
        gate = json.loads(gate_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("training gate is not configured at {}: {}".format(gate_file, exc)) from exc
    if not isinstance(gate, dict) or gate.get("authorized") is not True:
        raise ValueError("Training gate requires explicit project authorization.")
    missing = [name for name in GATE_FIELDS if not isinstance(gate.get(name), str) or not gate[name].strip()]
    if missing:
        raise ValueError("Training gate is missing: {}".format(", ".join(missing)))
    if gate["model_id"] != config.model_id:
        raise ValueError("Training model does not match the project gate model_id.")
    train_dataset = Path(train_dataset_path).expanduser().resolve() if train_dataset_path is not None else dataset
    if train_dataset != dataset:
        if not train_dataset.is_file():
            raise FileNotFoundError("Train partition does not exist: {}".format(train_dataset))
        train_count = 0
        with train_dataset.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict) or set(row) != {"prompt", "completion"}:
                    raise ValueError("Train partition rows must contain exactly prompt and completion fields.")
                if not all(isinstance(row.get(key), str) and row[key].strip() for key in ("prompt", "completion")):
                    raise ValueError("Train partition contains an empty prompt or completion (line {}).".format(line_number))
                train_count += 1
        expected = manifest.get("partitions", {}).get("train", {}) if not trusted else {}
        if not train_count or train_count != expected.get("count") or _sha256(train_dataset) != expected.get("dataset_sha256"):
            raise ValueError("Train partition no longer matches its trusted frozen manifest.")
    elif trusted:
        if train_dataset != dataset:
            raise ValueError("Trusted train path is inconsistent.")
    return {"manifest": manifest, "dataset_sha256": dataset_hash, "row_count": row_count,
            "dataset_path": dataset, "train_dataset_path": train_dataset, "gate": gate}


def train_adapter(dataset_path: PathLike, config: TrainingConfig, *, gate_path: PathLike,
                  train_dataset_path: Optional[PathLike] = None,
                  trusted_dataset_manifest=None, expected_task_id: Optional[str] = None) -> TrainingResult:
    validated = validate_training_request(dataset_path, config, gate_path=gate_path,
                                          train_dataset_path=train_dataset_path,
                                          trusted_dataset_manifest=trusted_dataset_manifest,
                                          expected_task_id=expected_task_id)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    try:
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise RuntimeError("Install lazylabel[train] to use PEFT/LoRA training.") from exc

    output_parent = config.output_dir.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".lazylabel-adapter-", dir=str(output_parent)))
    try:
        tokenizer = AutoTokenizer.from_pretrained(config.model_id, revision=config.model_revision, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(config.model_id, revision=config.model_revision, trust_remote_code=False)
        # The orchestration layer may provide an immutable trusted train-only partition.
        # Ordinary reviewed datasets retain their existing single-file behavior.
        train_path = validated.get("train_dataset_path", validated["dataset_path"])
        examples = load_dataset("json", data_files={"train": str(train_path)}, split="train")
        examples = examples.map(lambda row: format_training_example(row, tokenizer))
        trainer = SFTTrainer(
            model=model,
            args=SFTConfig(
                output_dir=str(staging), num_train_epochs=config.epochs,
                per_device_train_batch_size=config.batch_size, learning_rate=config.learning_rate,
                seed=config.seed, report_to="none", push_to_hub=False,
                completion_only_loss=True, save_strategy="no",
            ),
            train_dataset=examples,
            processing_class=tokenizer,
            peft_config=LoraConfig(r=config.lora_rank, target_modules="all-linear", task_type="CAUSAL_LM"),
        )
        trainer.train()
        trainer.model.save_pretrained(str(staging))
        tokenizer.save_pretrained(str(staging))
        trainer_state = getattr(getattr(trainer, "state", None), "log_history", []) or []
        metrics = {key: float(value) for item in trainer_state[-1:] for key, value in item.items()
                   if isinstance(value, (int, float)) and not isinstance(value, bool)}
        try:
            trl_version = version("trl")
            peft_version = version("peft")
            transformers_version = version("transformers")
            datasets_version = version("datasets")
            accelerate_version = version("accelerate")
            torch_version = version("torch")
        except PackageNotFoundError:
            trl_version = peft_version = transformers_version = datasets_version = accelerate_version = torch_version = "unknown"
        metadata = {
            "base_model_ref": config.model_id + ("@" + config.model_revision if config.model_revision else ""),
            "generation": {"do_sample": False, "max_new_tokens": 256,
                           "raw_score_method": "label_json_mean_log_likelihood_v2"},
            "task_id": validated["manifest"].get("task_id"),
            "dataset_sha256": validated["dataset_sha256"],
            "parameters": {"epochs": config.epochs, "batch_size": config.batch_size,
                           "learning_rate": config.learning_rate, "lora_rank": config.lora_rank, "seed": config.seed},
            "packages": {"trl": trl_version, "peft": peft_version, "transformers": transformers_version,
                         "datasets": datasets_version, "accelerate": accelerate_version, "torch": torch_version},
            "final_metrics": metrics,
            "adapter_artifacts_sha256": _artifact_tree_sha256(staging),
            "telemetry": "disabled",
            "hub_upload": False,
        }
        (staging / "lazylabel-training.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if config.output_dir.exists():
            raise FileExistsError("Refusing to overwrite training output: {}".format(config.output_dir))
        os.replace(staging, config.output_dir)
        directory_fd = os.open(output_parent, os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    except BaseException:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        raise
    adapter_files = tuple(path for path in config.output_dir.rglob("*") if path.is_file())
    return TrainingResult(config.output_dir, metadata["base_model_ref"], validated["dataset_sha256"],
                          adapter_files, metrics, metadata["adapter_artifacts_sha256"])
