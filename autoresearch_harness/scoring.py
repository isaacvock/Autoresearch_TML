from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from .folds import read_motifs, validate_dataset_manifest, validate_fold
from .io import atomic_write_json, read_json, sha256_file, utc_now


def _pearson(targets: np.ndarray, predictions: np.ndarray) -> float:
    if targets.size < 2 or predictions.size != targets.size:
        raise ValueError("Pearson correlation requires aligned vectors with at least two values")
    if not np.isfinite(targets).all() or not np.isfinite(predictions).all():
        raise ValueError("prediction inputs contain non-finite values")
    if float(np.std(targets)) == 0.0 or float(np.std(predictions)) == 0.0:
        raise ValueError("Pearson correlation is undefined for a constant vector")
    return float(np.corrcoef(targets, predictions)[0, 1])


def _read_predictions(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    indices: list[int] = []
    targets: list[float] = []
    predictions: list[float] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            indices.append(int(row["index"]))
            targets.append(float(row["target"]))
            predictions.append(float(row["prediction"]))
    return np.asarray(indices), np.asarray(targets), np.asarray(predictions)


def score_experiment(
    experiment_dir: str | Path,
    motifs_file: str | Path,
    *,
    expected_folds: int = 5,
    pearson_tolerance: float = 1e-4,
    motif_tolerance: float = 1e-6,
) -> dict[str, Any]:
    if expected_folds != 5:
        raise ValueError("campaign scoring requires exactly five folds")
    if float(pearson_tolerance) != 1e-4 or float(motif_tolerance) != 1e-6:
        raise ValueError("campaign Pareto tolerances are immutable")
    experiment = Path(experiment_dir).resolve()
    motifs = read_motifs(motifs_file)
    metadata = read_json(experiment / "experiment.json")
    if sha256_file(motifs_file) != metadata.get("motifs_sha256"):
        raise ValueError("motif definitions differ from the immutable experiment snapshot")
    validate_dataset_manifest(metadata.get("dataset"))
    fold_pearsons: list[float] = []
    all_indices: list[np.ndarray] = []
    all_targets: list[np.ndarray] = []
    all_predictions: list[np.ndarray] = []
    effects_by_motif: dict[str, list[np.ndarray]] = {label: [] for label, _ in motifs}
    instances_hashes: dict[str, set[str]] = {label: set() for label, _ in motifs}
    per_fold: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}

    for fold in range(expected_folds):
        validated = validate_fold(experiment, fold, motifs_file)
        prediction_path: Path = validated["paths"]["predictions"]
        indices, targets, predictions = _read_predictions(prediction_path)
        fold_pearsons.append(_pearson(targets, predictions))
        per_fold.append(
            {"fold": fold, "pearson": fold_pearsons[-1], "n_examples": int(indices.size)}
        )
        all_indices.append(indices)
        all_targets.append(targets)
        all_predictions.append(predictions)
        for artifact in (
            validated["manifest_path"],
            validated["paths"]["checkpoint"],
            validated["paths"]["predictions"],
            validated["paths"]["split"],
            validated["paths"]["train_config"],
        ):
            hashes[str(artifact.relative_to(experiment))] = sha256_file(artifact)
        for label, _ in motifs:
            effect_path: Path = validated["paths"]["motifs"][label]["effects"]
            effects = np.asarray(np.load(effect_path, allow_pickle=False), dtype=np.float64)
            effects_by_motif[label].append(effects)
            for artifact in validated["paths"]["motifs"][label].values():
                artifact_hash = sha256_file(artifact)
                hashes[str(artifact.relative_to(experiment))] = artifact_hash
                if artifact.name == "instances.csv":
                    instances_hashes[label].add(artifact_hash)

    inconsistent_instances = [label for label, values in instances_hashes.items() if len(values) != 1]
    if inconsistent_instances:
        raise ValueError(
            "motif instance populations differ across fold models: "
            + ", ".join(inconsistent_instances)
        )
    for label, fold_effects in effects_by_motif.items():
        if len({int(values.size) for values in fold_effects}) != 1:
            raise ValueError(f"motif effect counts differ across fold models: {label}")

    indices = np.concatenate(all_indices)
    if len(set(indices.tolist())) != int(indices.size):
        raise ValueError("out-of-fold predictions contain duplicate dataset indices")
    dataset_manifest = metadata.get("dataset")
    if dataset_manifest:
        dataset_targets = np.asarray(
            np.load(Path(dataset_manifest["path"]) / "y.npy", mmap_mode="r", allow_pickle=False)
        )
        if dataset_targets.ndim == 2 and dataset_targets.shape[1] == 1:
            dataset_targets = dataset_targets[:, 0]
        if dataset_targets.ndim != 1:
            raise ValueError("campaign scorer requires one scalar target per dataset example")
        expected_indices = np.arange(dataset_targets.size)
    else:
        dataset_targets = None
        expected_indices = np.arange(int(indices.max()) + 1) if indices.size else np.empty(0, dtype=int)
    if not np.array_equal(np.sort(indices), expected_indices):
        raise ValueError("out-of-fold predictions do not cover every dataset index exactly once")
    order = np.argsort(indices)
    targets = np.concatenate(all_targets)[order]
    predictions = np.concatenate(all_predictions)[order]
    if dataset_targets is not None and not np.allclose(
        targets, dataset_targets[indices[order]], rtol=1e-6, atol=1e-7, equal_nan=False
    ):
        raise ValueError("prediction CSV targets do not match the immutable dataset")
    pooled_pearson = _pearson(targets, predictions)

    motif_medians = {
        label: float(np.median(np.concatenate(fold_effects)))
        for label, fold_effects in effects_by_motif.items()
    }
    worst_label = max(motif_medians, key=motif_medians.__getitem__)
    near_zero_labels = sorted(
        label for label, value in motif_medians.items() if abs(value) <= float(motif_tolerance)
    )
    nonnegative_labels = sorted(label for label, value in motif_medians.items() if value >= 0.0)
    metrics = {
        "schema_version": 1,
        "experiment_id": metadata["experiment_id"],
        "scored_at": utc_now(),
        "valid": True,
        "validation_status": "validated",
        "performance_label": "adaptive_optimization_cv",
        "n_folds": expected_folds,
        "prediction": {
            "objective": "maximize",
            "metric": "pooled_out_of_fold_pearson",
            "pooled_pearson": pooled_pearson,
            "fold_pearsons": fold_pearsons,
            "fold_statistics": per_fold,
            "fold_mean": float(np.mean(fold_pearsons)),
            "fold_std": float(np.std(fold_pearsons)),
            "n_examples": int(indices.size),
            "tolerance": float(pearson_tolerance),
        },
        "motif_recovery": {
            "objective": "minimize",
            "effect_definition": "A - R",
            "population": "all_dataset_examples_for_each_fold_model",
            "motif_medians": motif_medians,
            "worst_motif": worst_label,
            "worst_motif_median": motif_medians[worst_label],
            "n_motifs_below_negative_tolerance": sum(
                value < -float(motif_tolerance) for value in motif_medians.values()
            ),
            "near_zero_motif_medians": near_zero_labels,
            "nonnegative_motif_medians": nonnegative_labels,
            "all_motif_medians_negative": not nonnegative_labels,
            "instances_per_model": {
                label: int(fold_effects[0].size)
                for label, fold_effects in effects_by_motif.items()
            },
            "numerical_zero_tolerance": float(motif_tolerance),
        },
        "artifact_sha256": dict(sorted(hashes.items())),
    }
    atomic_write_json(experiment / "metrics.json", metrics)
    return metrics
