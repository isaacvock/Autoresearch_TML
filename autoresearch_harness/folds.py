from __future__ import annotations

import csv
import importlib.metadata
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

from .io import atomic_write_json, read_json, sha256_file, utc_now, validate_experiment_id


EXPECTED_MOTIFS = (
    ("PRE", "UGUA[A|U|C]AUA"),
    ("ARE_heptamer", "UAUUUAU"),
    ("let7_7mer_m8", "CUACCUC"),
    ("miR16_7mer_m8", "UGCUGCU"),
    ("GRE", "UGUUUGUUUGU"),
    ("mir19_7mer_m8", "UUUGCAC"),
    ("mir17_7mer_m8", "GCACUUU"),
    ("mir29_7mer_m8", "UGGUGCU"),
    ("mir130_7mer_m8", "UGCACUA"),
)


def read_motifs(path: str | Path) -> list[tuple[str, str]]:
    motifs: list[tuple[str, str]] = []
    labels: set[str] = set()
    sequences: set[str] = set()
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) != 2 or not all(fields):
                raise ValueError(f"{path}:{line_number}: expected LABEL<TAB>MOTIF")
            label, motif = fields
            if label in labels:
                raise ValueError(f"duplicate motif label: {label}")
            if motif in sequences:
                raise ValueError(f"duplicate motif sequence: {motif}")
            labels.add(label)
            sequences.add(motif)
            motifs.append((label, motif))
    if not motifs:
        raise ValueError(f"no motifs found in {path}")
    if tuple(motifs) != EXPECTED_MOTIFS:
        raise ValueError(
            "motif specification differs from the immutable nine-motif campaign definition"
        )
    return motifs


def config_model(path: str | Path) -> str:
    config = read_json(path)
    try:
        model = str(config["model"]["name"]).strip()
    except (KeyError, TypeError) as exc:
        raise ValueError(f"training config has no model.name: {path}") from exc
    if not model:
        raise ValueError(f"training config has an empty model.name: {path}")
    return model


def _dataset_manifest(path: str | Path) -> dict[str, Any]:
    dataset = Path(path).resolve()
    required = ("X.npy", "y.npy", "ids.txt", "config.json", "schema.json", "metadata.json")
    missing = [name for name in required if not (dataset / name).is_file()]
    if missing:
        raise FileNotFoundError(f"dataset is missing required files: {', '.join(missing)}")
    return {
        "path": str(dataset),
        "files": {
            name: {"bytes": (dataset / name).stat().st_size, "sha256": sha256_file(dataset / name)}
            for name in required
        },
    }


def validate_dataset_manifest(manifest: dict[str, Any] | None) -> None:
    if not manifest:
        return
    dataset = Path(manifest["path"])
    for name, expected in manifest["files"].items():
        artifact = dataset / name
        if not artifact.is_file() or artifact.stat().st_size != int(expected["bytes"]):
            raise ValueError(f"campaign dataset artifact changed: {artifact}")
        if sha256_file(artifact) != expected["sha256"]:
            raise ValueError(f"campaign dataset artifact changed: {artifact}")


def prepare_experiment(
    root: str | Path,
    experiment_id: str,
    base_config: str | Path,
    runs_root: str | Path | None = None,
    dataset_dir: str | Path | None = None,
) -> Path:
    root_path = Path(root).resolve()
    experiment_id = validate_experiment_id(experiment_id)
    source = Path(base_config).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    source_config = read_json(source)
    if int(source_config.get("seed", -1)) != 42:
        raise ValueError("training seed is immutable and must equal 42")
    config_model(source)
    runs_path = Path(runs_root).resolve() if runs_root is not None else root_path / "runs"
    experiment = runs_path / experiment_id
    snapshot = experiment / "config" / "train_config.json"
    experiment.mkdir(parents=True, exist_ok=True)
    payload = source.read_bytes()
    if snapshot.exists():
        if snapshot.read_bytes() != payload:
            raise ValueError(f"experiment {experiment_id} already has a different config snapshot")
    else:
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporary = snapshot.with_name(f".{snapshot.name}.tmp")
        temporary.write_bytes(payload)
        temporary.replace(snapshot)
    metadata_path = experiment / "experiment.json"
    if not metadata_path.exists():
        try:
            transcriptml_version = importlib.metadata.version("transcriptml")
        except importlib.metadata.PackageNotFoundError:
            transcriptml_version = "unknown"
        motifs_path = root_path / "workflow" / "motifs.tsv"
        atomic_write_json(
            metadata_path,
            {
                "schema_version": 1,
                "experiment_id": experiment_id,
                "created_at": utc_now(),
                "config_sha256": sha256_file(snapshot),
                "source_config": str(source),
                "performance_label": "adaptive_optimization_cv",
                "n_folds": 5,
                "eval_split": "test",
                "seeds": {
                    "cv": 10141996,
                    "training_base": 42,
                    "training_by_fold": [42 + fold for fold in range(5)],
                    "motif_ablation": 42,
                },
                "motifs_sha256": sha256_file(motifs_path) if motifs_path.is_file() else None,
                "transcriptml": {
                    "version": transcriptml_version,
                    "executable": shutil.which("transcriptml"),
                    "python": sys.executable,
                },
                "dataset": _dataset_manifest(dataset_dir) if dataset_dir is not None else None,
            },
        )
    elif dataset_dir is not None:
        existing_dataset = read_json(metadata_path).get("dataset")
        if existing_dataset and Path(existing_dataset["path"]).resolve() != Path(dataset_dir).resolve():
            raise ValueError(f"experiment {experiment_id} was prepared with a different dataset")
    return experiment


def _artifact_paths(attempt_dir: Path, fold: int, motifs: list[tuple[str, str]], eval_split: str) -> dict[str, Any]:
    fold_root = attempt_dir / "cv" / f"fold{fold}"
    motif_root = attempt_dir / "interpret" / "motif_ablation"
    return {
        "checkpoint": fold_root / "model" / "best.pt",
        "predictions": fold_root / "eval" / f"{eval_split}_predictions.csv",
        "split": fold_root / "dataset" / "splits.json",
        "train_config": fold_root / "train_config.json",
        "motifs": {
            label: {
                "effects": motif_root / label / "effects.npy",
                "summary": motif_root / label / "summary.json",
                "instances": motif_root / label / "instances.csv",
            }
            for label, _ in motifs
        },
    }


def validate_attempt(
    attempt_dir: str | Path,
    fold: int,
    motifs: list[tuple[str, str]],
    eval_split: str = "test",
) -> dict[str, Any]:
    attempt = Path(attempt_dir).resolve()
    paths = _artifact_paths(attempt, fold, motifs, eval_split)
    for name in ("checkpoint", "predictions", "split", "train_config"):
        path = paths[name]
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"missing or empty {name}: {path}")
    with paths["predictions"].open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"index", "id", "prediction", "target"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"prediction CSV lacks {sorted(required)}: {paths['predictions']}")
        prediction_indices = [int(row["index"]) for row in reader]
        if not prediction_indices:
            raise ValueError(f"prediction CSV is empty: {paths['predictions']}")
    split = read_json(paths["split"])
    expected_indices = [int(value) for value in split.get(eval_split, [])]
    if sorted(prediction_indices) != sorted(expected_indices):
        raise ValueError(
            f"prediction indices do not match the {eval_split!r} split: {paths['predictions']}"
        )
    if len(prediction_indices) != len(set(prediction_indices)):
        raise ValueError(f"prediction CSV contains duplicate indices: {paths['predictions']}")
    for label, _ in motifs:
        motif_paths = paths["motifs"][label]
        for name, path in motif_paths.items():
            if not path.is_file() or path.stat().st_size == 0:
                raise FileNotFoundError(f"missing or empty {label} {name}: {path}")
        summary = read_json(motif_paths["summary"])
        if summary.get("analysis") != "motif_ablation" or summary.get("effect_definition") != "A - R":
            raise ValueError(f"unexpected motif summary for {label}: {summary}")
        effects = np.load(motif_paths["effects"], mmap_mode="r", allow_pickle=False)
        if effects.ndim != 1 or effects.size == 0:
            raise ValueError(f"{label} effects must be a nonempty vector")
        if int(summary.get("n_instances", -1)) != int(effects.size):
            raise ValueError(f"{label} summary/effect count mismatch")
        if not np.isfinite(effects).all():
            raise ValueError(f"{label} effects contain non-finite values")
    return paths


def _validate_fold_config(experiment: Path, paths: dict[str, Any], fold: int) -> None:
    expected = read_json(experiment / "config" / "train_config.json")
    actual = read_json(paths["train_config"])
    for key in ("dataset", "output_dir"):
        expected.pop(key, None)
        actual.pop(key, None)

    # TranscriptML's CV preparation deterministically derives a distinct
    # training seed for each fold from the candidate's base seed. Normalize
    # that expected transformation before comparing the rest of the config.
    base_seed = expected.get("seed")
    actual_seed = actual.get("seed")
    if not isinstance(base_seed, int) or isinstance(base_seed, bool):
        raise ValueError("immutable experiment snapshot has no integer training seed")
    expected_fold_seed = base_seed + int(fold)
    if actual_seed != expected_fold_seed:
        raise ValueError(
            f"fold{fold} training seed is {actual_seed!r}; expected "
            f"base seed {base_seed} + fold {fold} = {expected_fold_seed}"
        )
    actual["seed"] = base_seed

    if actual != expected:
        changed = sorted(
            key for key in set(expected) | set(actual) if expected.get(key) != actual.get(key)
        )
        raise ValueError(
            "fold training parameters differ from the immutable experiment snapshot: "
            + ", ".join(changed)
        )


def complete_fold(
    experiment_dir: str | Path,
    attempt_dir: str | Path,
    fold: int,
    motifs_file: str | Path,
    eval_split: str = "test",
) -> Path:
    experiment = Path(experiment_dir).resolve()
    attempt = Path(attempt_dir).resolve()
    try:
        relative_attempt = attempt.relative_to(experiment)
    except ValueError as exc:
        raise ValueError("attempt directory must be inside the experiment directory") from exc
    motifs = read_motifs(motifs_file)
    paths = validate_attempt(attempt, fold, motifs, eval_split)
    _validate_fold_config(experiment, paths, fold)
    manifest = {
        "schema_version": 1,
        "fold": int(fold),
        "status": "complete",
        "completed_at": utc_now(),
        "attempt_dir": relative_attempt.as_posix(),
        "eval_split": eval_split,
        "config_sha256": sha256_file(paths["train_config"]),
        "prediction_sha256": sha256_file(paths["predictions"]),
        "motif_labels": [label for label, _ in motifs],
    }
    destination = experiment / "folds" / f"fold{fold}.json"
    if destination.exists() and read_json(destination).get("status") == "complete":
        validate_fold(experiment, fold, motifs_file)
        return destination
    return atomic_write_json(destination, manifest)


def validate_fold(experiment_dir: str | Path, fold: int, motifs_file: str | Path) -> dict[str, Any]:
    experiment = Path(experiment_dir).resolve()
    manifest_path = experiment / "folds" / f"fold{fold}.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = read_json(manifest_path)
    if manifest.get("status") != "complete" or int(manifest.get("fold", -1)) != int(fold):
        raise ValueError(f"invalid fold manifest: {manifest_path}")
    attempt = (experiment / manifest["attempt_dir"]).resolve()
    try:
        attempt.relative_to(experiment)
    except ValueError as exc:
        raise ValueError(f"fold manifest escapes experiment directory: {manifest_path}") from exc
    paths = validate_attempt(attempt, fold, read_motifs(motifs_file), manifest.get("eval_split", "test"))
    _validate_fold_config(experiment, paths, fold)
    return {"manifest": manifest, "manifest_path": manifest_path, "attempt_dir": attempt, "paths": paths}


def fail_fold(experiment_dir: str | Path, attempt_dir: str | Path, fold: int, exit_code: int) -> Path:
    experiment = Path(experiment_dir).resolve()
    attempt = Path(attempt_dir).resolve()
    attempt.relative_to(experiment)
    return atomic_write_json(
        attempt / "failure.json",
        {"schema_version": 1, "fold": int(fold), "exit_code": int(exit_code), "failed_at": utc_now()},
    )
