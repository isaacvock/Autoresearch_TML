# Saluki autoresearch harness

This directory runs one five-fold adaptive-CV campaign against an externally
prepared TranscriptML dataset. It contains orchestration and candidate config,
not TranscriptML source or datasets. `Saluki_let7/` is ignored example context;
production data must be imported separately and selected in `config.sh`.

## One-time configuration

Edit the root `config.sh`. It is the single place for both WSL and Sherlock
dataset paths, experiment-output paths, Codex executable selection, Conda
roots, and Conda environment names. The launch scripts automatically select
the WSL or Sherlock section. No shell variables need to be set before a run.

```bash
# Local WSL
WSL_DATASET_DIR="/mnt/c/path/to/transcriptml_dataset"
WSL_RUNS_ROOT="${AUTORESEARCH_ROOT}/runs"
WSL_CODEX_BIN="/absolute/path/to/codex"
WSL_CONDA_ROOT="/home/isaac/miniforge3"
WSL_CONDA_ENV="transcript-ml2"

# Sherlock
SHERLOCK_DATASET_DIR="/scratch/users/${USER}/path/to/transcriptml_dataset"
SHERLOCK_RUNS_ROOT="/scratch/users/${USER}/saluki-autoresearch-runs"
SHERLOCK_CODEX_BIN="codex"
SHERLOCK_CONDA_ROOT="${GROUP_HOME:-${HOME}}/miniconda"
SHERLOCK_CONDA_ENV="transcript-ml"

# Shared motif objective (one or more LABEL=MOTIF entries)
MOTIFS_TO_ABLATE=(
  "let7_7mer_m8=CUACCUC"
  "miR16_7mer_m8=UGCUGCU"
)
```

Use Linux paths in both sections: WSL paths for the local section and Sherlock
paths for the cluster section. `*_DATASET_DIR` must point to a prepared
TranscriptML dataset bundle. `*_RUNS_ROOT` is where large experiment artifacts
will be written. `WSL_CODEX_BIN` is the local Codex executable path.
`SHERLOCK_CODEX_BIN` should remain `codex`: the Sherlock supervisor runs
`module load codex` and then uses the command supplied by that module. Codex is
needed by the autonomous supervisor but not by a direct manually selected
experiment. The repository root is detected automatically and should not be
added to `config.sh`.

`MOTIFS_TO_ABLATE` controls both which ablations run and the motif objective.
Each entry uses `LABEL=MOTIF` syntax; labels must be filesystem-safe and unique,
and motif definitions must also be unique. With one entry, its pooled median
`A - R` effect is minimized. With multiple entries, every listed ablation runs
and the objective minimized is the maximum of their pooled median effects.
Choose this list before starting a campaign and do not change it while adding
experiments to the same results directory.

Commit `config.sh` after setting it so fresh agent turns and Sherlock clones use
the same declared campaign configuration. Do not place tokens or passwords in
it; the configured values should only be paths and environment names.

## Direct local run in WSL

Run this from a WSL shell. The wrapper reads the WSL section of `config.sh`,
activates the configured Conda environment, checks the dataset and TranscriptML
installation, and then runs folds `0-4` serially.

```bash
cd /path/to/Autoresearch
bash workflow/run_local_wsl.sh --experiment-id baseline-five-fold
```

Each experiment gets an immutable subdirectory under the configured WSL runs
path. The direct runner processes folds serially; each fold performs training,
held-out evaluation, and all configured full-dataset motif ablations before
validated aggregation.

## Direct Sherlock run

Run this from a Sherlock login node. The submitter reads the Sherlock section
of `config.sh`, activates the configured Conda environment, snapshots the
candidate config, creates the log directory, submits array indices `0-4`, and
submits one dependent aggregation job.

```bash
cd /path/to/Autoresearch
bash workflow_slurm/submit_train_eval_cv.sh --experiment-id baseline-five-fold
```

The submitted jobs receive these settings automatically; do not export them in
your shell or add them to the submission command. Keep the same TranscriptML
release/revision in both environments; every experiment records the installed
package version and executable path.

## Restartable agent supervisor

The supervisor performs one bounded tick and exits. It holds an exclusive
lock, reconciles active artifacts/jobs, scores complete folds, invokes one
fresh ephemeral Codex turn only when idle, and consumes at most one validated
proposal. Durable control state is in `runtime/state.json`; the append-only
ledger and derived Pareto set are `runtime/experiments.jsonl` and
`runtime/frontier.json`.

Run a local tick with:

```bash
bash workflow/supervisor_once_wsl.sh
```

Run a Sherlock tick with:

```bash
bash workflow_slurm/supervisor_once_sherlock.sh
```

The supervisor wrapper selects the appropriate dataset, results directory,
Codex executable, Conda root, and Conda environment from `config.sh`. The
Sherlock supervisor additionally runs `module load codex` and verifies that the
module supplied the configured `codex` command. A direct experiment does not
invoke or load Codex; a supervisor tick invokes it only when no experiment
needs reconciliation or monitoring.

For unattended Sherlock operation, install the included Slurm schedule once:

```bash
bash workflow_slurm/start_autoresearch.sh
```

This validates the configured TranscriptML and Codex environments, removes a
previous `runtime/STOP` marker, and adds a marked entry to Sherlock's
`scrontab`. It preserves unrelated scheduled jobs. Sherlock then runs one
supervisor tick every five minutes in the lightweight `service` partition;
`--dependency=singleton` prevents overlapping copies. The rendered schedule is
equivalent to `workflow_slurm/autoresearch.scrontab.example`.

Inspect or stop it with:

```bash
bash workflow_slurm/status_autoresearch.sh
bash workflow_slurm/stop_autoresearch.sh
```

Stopping removes only this repository's scheduled block and creates
`runtime/STOP`. It deliberately does not cancel training jobs that are already
running. The supervisor checks the stop marker again after a Codex turn, so a
stop requested during that turn prevents submission of its proposal.

For unattended WSL operation, schedule the local command every five minutes
with cron or Windows Task Scheduler. For cron, use an absolute path:

```cron
*/5 * * * * /absolute/path/Autoresearch/workflow/supervisor_once_wsl.sh >>/absolute/path/supervisor.log 2>&1
```

For Windows Task Scheduler, make the action `wsl.exe` and pass arguments like
`-- bash -lc 'bash /absolute/wsl/path/Autoresearch/workflow/supervisor_once_wsl.sh'`.
The supervisor honors an advertised ISO reset time in quota messages; otherwise
it backs off for 15 minutes, 30 minutes, one hour, then two hours. A later tick
starts a fresh agent turn from Git and the durable files. Never schedule both
local and Sherlock supervisors against the same campaign at once.

Metrics in `metrics.json` are optimization/adaptive-CV results, not independent
test-set estimates. No sealed holdout is used during this campaign.

## Full Details

### Design boundaries

The system deliberately separates three kinds of state:

1. **Version-controlled research intent.** `AGENTS.md`, `program.md`,
   `SEARCH_SPACE.md`, `config.sh`, the fixed workflow and scoring code, and
   `example_train_config.json` live in this Git repository.
   During an autonomous research turn, the candidate config is the only
   scientific workflow file the agent may edit.
2. **External immutable inputs.** TranscriptML is installed in the configured
   Conda environment, and the prepared dataset is selected in `config.sh`.
   Neither TranscriptML source nor production data is vendored here.
3. **Durable generated state.** Experiment artifacts live under the applicable
   `*_RUNS_ROOT` path from `config.sh` (used internally as `RUNS_ROOT`), while
   campaign control state lives under the ignored `runtime/` directory. These
   files, rather than the lifetime of a Codex process, determine what has run
   and what remains to be done.

This Git repository must be valid before autonomous proposals can be
accepted. Git revisions identify the candidate and its Pareto parent. The
supervisor never initializes a nested repository and never modifies an
installed TranscriptML package.

### Source layout

```text
Autoresearch/
├── AGENTS.md                         stable permissions and campaign rules
├── program.md                        one bounded agent-turn protocol
├── SEARCH_SPACE.md                   user-defined permitted candidate choices
├── config.sh                         WSL and Sherlock user configuration
├── example_train_config.json         agent-editable candidate
├── README.md
├── workflow/
│   ├── campaign.env                  fixed folds, seeds, metric tolerances
│   ├── motifs.tsv                    reference motif catalogue
│   ├── common.sh                     shared paths and campaign validation
│   ├── run_fold.sh                   common local/Slurm fold implementation
│   ├── run_experiment.sh             serial five-fold local runner
│   ├── run_local_wsl.sh              WSL environment wrapper
│   └── supervisor_once_wsl.sh        one local supervisor tick
├── workflow_slurm/
│   ├── sherlock_config.sh            Sherlock environment activation
│   ├── autoresearch.scrontab.example recurring supervisor example
│   ├── start_autoresearch.sh          enable recurring Sherlock supervisor
│   ├── stop_autoresearch.sh           stop new autonomous work safely
│   ├── status_autoresearch.sh         show schedule, state, and related jobs
│   ├── submit_train_eval_cv.sh       array and aggregation submission
│   ├── train_eval_cv_fold.sh         Slurm wrapper around run_fold.sh
│   ├── aggregate_experiment.sh       validation, scoring, and ledger update
│   └── supervisor_once_sherlock.sh   one Sherlock supervisor tick
├── autoresearch_harness/
│   ├── folds.py                      snapshots and artifact validation
│   ├── scoring.py                    fixed two-objective scorer
│   ├── frontier.py                   ledger and Pareto frontier
│   ├── supervisor.py                 reconciliation and bounded agent launch
│   └── io.py                         atomic files, hashes, locks, JSONL
└── harness_tests/                    synthetic and interruption tests
```

`Saluki_let7/` is ignored contextual material. It is not a workflow default.
If those files were tracked before the ignore rule was added, they must be
removed once from this repository's Git index with `git rm -r --cached` while
leaving the local files intact.

### Fixed scientific contract

Every candidate is evaluated with five fixed CV folds. The CV seed is
`10141996`, validation offset is `1`, the candidate training base seed is `42`
(TranscriptML derives fold seeds `42` through `46`), and motif-ablation seed is
`42`. Predictive evaluation uses the held-out `test` partition of each fold.
Because these folds are repeatedly consulted during optimization, the result is
called **adaptive CV** or **optimization CV**, never an unbiased test result.

The predictive objective is pooled out-of-fold Pearson correlation. Predictions
from all five held-out folds are reordered by dataset index and correlated with
the corresponding targets as one vector. The scorer requires every dataset
index exactly once, rejects duplicates or missing indices, and verifies the CSV
targets against the immutable `y.npy` values.

The motif objective uses the one or more definitions in `MOTIFS_TO_ABLATE` in
`config.sh`. Each of the five trained models performs every configured motif
ablation over the complete dataset. Effects use TranscriptML's `A - R`
definition. For each motif, effects from all instances and all five models are
concatenated and their median is computed. `worst_motif_median` is the maximum
of the configured motif medians and is minimized; with one motif it equals that
motif's median. Pooled Pearson is maximized. Negative motif medians are desired,
and the metrics include near-zero and nonnegative diagnostics.

The Pareto frontier uses tolerances of `1e-4` Pearson and `1e-6` motif effect.
A candidate dominates another only when it is non-worse in both objectives
within those tolerances and better than tolerance in at least one objective.

### Experiment initialization and layout

An experiment ID must be unique and contain only letters, digits, dots,
underscores, and hyphens. Initialization copies the candidate into an immutable
snapshot, validates the fixed training seed and model name, and records:

- candidate config hash;
- dataset path, sizes, and SHA-256 hashes;
- an immutable snapshot and hash of the configured motif definitions;
- fixed folds and seeds;
- TranscriptML package version and executable path; and
- the optimization-CV performance label.

The generated layout under the selected configured runs directory is
approximately:

```text
RUNS_ROOT/<experiment-id>/
├── experiment.json
├── proposal.json                    autonomous runs only
├── config/train_config.json         immutable candidate snapshot
├── config/motifs.tsv                immutable selected-motif snapshot
├── attempts/
│   ├── fold0/<attempt-id>/
│   │   ├── cv/fold0/                dataset links, config, model, predictions
│   │   ├── interpret/motif_ablation/
│   │   └── failure.json             only if that attempt fails
│   └── fold1/... through fold4/...
├── folds/
│   ├── fold0.json                   promoted validated attempt
│   └── fold1.json through fold4.json
├── metrics.json                     atomic final aggregation
├── submission.json                  Slurm job IDs, when applicable
├── local.log                        supervised local execution, when applicable
└── slurm/                            per-fold and aggregation logs
```

Retries never write into a previous attempt directory. This prevents a partial
retry from corrupting a previously useful artifact and preserves failure
evidence for later diagnosis.

### Fold lifecycle and validation

Before doing work, `run_fold.sh` validates any existing promoted fold. A valid
fold is skipped. If no promoted fold exists, it checks previous attempt
directories and promotes a fully finished valid attempt when possible. Only
when there is nothing recoverable does it create a new attempt and perform:

1. TranscriptML fold preparation using the immutable config snapshot.
2. Model training.
3. Evaluation on the fold's held-out test split.
4. All configured full-dataset motif ablations.
5. Artifact validation and atomic promotion to `folds/foldN.json`.

Promotion requires a nonempty checkpoint, prediction CSV, split definition,
and fold training config. The prediction columns and indices must be valid and
must exactly match the fold's test indices. The effective training parameters,
apart from derived dataset and output paths, must match the experiment
snapshot.

For every motif, the effects array, summary, and instance table must be present
and nonempty. Effects must be a finite one-dimensional vector, the summary must
declare `A - R`, and the instance count must agree with the effect count. During
final scoring, motif instance tables and effect counts must also agree across
all five models.

A checkpoint or prediction file by itself is never a completion marker. Only a
validated promoted fold manifest causes future runs to skip that fold.

### Scoring and completion semantics

Scoring begins only after all five promoted folds validate again. It rechecks
the dataset hashes, out-of-fold coverage, prediction targets, fold artifacts,
and motif populations. It then atomically writes `metrics.json` containing:

- pooled out-of-fold Pearson;
- Pearson and example count for each fold;
- mean and standard deviation of fold Pearson values;
- all configured pooled motif medians;
- `worst_motif` and `worst_motif_median`;
- near-zero, nonnegative, and all-negative motif diagnostics;
- motif instance counts; and
- SHA-256 hashes for the scored artifacts.

The current implementation does not use a separate empty `COMPLETE` file.
Successful atomic `metrics.json` creation followed by an idempotent `scored`
ledger record is the completion contract. If interruption occurs after metrics
are written but before the ledger update, the next supervisor invocation finds
the metrics and finishes ledger/frontier reconciliation without retraining.

`runtime/experiments.jsonl` is the append-only authoritative campaign ledger.
It records candidate and parent commits, hypothesis, hashes, seeds, package
provenance, job IDs, failures, artifact paths, and metrics. Ledger updates use a
lock and are idempotent for a scored experiment. `runtime/frontier.json` is a
derived view and can be regenerated from the ledger. A tabular report may be
generated for convenience, but it should not replace the JSONL ledger.

### Local and Sherlock execution

Local execution and Sherlock execution call the same `workflow/run_fold.sh`.
This guarantees the same folds, seeds, motifs, configuration rules, artifact
layout, and scorer in both environments.

`workflow/run_local_wsl.sh` selects the five `WSL_*` values in `config.sh`.
The scripts under `workflow_slurm/` select the five `SHERLOCK_*` values. They
translate those settings into internal process and Slurm-job values
automatically. User-provided shell exports are neither required nor used as the
configuration interface.

The direct WSL runner processes folds serially. When launched by the supervisor,
it runs as an independent process and writes `local.log`. A manually started
foreground run can instead be protected with a user-managed terminal session
such as `tmux`; terminal persistence is operational convenience and is not used
as evidence of experiment completion.

Sherlock submission creates a Slurm array with indices `0-4`. Each array task
runs exactly one fold. A dependent aggregation job uses `afterany`, so it runs
even if one fold fails; validation then either scores the complete experiment
or fails clearly because required fold manifests are absent. Slurm job IDs are
captured with `sbatch --parsable` and stored in `submission.json`.

The array-based path is the preferred unattended mode because training remains
independent of Codex, a terminal, or an interactive allocation. A persistent
interactive L40S allocation can reduce queue latency for actively supervised
work, but neither `tmux` nor Codex can keep work alive after the allocation's
time limit expires. Completed fold manifests still allow a later invocation to
skip finished folds and start new attempts for unfinished folds.

Before manually resubmitting an interrupted experiment, confirm that its
recorded jobs are no longer pending or running. The common fold runner will
skip validated folds, but the submitter itself must not be invoked concurrently
for the same experiment.

### Agent proposal lifecycle

Each Codex turn is intentionally bounded. The agent reads `AGENTS.md`,
`program.md`, `SEARCH_SPACE.md`, Git history and diff, durable state, the full
ledger, the Pareto frontier, and relevant prior metrics. If an experiment is
active, it exits without editing or waiting.

When idle, the agent selects a Pareto parent, states one hypothesis, edits only
the candidate config using choices explicitly permitted by `SEARCH_SPACE.md`,
validates it, and—except for the unchanged baseline—makes one candidate commit
in this repository. An empty or incomplete search space blocks
post-baseline proposals rather than inviting guesses. The agent writes one
atomic `runtime/proposal.json` containing the experiment ID, hypothesis, parent
commit, candidate commit, and config path. It does not submit compute itself.

Before consuming a proposal, the supervisor verifies:

- exact proposal schema;
- unique and valid experiment ID;
- full Git object IDs;
- candidate config path and committed contents;
- that only the permitted config changed;
- that the parent is on the current Pareto frontier; and
- that the external dataset is available.

The supervisor then snapshots the candidate and launches at most one experiment.
This keeps research decisions separate from fixed execution and scoring logic.

### Durable state and interruption recovery

`runtime/state.json` is written atomically and records the campaign status,
active experiment, execution mode, worktree, run root, process or Slurm job IDs,
quota retry time, and last error. The normal lifecycle is:

```text
idle → submitting → submitted → running → aggregating → idle
                                             │
                                             └→ scored ledger record
```

Failures may instead produce `failed`, `agent_error`, `integrity_failure`,
`quota_wait`, or `submission_uncertain`. A lock prevents overlapping supervisor
ticks. Creating `runtime/STOP` causes future ticks to record `stopped` and exit.

Recovery follows durable evidence in this order:

1. If final metrics exist, finish the ledger/frontier update.
2. If all five fold manifests exist, rerun aggregation and scoring.
3. If a recorded local process or Slurm job is active, record `running` and
   exit without launching an agent.
4. If the process or jobs ended without complete artifacts, record a failed
   experiment and preserve every attempt.
5. Only when no experiment is active may a fresh agent turn begin.

There is an unavoidable external-scheduler boundary between `sbatch` accepting
a job and its returned ID being durably recorded. If interruption makes that
boundary ambiguous, the system uses `submission_uncertain` and refuses an
automatic duplicate submission. This condition requires manual comparison of
the experiment, `squeue`, and `sacct`. Refusing duplicate GPU work is safer than
guessing that submission failed.

An incomplete fold starts a new attempt from the beginning unless TranscriptML
itself provides a verified training-state resume mechanism. Completed promoted
folds are never rerun. Partial checkpoints are retained for diagnosis but are
not trusted as resumable or complete state.

### Quota handling and manual operation

Training is independent of the Codex process. Agent quota exhaustion cannot
terminate an already submitted Slurm job or an independently launched local
runner. When automatic supervision is enabled, a quota error records
`quota_wait` and an advertised ISO reset time when one is available. Otherwise,
the backoff sequence is 15 minutes, 30 minutes, one hour, and two hours. A later
tick starts a fresh Codex process that reconstructs context from Git and durable
files.

Automatic Codex restarting is optional. Manual operation is fully compatible
with the design: allow compute to finish, then start a new agent or run one
supervisor tick. The new process does not need conversational memory because
the candidate commit, proposal, manifests, metrics, ledger, and state file are
persistent.

### Reproducibility and operational cautions

- Keep the dataset, fold definitions, seeds, motifs, effect definition,
  tolerances, search space, and resource budget fixed within one campaign.
- Use the same TranscriptML release and code revision in WSL and Sherlock.
  Package version and executable path are recorded, but operators should also
  ensure identically built environments when comparing results.
- Point both configured `*_RUNS_ROOT` values at persistent storage. Generated
  runs, `runtime/`, and the contextual dataset are ignored by Git.
- Do not run local and Sherlock supervisors against the same campaign
  simultaneously.
- Do not delete attempts or edit completed experiment artifacts. Start a new
  experiment ID for a new candidate.
- Do not interpret adaptive-CV performance as a final generalization estimate.
  A separately designed sealed evaluation would be required for that claim.

The test suite uses only synthetic temporary artifacts. It checks pooled
Pearson, motif aggregation, Pareto tolerances, missing and non-finite artifacts,
ledger idempotence, fixed workflow contracts, Slurm job-ID/dependency capture,
active-process reconciliation, uncertain-launch behavior, and quota backoff.
It does not launch model training or read the contextual dataset.
