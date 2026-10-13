from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .folds import (
    complete_fold,
    config_model,
    fail_fold,
    prepare_experiment,
    validate_fold,
)
from .frontier import record_scored_experiment, update_frontier
from .io import atomic_write_json, utc_now
from .scoring import score_experiment
from .supervisor import run_once


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Durable Saluki autoresearch harness")
    commands = parser.add_subparsers(dest="command", required=True)

    model = commands.add_parser("config-model", help="print model.name from a training config")
    model.add_argument("config")

    prepare = commands.add_parser("prepare-experiment", help="create an immutable experiment snapshot")
    prepare.add_argument("--root", required=True)
    prepare.add_argument("--experiment-id", required=True)
    prepare.add_argument("--base-config", required=True)
    prepare.add_argument("--runs-root")
    prepare.add_argument("--dataset")

    validate = commands.add_parser("validate-fold", help="validate a completed fold manifest and artifacts")
    validate.add_argument("--experiment-dir", required=True)
    validate.add_argument("--fold", type=int, required=True)
    validate.add_argument("--motifs", required=True)

    complete = commands.add_parser("complete-fold", help="validate and promote a fold attempt")
    complete.add_argument("--experiment-dir", required=True)
    complete.add_argument("--attempt-dir", required=True)
    complete.add_argument("--fold", type=int, required=True)
    complete.add_argument("--motifs", required=True)
    complete.add_argument("--eval-split", default="test")

    fail = commands.add_parser("fail-fold", help="record a failed fold attempt")
    fail.add_argument("--experiment-dir", required=True)
    fail.add_argument("--attempt-dir", required=True)
    fail.add_argument("--fold", type=int, required=True)
    fail.add_argument("--exit-code", type=int, required=True)

    score = commands.add_parser("score", help="validate and score a five-fold experiment")
    score.add_argument("--experiment-dir", required=True)
    score.add_argument("--motifs", required=True)
    score.add_argument("--expected-folds", type=int, default=5)
    score.add_argument("--pearson-tolerance", type=float, default=1e-4)
    score.add_argument("--motif-tolerance", type=float, default=1e-6)

    frontier = commands.add_parser("frontier", help="derive the Pareto frontier from a JSONL ledger")
    frontier.add_argument("--ledger", required=True)
    frontier.add_argument("--output", required=True)
    frontier.add_argument("--pearson-tolerance", type=float, default=1e-4)
    frontier.add_argument("--motif-tolerance", type=float, default=1e-6)

    record = commands.add_parser("record-score", help="append one validated score to the campaign ledger")
    record.add_argument("--root", required=True)
    record.add_argument("--experiment-id", required=True)
    record.add_argument("--runs-root")

    submission = commands.add_parser("write-submission", help="atomically save Slurm submission IDs")
    submission.add_argument("--experiment-dir", required=True)
    submission.add_argument("--array-job-id", required=True)
    submission.add_argument("--aggregate-job-id", required=True)

    supervisor = commands.add_parser("supervisor", help="run one idempotent supervisor tick")
    supervisor.add_argument("--root", required=True)
    supervisor.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "config-model":
        print(config_model(args.config))
    elif args.command == "prepare-experiment":
        print(
            prepare_experiment(
                args.root,
                args.experiment_id,
                args.base_config,
                args.runs_root,
                args.dataset,
            )
        )
    elif args.command == "validate-fold":
        result = validate_fold(args.experiment_dir, args.fold, args.motifs)
        _print_json({"status": "complete", "manifest": str(result["manifest_path"])})
    elif args.command == "complete-fold":
        print(
            complete_fold(
                args.experiment_dir,
                args.attempt_dir,
                args.fold,
                args.motifs,
                args.eval_split,
            )
        )
    elif args.command == "fail-fold":
        print(fail_fold(args.experiment_dir, args.attempt_dir, args.fold, args.exit_code))
    elif args.command == "score":
        _print_json(
            score_experiment(
                args.experiment_dir,
                args.motifs,
                expected_folds=args.expected_folds,
                pearson_tolerance=args.pearson_tolerance,
                motif_tolerance=args.motif_tolerance,
            )
        )
    elif args.command == "frontier":
        _print_json(
            update_frontier(
                args.ledger,
                args.output,
                pearson_tolerance=args.pearson_tolerance,
                motif_tolerance=args.motif_tolerance,
            )
        )
    elif args.command == "record-score":
        _print_json(record_scored_experiment(args.root, args.experiment_id, args.runs_root))
    elif args.command == "write-submission":
        path = atomic_write_json(
            Path(args.experiment_dir) / "submission.json",
            {
                "schema_version": 1,
                "submitted_at": utc_now(),
                "array_job_id": str(args.array_job_id),
                "aggregate_job_id": str(args.aggregate_job_id),
            },
        )
        print(path)
    elif args.command == "supervisor":
        _print_json(run_once(Path(args.root), dry_run=args.dry_run))
    else:  # pragma: no cover - argparse enforces this
        raise AssertionError(args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
