# Saluki autoresearch agent contract

## Scope and environment

`Autoresearch/` is the Git repository root. Never initialize a nested Git
repository or clone/vendor TranscriptML or Karpathy's autoresearch repository
inside it. TranscriptML is an installed dependency:

- Local and Sherlock paths, Codex binaries, and Conda environments are selected
  from the user-maintained root `config.sh`.
- On Sherlock, the supervisor loads Codex with `module load codex`; training and
  aggregation jobs do not need the Codex module.
- Never edit Conda `site-packages`. Architecture experiments must use models
  and parameters exposed by the installed TranscriptML version. A source-level
  TranscriptML change requires separate user authorization and an editable
  sibling checkout; it does not belong in this directory.

Project layout:

- `config.sh`: the single user-maintained configuration for WSL and Sherlock
  dataset paths, results paths, Codex binaries, and Conda environments.
- `SEARCH_SPACE.md`: the campaign's authoritative list of permitted models,
  configuration fields, values/ranges, and cross-field constraints. It is
  maintained by the user, not by autonomous research turns.
- `example_train_config.json`: the agent-editable candidate configuration.
- `workflow/`: shared five-fold runner, immutable campaign settings, motif set,
  and local execution wrappers.
- `workflow_slurm/`: Sherlock activation and Slurm wrappers around the shared
  runner.
- `autoresearch_harness/`: validation, scoring, ledger, Pareto, and supervisor
  code. This is campaign infrastructure, not an optimization target.
- `runtime/`: ignored durable state (`state.json`, `experiments.jsonl`,
  `frontier.json`, proposals, and agent logs).
- `runs/<experiment_id>/`: ignored immutable configs, attempts, manifests,
  metrics, and scheduler logs for one experiment.
- `Saluki_let7/`: ignored, read-only example data retained only as context. Real
  datasets are imported separately and their paths are set in `config.sh`.

## Fixed campaign contract

The following are immutable within a campaign:

- five folds; CV seed `10141996`; validation offset `1`;
- evaluation split `test`, described only as adaptive CV or optimization CV;
- candidate training base seed `42`, with TranscriptML deterministically using
  `42 + fold` for folds `0` through `4`, and motif-ablation seed `42`;
- the external dataset and its prepared contents;
- effect definition `A - R` over the complete dataset for every fold model;
- Pearson tolerance `1e-4` and motif-effect tolerance `1e-6`;
- available compute/resource budget; and
- exactly these nine motifs from `workflow/motifs.tsv`: `PRE`, `ARE_heptamer`,
  `let7_7mer_m8`, `miR16_7mer_m8`, `GRE`, `mir19_7mer_m8`,
  `mir17_7mer_m8`, `mir29_7mer_m8`, and `mir130_7mer_m8`.

Prediction is pooled out-of-fold Pearson across all five fixed test folds and
is maximized. Motif recovery is the median `A - R` for each motif after pooling
all instances across all five models; `worst_motif_median` is the maximum of
those nine medians and is minimized. A candidate belongs on the Pareto frontier
unless another candidate is non-worse in both objectives and better beyond at
least one tolerance.

This campaign has no sealed holdout. Never call adaptive/optimization CV an
unbiased test result or imply that it estimates performance after selection.

## Allowed experiment edits

During an autoresearch turn, edit only `example_train_config.json`.
You may change only the model architecture and optimizer/training fields that
`SEARCH_SPACE.md` explicitly permits, and only to values satisfying its ranges
and constraints. A TranscriptML option is not permitted merely because it
exists in the installed package. Keep `seed` fixed at `42`. Make exactly one
coherent, stated hypothesis per candidate commit.

Treat `SEARCH_SPACE.md` as immutable campaign policy. Do not edit it during an
autonomous research turn. If it is empty, incomplete for the proposed change,
or disagrees with the installed TranscriptML interface, stop and report the
blocker instead of guessing. The unchanged baseline may still be proposed when
the search-space file is empty because it introduces no new parameter choice.

Do not change the dataset, splits, seeds, motifs, scoring definition,
tolerances, resource requests, fold count, runner scripts, harness,
`.gitignore`, `config.sh`, `AGENTS.md`, or `program.md` to improve a score.
Infrastructure repairs require explicit user authorization and must not be
mixed with a model candidate.

## Required behavior

Before editing, read `program.md`, `SEARCH_SPACE.md`, `runtime/state.json` when
present, the full `runtime/experiments.jsonl`, `runtime/frontier.json`, relevant
prior metrics, and the current Git diff/log. Reconcile those sources before
deciding what to try. Select a Pareto parent and state why the proposed single
change might help one or both objectives.

Validate JSON and the candidate config before committing. Explicitly check
every changed field against `SEARCH_SPACE.md`, including conditional and
cross-field constraints. Record the repository's parent and candidate commit
hashes. Use a new immutable experiment ID. Write only the
proposal described in `program.md`; the supervisor owns submission. Never
submit a second experiment while one is active.

Never use destructive resets, delete artifacts or datasets, cancel unrelated
jobs, alter old experiment directories, reuse an experiment ID with different
content, or submit duplicate Slurm jobs. Treat missing/non-finite artifacts,
changed campaign inputs, or inconsistent folds as integrity failures.

Quota exhaustion is a pause, never completion. Preserve the worktree and
proposal state, record a retry time through the supervisor, and exit cleanly so
a later fresh turn can reconstruct the campaign from durable state.
