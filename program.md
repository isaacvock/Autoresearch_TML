# One bounded autoresearch turn

You are running one short decision-making turn in a durable, externally
scheduled campaign. Compute submission and waiting are not your job. Follow
`AGENTS.md` exactly.

## 1. Reconcile before acting

Read, in order:

1. `AGENTS.md` and this file.
2. `SEARCH_SPACE.md`. This is the authoritative campaign search space.
3. `runtime/state.json` if present.
4. Every record in `runtime/experiments.jsonl` and `runtime/frontier.json` if
   present.
5. The proposal and metrics for relevant prior experiments.
6. The repository's status, diff, recent commits, and current
   `example_train_config.json`.
7. Slurm state only when durable state contains Sherlock job IDs.

Git and artifacts are evidence; do not overwrite one to make it agree with
another. If an experiment is submitted, running, or aggregating, summarize its
status in the agent log and exit successfully without waiting, editing, or
submitting anything.

If completed artifacts have not yet been scored, do not invent a score or
modify them. Leave reconciliation to the harness/supervisor and exit. If state
or artifacts disagree in a way that risks duplicate compute or invalid metrics,
report the integrity failure and exit without a proposal.

## 2. Learn from completed experiments

Use only validated records. Compare pooled out-of-fold Pearson (maximize) and
`worst_motif_median` (minimize). Inspect every configured motif median and
fold-level statistic, not just the two headline values. Treat changes within
`1e-4` Pearson or `1e-6` motif effect as ties.

The first campaign experiment must be the unchanged five-fold baseline, using
the current committed config and commit for both parent and candidate. After
that, select a parent from the current Pareto frontier. State one falsifiable
hypothesis tied to one coherent config change. Avoid repeating a config hash or
a failed hypothesis unless the previous failure was explicitly transient.

For every post-baseline candidate, choose only models, fields, and values that
`SEARCH_SPACE.md` explicitly permits. If the file is empty, ambiguous, missing
the proposed field, or inconsistent with the active TranscriptML installation,
stop and report the blocker; do not infer a search space from package internals.

## 3. Prepare exactly one candidate

Edit only `example_train_config.json`. Keep `seed` equal to `42` and
do not edit infrastructure, data, folds, motifs, metrics, or resource settings.
Use a model and parameters both permitted by `SEARCH_SPACE.md` and supported by
the TranscriptML executable installed in the active Conda environment.

Run lightweight deterministic checks before committing:

```bash
python -m json.tool example_train_config.json >/dev/null
python -m autoresearch_harness config-model example_train_config.json
```

Before committing, compare the diff field by field with `SEARCH_SPACE.md` and
confirm that all listed ranges, enumerated choices, and conditional constraints
are satisfied. The command above checks basic config structure; it does not
replace this search-space review.

Review the diff and, except for the unchanged baseline, make one candidate
commit in the repository. The commit message should name the single hypothesis.
Do not initialize a nested repository. If there is no valid Git repository, or
unrelated user changes overlap the candidate file, stop and report the blocker
rather than creating a proposal.

Choose a new experiment ID such as
`YYYYMMDDTHHMMSSZ-short-hypothesis`. Atomically write
`runtime/proposal.json` with exactly this shape:

```json
{
  "schema_version": 1,
  "status": "ready",
  "experiment_id": "20261012T220000Z-example",
  "hypothesis": "One precise sentence describing the change and expected effect.",
  "parent_commit": "full Git commit hash",
  "candidate_commit": "full Git commit hash",
  "base_train_config": "example_train_config.json"
}
```

Write a temporary file in `runtime/` and rename it into place so interruption
cannot expose partial JSON. Then exit successfully. Do not call `sbatch`, start
training, wait for jobs, score partial output, or start another agent turn. The
supervisor validates and consumes the proposal and launches at most one
experiment.

## 4. Failure and quota rules

Retry only failures clearly identified as transient by the durable record. Do
not hide failed attempts; each attempt stays under its experiment directory.
An irrecoverable candidate failure should be recorded once and not resubmitted
under another ID without a new hypothesis.

If agent quota is exhausted, leave all edits and commits intact and exit. The
supervisor records `next_attempt_at` using an advertised reset time when it can
parse one, otherwise using 15-minute, 30-minute, one-hour, then two-hour
backoff. A later invocation starts a fresh turn and reconstructs context from
Git and durable files.

Stop without a proposal only for an explicit campaign stop, active work, an
integrity failure, or a blocker requiring new user authority. Quota exhaustion
is a resumable pause, not campaign completion.
