from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .frontier import record_failed_experiment, record_scored_experiment
from .io import atomic_write_json, load_jsonl, read_json, utc_now, validate_experiment_id
from .scoring import score_experiment


ACTIVE_SLURM_STATES = {"PENDING", "RUNNING", "CONFIGURING", "COMPLETING", "SUSPENDED", "REQUEUED"}
QUOTA_PATTERNS = ("quota", "rate limit", "usage limit", "too many requests", "429", "exhausted")
BACKOFF_SECONDS = (15 * 60, 30 * 60, 60 * 60, 2 * 60 * 60)


class RuntimeLock(AbstractContextManager["RuntimeLock"]):
    def __init__(self, path: Path, stale_seconds: int = 6 * 60 * 60):
        self.path = path
        self.stale_seconds = stale_seconds
        self.acquired = False

    def __enter__(self) -> "RuntimeLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            age = time.time() - self.path.stat().st_mtime
            if age <= self.stale_seconds:
                raise RuntimeError(f"supervisor lock is active: {self.path}")
            self.path.unlink()
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "created_at": utc_now()}))
        self.acquired = True
        return self

    def __exit__(self, *args: object) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)


def default_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "idle",
        "active_experiment": None,
        "worktree": None,
        "execution_mode": os.environ.get("AUTORESEARCH_EXECUTION_MODE", "local"),
        "jobs": {},
        "quota_failures": 0,
        "next_attempt_at": None,
        "last_error": None,
        "updated_at": utc_now(),
    }


def load_state(root: Path) -> dict[str, Any]:
    path = root / "runtime" / "state.json"
    return read_json(path) if path.exists() else default_state()


def save_state(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    atomic_write_json(root / "runtime" / "state.json", state)


def quota_delay_seconds(message: str, failures: int) -> int:
    lowered = message.lower()
    match = re.search(r"retry after\s+(\d+)\s*(second|minute|hour)s?", lowered)
    if match:
        multiplier = {"second": 1, "minute": 60, "hour": 3600}[match.group(2)]
        return int(match.group(1)) * multiplier
    reset = re.search(
        r"(?:retry|reset|resets)(?:\s+at|\s+after)?\s+"
        r"(\d{4}-\d{2}-\d{2}t\d{2}:\d{2}(?::\d{2})?(?:z|[+-]\d{2}:?\d{2}))",
        lowered,
    )
    if reset:
        reset_at = datetime.fromisoformat(reset.group(1).replace("z", "+00:00"))
        return max(0, int((reset_at - datetime.now(timezone.utc)).total_seconds()))
    return BACKOFF_SECONDS[min(max(failures, 0), len(BACKOFF_SECONDS) - 1)]


def is_quota_error(message: str) -> bool:
    lowered = message.lower()
    return any(pattern in lowered for pattern in QUOTA_PATTERNS)


def _all_fold_manifests(runs_root: Path, experiment_id: str) -> bool:
    fold_root = runs_root / experiment_id / "folds"
    return all((fold_root / f"fold{fold}.json").is_file() for fold in range(5))


def _slurm_states(job_id: str) -> set[str]:
    if not shutil.which("sacct"):
        return set()
    result = subprocess.run(
        ["sacct", "-j", job_id, "--noheader", "--parsable2", "--format=State"],
        text=True,
        capture_output=True,
        check=False,
    )
    return {line.split("|")[0].split()[0].upper() for line in result.stdout.splitlines() if line.strip()}


def reconcile(root: Path, runs_root: Path, state: dict[str, Any]) -> bool:
    """Reconcile active work. Return True when this invocation should stop."""
    experiment_id = state.get("active_experiment")
    if not experiment_id:
        return False
    experiment = runs_root / experiment_id
    if state.get("execution_mode") == "slurm" and not state.get("jobs"):
        receipt = experiment / "submission.json"
        if receipt.is_file():
            submitted = read_json(receipt)
            state["jobs"] = {
                "array": str(submitted["array_job_id"]),
                "aggregate": str(submitted["aggregate_job_id"]),
            }
            state["status"] = "submitted"
            save_state(root, state)
    metrics_path = experiment / "metrics.json"
    if metrics_path.is_file():
        record_scored_experiment(root, experiment_id, runs_root)
        state.update(status="idle", active_experiment=None, jobs={}, last_error=None)
        save_state(root, state)
        return False
    if _all_fold_manifests(runs_root, experiment_id):
        state["status"] = "aggregating"
        save_state(root, state)
        score_experiment(experiment, experiment / "config" / "motifs.tsv")
        record_scored_experiment(root, experiment_id, runs_root)
        state.update(status="idle", active_experiment=None, jobs={}, last_error=None)
        save_state(root, state)
        return False
    if state.get("execution_mode") == "slurm":
        job_id = str(state.get("jobs", {}).get("array", ""))
        if not job_id:
            state["last_error"] = "Slurm submission receipt is uncertain; refusing duplicate submission"
            save_state(root, state)
            return True
        statuses = _slurm_states(job_id) if job_id else set()
        if not statuses or statuses & ACTIVE_SLURM_STATES:
            state["status"] = "running"
            save_state(root, state)
            return True
        if statuses and all(value == "COMPLETED" for value in statuses):
            state["last_error"] = "Slurm completed but one or more validated fold manifests are missing"
        else:
            state["last_error"] = f"Slurm experiment ended without complete artifacts: {sorted(statuses)}"
        reason = state["last_error"]
        record_failed_experiment(root, experiment_id, reason, runs_root, state.get("jobs"))
        state.update(status="failed", active_experiment=None, jobs={})
        save_state(root, state)
        return True
    pid = int(state.get("jobs", {}).get("pid", 0) or 0)
    if pid:
        try:
            os.kill(pid, 0)
            state["status"] = "running"
            save_state(root, state)
            return True
        except OSError:
            reason = "local experiment process exited without complete fold manifests"
            record_failed_experiment(root, experiment_id, reason, runs_root, state.get("jobs"))
            state.update(
                status="failed",
                active_experiment=None,
                jobs={},
                last_error=reason,
            )
            save_state(root, state)
            return True
    else:
        # An interruption in the narrow launch/receipt window is deliberately
        # not retried: doing so could start the same experiment twice.
        state["status"] = "submission_uncertain"
        state["last_error"] = "local submission receipt is uncertain; refusing duplicate launch"
        save_state(root, state)
        return True
    return False


def _invoke_codex(root: Path) -> subprocess.CompletedProcess[str]:
    runtime = root / "runtime"
    log_dir = runtime / "agent_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prompt = (
        "Read AGENTS.md, program.md, and SEARCH_SPACE.md and perform exactly one bounded "
        "autoresearch turn. Treat SEARCH_SPACE.md as authoritative and do not modify it. "
        "Do not submit or wait for compute jobs. If you prepare a candidate, atomically write "
        "runtime/proposal.json with status=ready, experiment_id, hypothesis, parent_commit, "
        "candidate_commit, and base_train_config."
    )
    command = [
        os.environ.get("CODEX_BIN", "codex"),
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "-C",
        str(root),
        "-s",
        "workspace-write",
        "-a",
        "never",
        "-",
    ]
    result = subprocess.run(command, input=prompt, text=True, capture_output=True, check=False)
    (log_dir / f"{stamp}.log").write_text(result.stdout + "\n--- stderr ---\n" + result.stderr, encoding="utf-8")
    return result


def _validate_proposal(root: Path, runs_root: Path, proposal: dict[str, Any]) -> tuple[str, Path]:
    required = {
        "schema_version",
        "status",
        "experiment_id",
        "hypothesis",
        "parent_commit",
        "candidate_commit",
        "base_train_config",
    }
    if set(proposal) != required or proposal.get("schema_version") != 1 or proposal.get("status") != "ready":
        raise ValueError("runtime/proposal.json does not match the required schema")
    experiment_id = validate_experiment_id(str(proposal["experiment_id"]))
    if not str(proposal["hypothesis"]).strip():
        raise ValueError("proposal hypothesis must be nonempty")
    for field in ("parent_commit", "candidate_commit"):
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", str(proposal[field])):
            raise ValueError(f"proposal {field} must be a full Git object ID")
    config = Path(str(proposal["base_train_config"]))
    if not config.is_absolute():
        config = root / config
    config = config.resolve()
    allowed_config = (root / "example_train_config.json").resolve()
    if config != allowed_config:
        raise ValueError("proposal base_train_config must be example_train_config.json")
    if (runs_root / experiment_id).exists():
        raise ValueError(f"experiment ID already exists: {experiment_id}")

    git_root_result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if git_root_result.returncode != 0:
        raise RuntimeError("no valid enclosing Git repository")
    git_root = Path(git_root_result.stdout.strip()).resolve()
    relative_config = config.relative_to(git_root).as_posix()
    candidate = str(proposal["candidate_commit"])
    parent = str(proposal["parent_commit"])
    for commit in (parent, candidate):
        subprocess.run(
            ["git", "-C", str(git_root), "cat-file", "-e", f"{commit}^{{commit}}"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    committed_config = subprocess.run(
        ["git", "-C", str(git_root), "show", f"{candidate}:{relative_config}"],
        capture_output=True,
        check=True,
    ).stdout
    if committed_config != config.read_bytes():
        raise ValueError("candidate config in the worktree differs from the proposed commit")
    changed = subprocess.run(
        ["git", "-C", str(git_root), "diff", "--name-only", parent, candidate],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    scored = [
        row
        for row in load_jsonl(root / "runtime" / "experiments.jsonl")
        if row.get("status") == "scored"
    ]
    if scored and changed != [relative_config]:
        raise ValueError("candidate commit must change only example_train_config.json")
    if scored:
        frontier_path = root / "runtime" / "frontier.json"
        frontier = read_json(frontier_path) if frontier_path.is_file() else {}
        frontier_commits = {
            str(item.get("candidate_commit")) for item in frontier.get("experiments", [])
        }
        if parent not in frontier_commits:
            raise ValueError("proposal parent_commit is not on the current Pareto frontier")
    if not scored and changed not in ([], [relative_config]):
        raise ValueError("baseline proposal contains changes outside the candidate config")
    return experiment_id, config


def _launch_proposal(root: Path, runs_root: Path, state: dict[str, Any]) -> bool:
    proposal_path = root / "runtime" / "proposal.json"
    if not proposal_path.is_file():
        return False
    proposal = read_json(proposal_path)
    experiment_id, base_config = _validate_proposal(root, runs_root, proposal)
    from .folds import prepare_experiment

    dataset_dir = os.environ.get("DATASET_DIR")
    if not dataset_dir:
        raise RuntimeError("DATASET_DIR must point to the external campaign dataset")
    motifs_file = os.environ.get("MOTIF_SPECS_FILE")
    if not motifs_file:
        raise RuntimeError("MOTIF_SPECS_FILE was not loaded from config.sh")
    experiment = prepare_experiment(
        root, experiment_id, base_config, runs_root, dataset_dir, motifs_file
    )
    atomic_write_json(experiment / "proposal.json", proposal)
    proposal_path.unlink()
    mode = state.get("execution_mode", "local")
    state.update(status="submitting", active_experiment=experiment_id, jobs={}, last_error=None)
    save_state(root, state)
    if mode == "slurm":
        submit_env = os.environ.copy()
        submit_env["RUNS_ROOT"] = str(runs_root)
        submit_env["BASE_TRAIN_CONFIG"] = str(experiment / "config" / "train_config.json")
        result = subprocess.run(
            ["bash", str(root / "workflow_slurm" / "submit_train_eval_cv.sh"), "--experiment-id", experiment_id],
            text=True,
            capture_output=True,
            check=True,
            env=submit_env,
        )
        submission = json.loads(result.stdout.splitlines()[-1])
        jobs = {"array": str(submission["array_job_id"]), "aggregate": str(submission["aggregate_job_id"])}
    elif mode == "local":
        log_path = experiment / "local.log"
        log_handle = log_path.open("a", encoding="utf-8")
        process_env = os.environ.copy()
        process_env["RUNS_ROOT"] = str(runs_root)
        process_env["BASE_TRAIN_CONFIG"] = str(experiment / "config" / "train_config.json")
        process = subprocess.Popen(
            ["bash", str(root / "workflow" / "run_experiment.sh"), "--experiment-id", experiment_id],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=process_env,
        )
        log_handle.close()
        jobs = {"pid": process.pid}
    else:
        raise ValueError(f"unsupported execution mode: {mode}")
    state.update(status="submitted", active_experiment=experiment_id, jobs=jobs, last_error=None)
    save_state(root, state)
    return True


def run_once(root: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    root_path = Path(root).resolve()
    runs_root = Path(os.environ.get("RUNS_ROOT", root_path / "runs")).resolve()
    runtime = root_path / "runtime"
    with RuntimeLock(runtime / "supervisor.lock"):
        state = load_state(root_path)
        state["worktree"] = str(root_path)
        if (runtime / "STOP").exists():
            state.update(status="stopped", last_error=None)
            save_state(root_path, state)
            return state
        requested_mode = os.environ.get("AUTORESEARCH_EXECUTION_MODE", "local")
        if requested_mode not in {"local", "slurm"}:
            raise ValueError(f"unsupported AUTORESEARCH_EXECUTION_MODE: {requested_mode}")
        if state.get("active_experiment") and state.get("execution_mode") != requested_mode:
            raise RuntimeError("execution mode changed while an experiment is active")
        if not state.get("active_experiment"):
            state["execution_mode"] = requested_mode
        previous_runs_root = state.get("runs_root")
        if previous_runs_root and Path(previous_runs_root).resolve() != runs_root and state.get("active_experiment"):
            raise RuntimeError("RUNS_ROOT changed while an experiment is active")
        state["runs_root"] = str(runs_root)
        if reconcile(root_path, runs_root, state):
            return state
        next_attempt = state.get("next_attempt_at")
        if next_attempt and datetime.fromisoformat(next_attempt) > datetime.now(timezone.utc):
            return state
        if dry_run:
            state["dry_run"] = True
            return state
        try:
            result = _invoke_codex(root_path)
        except OSError as exc:
            state.update(status="agent_error", last_error=str(exc))
            save_state(root_path, state)
            return state
        combined = result.stdout + "\n" + result.stderr
        if result.returncode != 0:
            if is_quota_error(combined):
                failures = int(state.get("quota_failures", 0))
                delay = quota_delay_seconds(combined, failures)
                state.update(
                    status="quota_wait",
                    quota_failures=failures + 1,
                    next_attempt_at=(datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(),
                    last_error="agent quota or rate limit reached",
                )
            else:
                state.update(status="agent_error", last_error=f"Codex exited with status {result.returncode}")
            save_state(root_path, state)
            return state
        state.update(status="idle", quota_failures=0, next_attempt_at=None, last_error=None)
        if (runtime / "STOP").exists():
            state.update(status="stopped", last_error=None)
            save_state(root_path, state)
            return state
        try:
            _launch_proposal(root_path, runs_root, state)
        except subprocess.CalledProcessError as exc:
            state.update(
                status="submission_uncertain",
                last_error=f"experiment submission failed with status {exc.returncode}",
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            state.update(status="integrity_failure", last_error=str(exc))
        except OSError as exc:
            state.update(
                status="submission_uncertain" if state.get("active_experiment") else "integrity_failure",
                last_error=str(exc),
            )
        save_state(root_path, state)
        return state
