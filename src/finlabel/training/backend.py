"""Explicit TRL SFT + PEFT/LoRA training, protected by a project gate."""

import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

from finlabel.project import load_project
from finlabel.training.quality import inspect_training_dataset
from finlabel.training.split import TrainingBundle


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
    adapter_sha256: str
    split_sha256: str
    adapter_files: Sequence[Path]
    final_metrics: Mapping[str, float]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_object(path: Path, description: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read {}: {}".format(description, exc)) from exc
    if not isinstance(value, dict):
        raise ValueError("{} must be a JSON object.".format(description))
    return value


def load_training_bundle(bundle_dir: PathLike) -> TrainingBundle:
    """Load the bundle identity from its local manifest, without reading holdout rows."""
    from finlabel.training.quality import DatasetQualityReport

    directory = Path(bundle_dir).expanduser().resolve()
    manifest_path = directory / "manifest.json"
    manifest = _json_object(manifest_path, "bundle manifest")
    report = manifest.get("quality_report")
    if not isinstance(report, dict):
        raise ValueError("Bundle manifest is missing its quality report.")
    try:
        quality = DatasetQualityReport(**report)
        return TrainingBundle(directory / "train.jsonl", directory / "holdout.jsonl", manifest_path,
                              quality, manifest["train_count"], manifest["holdout_count"],
                              manifest["split_sha256"], manifest["warnings"])
    except (KeyError, TypeError) as exc:
        raise ValueError("Bundle manifest has invalid bundle fields.") from exc


def _validate_train_rows(path: Path, expected_count: int) -> None:
    if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 1:
        raise ValueError("Training partition count must be positive.")
    count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                row = json.loads(line)
                if not isinstance(row, dict) or set(row) != {"prompt", "completion"} or any(
                    not isinstance(row[key], str) or not row[key].strip() for key in ("prompt", "completion")
                ):
                    raise ValueError("Invalid training row at line {}.".format(line_number))
                count += 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not validate training partition: {}".format(exc)) from exc
    if count != expected_count:
        raise ValueError("Training partition row count does not match bundle manifest.")


def format_training_example(row: Mapping, tokenizer) -> dict:
    """Render the prompt with the model chat template while keeping target separate."""
    if not isinstance(row, Mapping) or set(row) != {"prompt", "completion"}:
        raise ValueError("Training example must contain prompt and completion.")
    prompt, completion = row["prompt"], row["completion"]
    if not isinstance(prompt, str) or not prompt.strip() or not isinstance(completion, str) or not completion.strip():
        raise ValueError("Training prompt and completion must be non-empty strings.")
    if getattr(tokenizer, "chat_template", None):
        rendered = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True
        )
    else:
        rendered = prompt
    return {"prompt": rendered, "completion": completion}


def validate_training_request(bundle: TrainingBundle, config: TrainingConfig, *, gate_path: PathLike,
                              exploratory_confirmed: bool = False) -> dict:
    """Recheck source, split, quality and authorization before optional ML imports."""
    if not isinstance(bundle, TrainingBundle):
        raise TypeError("Training requires a TrainingBundle, never a raw dataset path.")
    if config.output_dir.exists() or config.output_dir.is_symlink():
        raise FileExistsError("Refusing to overwrite training output: {}".format(config.output_dir))
    manifest_path = Path(bundle.manifest_path).expanduser().resolve()
    directory = manifest_path.parent
    train_path, holdout_path = directory / "train.jsonl", directory / "holdout.jsonl"
    if manifest_path.name != "manifest.json" or Path(bundle.train_path).expanduser().resolve() != train_path or Path(bundle.holdout_path).expanduser().resolve() != holdout_path:
        raise ValueError("Bundle paths do not match the bundle manifest location.")
    manifest = _json_object(manifest_path, "bundle manifest")
    stable = {key: value for key, value in manifest.items() if key not in {"dataset_path", "dataset_manifest_path", "split_sha256"}}
    split_hash = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if manifest.get("split_sha256") != split_hash or bundle.split_sha256 != split_hash:
        raise ValueError("Bundle manifest split hash does not match its contents.")
    if bundle.train_count != manifest.get("train_count") or bundle.holdout_count != manifest.get("holdout_count"):
        raise ValueError("Bundle partition counts do not match its manifest.")
    if isinstance(bundle.holdout_count, bool) or not isinstance(bundle.holdout_count, int) or bundle.holdout_count < 1:
        raise ValueError("Holdout partition count must be positive.")
    if not train_path.is_file() or not holdout_path.is_file():
        raise FileNotFoundError("Bundle train or holdout partition is missing.")
    if _sha256(train_path) != manifest.get("train_sha256") or _sha256(holdout_path) != manifest.get("holdout_sha256"):
        raise ValueError("Bundle partition hash does not match its manifest.")
    _validate_train_rows(train_path, bundle.train_count)
    dataset = Path(manifest.get("dataset_path", "")).expanduser().resolve()
    if not dataset.is_file() or _sha256(dataset) != manifest.get("dataset_sha256"):
        raise ValueError("Reviewed dataset hash does not match the bundle manifest.")
    dataset_manifest_path = dataset.with_suffix(dataset.suffix + ".manifest.json")
    if Path(manifest.get("dataset_manifest_path", "")).expanduser().resolve() != dataset_manifest_path:
        raise ValueError("Dataset manifest path does not match the bundle manifest.")
    dataset_manifest = _json_object(dataset_manifest_path, "dataset manifest")
    if dataset_manifest.get("dataset_sha256") != manifest.get("dataset_sha256") or dataset_manifest.get("task_id") != manifest.get("task_id") or dataset_manifest.get("run_id") != manifest.get("run_id"):
        raise ValueError("Reviewed dataset manifest does not match the bundle.")
    gate_file = Path(gate_path).expanduser().resolve()
    project = load_project(gate_file.parent / "project.json")
    report = inspect_training_dataset(project, dataset)
    if not report.ready or report.blockers:
        raise ValueError("Dataset quality gate blocked training: {}".format("; ".join(report.blockers)))
    report_json = json.loads(json.dumps(asdict(report), ensure_ascii=False))
    bundle_report_json = json.loads(json.dumps(asdict(bundle.quality_report), ensure_ascii=False))
    if report_json != manifest.get("quality_report") or report_json != bundle_report_json:
        raise ValueError("Stored quality report no longer matches the current dataset and source.")
    warnings = manifest.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings) or list(bundle.warnings) != warnings:
        raise ValueError("Bundle warnings do not match its manifest.")
    if not set(report.warnings).issubset(warnings):
        raise ValueError("Bundle omitted quality warnings.")
    if warnings and exploratory_confirmed is not True:
        raise ValueError("Bundle has quality/split warnings; pass --confirm-exploratory after reviewing them.")
    manifest_model = dataset_manifest.get("model_ref")
    if manifest_model:
        if not isinstance(manifest_model, str):
            raise ValueError("Reviewed dataset model reference is invalid.")
        manifest_model_id, separator, manifest_revision = manifest_model.partition("@")
        expected_revision = manifest_revision if separator else None
        if manifest_model_id != config.model_id:
            raise ValueError("Training model must match the model recorded in the reviewed dataset manifest.")
        if config.model_revision != expected_revision:
            raise ValueError("Training model revision must match the revision recorded in the reviewed dataset manifest.")
    gate = _json_object(gate_file, "training gate")
    if not isinstance(gate, dict) or gate.get("authorized") is not True:
        raise ValueError("Training gate requires explicit project authorization.")
    missing = [name for name in GATE_FIELDS if not isinstance(gate.get(name), str) or not gate[name].strip()]
    if missing:
        raise ValueError("Training gate is missing: {}".format(", ".join(missing)))
    if gate["model_id"] != config.model_id:
        raise ValueError("Training model does not match the project gate model_id.")
    return {"manifest": manifest, "dataset_sha256": manifest["dataset_sha256"], "split_sha256": split_hash,
            "train_path": train_path, "gate": gate}


def train_adapter(bundle: TrainingBundle, config: TrainingConfig, *, gate_path: PathLike,
                  exploratory_confirmed: bool = False) -> TrainingResult:
    validated = validate_training_request(bundle, config, gate_path=gate_path,
                                          exploratory_confirmed=exploratory_confirmed)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    try:
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise RuntimeError("Install finlabel-local[train] to use PEFT/LoRA training.") from exc

    output_parent = config.output_dir.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(exist_ok=False)
    staging = Path(tempfile.mkdtemp(prefix=".finlabel-adapter-", dir=str(output_parent)))
    snapshot_dir = None
    try:
        snapshot_dir = Path(tempfile.mkdtemp(prefix=".finlabel-train-snapshot-", dir=str(output_parent)))
        snapshot_path = snapshot_dir / "train.jsonl"
        shutil.copyfile(validated["train_path"], snapshot_path)
        if _sha256(snapshot_path) != validated["manifest"]["train_sha256"]:
            raise ValueError("Training partition changed while creating its private snapshot.")
        tokenizer = AutoTokenizer.from_pretrained(config.model_id, revision=config.model_revision, trust_remote_code=False, local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(config.model_id, revision=config.model_revision, trust_remote_code=False, local_files_only=True)
        examples = load_dataset("json", data_files={"train": str(snapshot_path)}, split="train")
        examples = examples.map(lambda row: format_training_example(row, tokenizer))
        if _sha256(snapshot_path) != validated["manifest"]["train_sha256"]:
            raise ValueError("Private training snapshot changed while loading examples.")
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
        def package_version(package: str) -> str:
            try:
                return version(package)
            except PackageNotFoundError:
                return "unknown"
        adapter_weights = sorted(path for path in staging.rglob("*") if path.is_file() and path.name.endswith((".safetensors", ".bin")))
        if not adapter_weights:
            raise ValueError("Trainer did not save adapter weights.")
        adapter_digest = hashlib.sha256()
        for path in adapter_weights:
            adapter_digest.update(path.relative_to(staging).as_posix().encode("utf-8"))
            adapter_digest.update(bytes.fromhex(_sha256(path)))
        adapter_sha256 = adapter_digest.hexdigest()
        from finlabel.training.active_model import tokenizer_sha256
        metadata = {
            "base_model_ref": config.model_id + ("@" + config.model_revision if config.model_revision else ""),
            "task_id": validated["manifest"].get("task_id"),
            "dataset_sha256": validated["dataset_sha256"],
            "split_sha256": validated["split_sha256"],
            "train_sha256": validated["manifest"]["train_sha256"],
            "adapter_sha256": adapter_sha256,
            "tokenizer_sha256": tokenizer_sha256(staging),
            "generation": {"do_sample": False, "max_new_tokens": 256},
            "parameters": {"epochs": config.epochs, "batch_size": config.batch_size,
                           "learning_rate": config.learning_rate, "lora_rank": config.lora_rank, "seed": config.seed},
            "packages": {name: package_version(name) for name in ("trl", "peft", "transformers", "datasets", "accelerate", "torch")},
            "final_metrics": metrics,
            "telemetry": "disabled",
            "hub_upload": False,
        }
        (staging / "finlabel-training.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for path in staging.iterdir():
            os.replace(path, config.output_dir / path.name)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(config.output_dir, ignore_errors=True)
        raise
    finally:
        if snapshot_dir is not None:
            shutil.rmtree(snapshot_dir, ignore_errors=True)
    shutil.rmtree(staging)
    adapter_files = tuple(path for path in config.output_dir.rglob("*") if path.is_file())
    return TrainingResult(config.output_dir, metadata["base_model_ref"], validated["dataset_sha256"],
                          adapter_sha256, validated["split_sha256"], adapter_files, metrics)
