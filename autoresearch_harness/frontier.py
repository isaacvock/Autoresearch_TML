from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import append_jsonl, atomic_write_json, exclusive_lock, load_jsonl, read_json, utc_now


def _scores(record: dict[str, Any]) -> tuple[float, float]:
    metrics = record["metrics"]
    return (
        float(metrics["prediction"]["pooled_pearson"]),
        float(metrics["motif_recovery"]["worst_motif_median"]),
    )


def dominates(
    candidate: dict[str, Any],
    other: dict[str, Any],
    *,
    pearson_tolerance: float = 1e-4,
    motif_tolerance: float = 1e-6,
) -> bool:
    candidate_pearson, candidate_motif = _scores(candidate)
    other_pearson, other_motif = _scores(other)
    nonworse = (
        candidate_pearson >= other_pearson - pearson_tolerance
        and candidate_motif <= other_motif + motif_tolerance
    )
    strictly_better = (
        candidate_pearson > other_pearson + pearson_tolerance
        or candidate_motif < other_motif - motif_tolerance
    )
    return bool(nonworse and strictly_better)


def compute_frontier(
    records: list[dict[str, Any]],
    *,
    pearson_tolerance: float = 1e-4,
    motif_tolerance: float = 1e-6,
) -> list[dict[str, Any]]:
    scored = [row for row in records if row.get("status") == "scored" and row.get("metrics", {}).get("valid")]
    return [
        row
        for row in scored
        if not any(
            other is not row
            and dominates(
                other,
                row,
                pearson_tolerance=pearson_tolerance,
                motif_tolerance=motif_tolerance,
            )
            for other in scored
        )
    ]


def update_frontier(
    ledger_path: str | Path,
    output_path: str | Path,
    *,
    pearson_tolerance: float = 1e-4,
    motif_tolerance: float = 1e-6,
) -> dict[str, Any]:
    rows = load_jsonl(ledger_path)
    frontier = compute_frontier(
        rows,
        pearson_tolerance=pearson_tolerance,
        motif_tolerance=motif_tolerance,
    )
    payload = {
        "schema_version": 1,
        "updated_at": utc_now(),
        "pearson_tolerance": pearson_tolerance,
        "motif_tolerance": motif_tolerance,
        "experiments": [
            {
                "experiment_id": row["experiment_id"],
                "candidate_commit": row.get("candidate_commit"),
                "hypothesis": row.get("hypothesis"),
                "pooled_pearson": _scores(row)[0],
                "worst_motif_median": _scores(row)[1],
            }
            for row in frontier
        ],
    }
    atomic_write_json(output_path, payload)
    return payload


def record_scored_experiment(
    root: str | Path,
    experiment_id: str,
    runs_root: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    with exclusive_lock(root_path / "runtime" / "ledger.lock"):
        return _record_scored_experiment(root_path, experiment_id, runs_root)


def _record_scored_experiment(
    root: Path,
    experiment_id: str,
    runs_root: str | Path | None,
) -> dict[str, Any]:
    root_path = root.resolve()
    runtime = root_path / "runtime"
    ledger = runtime / "experiments.jsonl"
    existing = load_jsonl(ledger)
    for row in existing:
        if row.get("experiment_id") == experiment_id and row.get("status") == "scored":
            return row
    runs_path = Path(runs_root).resolve() if runs_root is not None else root_path / "runs"
    experiment = runs_path / experiment_id
    metadata = read_json(experiment / "experiment.json")
    metrics = read_json(experiment / "metrics.json")
    proposal_path = experiment / "proposal.json"
    proposal = read_json(proposal_path) if proposal_path.exists() else {}
    submission_path = experiment / "submission.json"
    submission = read_json(submission_path) if submission_path.exists() else {}
    failures = [
        read_json(path)
        for path in sorted((experiment / "attempts").glob("fold*/*/failure.json"))
    ] if (experiment / "attempts").exists() else []
    record = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "status": "scored",
        "recorded_at": utc_now(),
        "candidate_commit": proposal.get("candidate_commit"),
        "parent_commit": proposal.get("parent_commit"),
        "hypothesis": proposal.get("hypothesis"),
        "config_sha256": metadata.get("config_sha256"),
        "seeds": metadata.get("seeds"),
        "transcriptml": metadata.get("transcriptml"),
        "job_ids": {
            "array": submission.get("array_job_id"),
            "aggregate": submission.get("aggregate_job_id"),
        },
        "failures": failures,
        "artifact_path": str(experiment),
        "metrics": metrics,
    }
    append_jsonl(ledger, record)
    update_frontier(
        ledger,
        runtime / "frontier.json",
        pearson_tolerance=float(metrics["prediction"]["tolerance"]),
        motif_tolerance=float(metrics["motif_recovery"]["numerical_zero_tolerance"]),
    )
    return record


def record_failed_experiment(
    root: str | Path,
    experiment_id: str,
    reason: str,
    runs_root: str | Path | None = None,
    job_ids: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    runtime = root_path / "runtime"
    ledger = runtime / "experiments.jsonl"
    with exclusive_lock(runtime / "ledger.lock"):
        existing = load_jsonl(ledger)
        for row in existing:
            if row.get("experiment_id") == experiment_id and row.get("status") == "failed":
                return row
        runs_path = Path(runs_root).resolve() if runs_root is not None else root_path / "runs"
        experiment = runs_path / experiment_id
        proposal_path = experiment / "proposal.json"
        proposal = read_json(proposal_path) if proposal_path.is_file() else {}
        failures = [
            read_json(path)
            for path in sorted((experiment / "attempts").glob("fold*/*/failure.json"))
        ] if (experiment / "attempts").exists() else []
        record = {
            "schema_version": 1,
            "experiment_id": experiment_id,
            "status": "failed",
            "recorded_at": utc_now(),
            "candidate_commit": proposal.get("candidate_commit"),
            "parent_commit": proposal.get("parent_commit"),
            "hypothesis": proposal.get("hypothesis"),
            "job_ids": job_ids or {},
            "reason": reason,
            "failures": failures,
            "artifact_path": str(experiment),
        }
        append_jsonl(ledger, record)
        return record
