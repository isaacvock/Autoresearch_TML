from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoresearch_harness import supervisor
from autoresearch_harness.folds import EXPECTED_MOTIFS, read_motifs


ROOT = Path(__file__).resolve().parents[1]


class WorkflowContractTest(unittest.TestCase):
    def test_campaign_and_motif_contract(self) -> None:
        campaign = (ROOT / "workflow" / "campaign.env").read_text(encoding="utf-8")
        self.assertIn("N_FOLDS=5", campaign)
        self.assertIn("EVAL_SPLIT=test", campaign)
        self.assertEqual(tuple(read_motifs(ROOT / "workflow" / "motifs.tsv")), EXPECTED_MOTIFS)
        self.assertEqual(len(EXPECTED_MOTIFS), 9)
        self.assertEqual(len({sequence for _, sequence in EXPECTED_MOTIFS}), 9)

        with tempfile.TemporaryDirectory() as temporary:
            selected = Path(temporary) / "motifs.tsv"
            selected.write_text(
                "".join(f"{label}\t{motif}\n" for label, motif in EXPECTED_MOTIFS[:2]),
                encoding="utf-8",
            )
            self.assertEqual(tuple(read_motifs(selected)), EXPECTED_MOTIFS[:2])

    def test_local_and_slurm_share_the_fold_runner(self) -> None:
        local = (ROOT / "workflow" / "run_experiment.sh").read_text(encoding="utf-8")
        slurm = (ROOT / "workflow_slurm" / "train_eval_cv_fold.sh").read_text(encoding="utf-8")
        submit = (ROOT / "workflow_slurm" / "submit_train_eval_cv.sh").read_text(encoding="utf-8")
        self.assertIn("run_fold.sh", local)
        self.assertIn("run_fold.sh", slurm)
        self.assertIn('--array="0-$((N_FOLDS - 1))"', submit)
        self.assertIn("--parsable", submit)
        self.assertIn("afterany", submit)

    def test_data_is_external_and_ignored(self) -> None:
        common = (ROOT / "workflow" / "common.sh").read_text(encoding="utf-8")
        config = (ROOT / "config.sh").read_text(encoding="utf-8")
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn('WSL_DATASET_DIR=', config)
        self.assertIn('SHERLOCK_DATASET_DIR=', config)
        self.assertIn('${AUTORESEARCH_ROOT}/example_train_config.json', common)
        self.assertTrue((ROOT / "example_train_config.json").is_file())
        self.assertFalse((ROOT / "workflow" / "example_train_config.json").exists())
        self.assertIn("/Saluki_let7/", ignore)

    def test_search_space_is_part_of_the_agent_contract(self) -> None:
        self.assertTrue((ROOT / "SEARCH_SPACE.md").is_file())
        for relative_path in (
            "AGENTS.md",
            "program.md",
            "autoresearch_harness/supervisor.py",
        ):
            contents = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("SEARCH_SPACE.md", contents)

    @patch("autoresearch_harness.supervisor.shutil.which", return_value="/usr/bin/sacct")
    @patch("autoresearch_harness.supervisor.subprocess.run")
    def test_sacct_state_parsing(self, run, _which) -> None:
        run.return_value.stdout = "COMPLETED|\nFAILED|\n"
        self.assertEqual(supervisor._slurm_states("123"), {"COMPLETED", "FAILED"})
        run.assert_called_once_with(
            ["sacct", "-j", "123", "--noheader", "--parsable2", "--format=State"],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_slurm_submitter_captures_ids_and_dependency(self) -> None:
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if not conda_prefix:
            self.skipTest("test requires an active Conda environment")
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            test_root = temp / "repo"
            shutil.copytree(
                ROOT,
                test_root,
                ignore=shutil.ignore_patterns(
                    ".git", "Saluki_let7", "runs", "runtime", "test_experiments", "__pycache__"
                ),
            )
            dataset = temp / "dataset"
            dataset.mkdir()
            for name in ("X.npy", "y.npy", "ids.txt", "config.json", "schema.json", "metadata.json"):
                (dataset / name).write_bytes(b"synthetic-test-data")
            fake_bin = temp / "bin"
            fake_bin.mkdir()
            sbatch = fake_bin / "sbatch"
            sbatch.write_text(
                "#!/bin/bash\n"
                "printf '%s\\n' \"$*\" >> \"$SBATCH_STUB_LOG\"\n"
                "if [[ ! -f \"$SBATCH_STUB_STATE\" ]]; then\n"
                "  printf '1\\n' > \"$SBATCH_STUB_STATE\"\n"
                "  printf '8100;testcluster\\n'\n"
                "else\n"
                "  printf '8101;testcluster\\n'\n"
                "fi\n",
                encoding="utf-8",
            )
            sbatch.chmod(0o755)
            (test_root / "config.sh").write_text(
                "#!/bin/bash\n"
                f'SHERLOCK_DATASET_DIR="{dataset}"\n'
                f'SHERLOCK_RUNS_ROOT="{temp / "runs"}"\n'
                'SHERLOCK_CODEX_BIN="codex"\n'
                f'SHERLOCK_CONDA_ROOT="{Path(conda_prefix).parents[1]}"\n'
                f'SHERLOCK_CONDA_ENV="{Path(conda_prefix).name}"\n'
                'MOTIFS_TO_ABLATE=("PRE=UGUA[A|U|C]AUA" "ARE_heptamer=UAUUUAU")\n',
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "SBATCH_STUB_LOG": str(temp / "sbatch.log"),
                    "SBATCH_STUB_STATE": str(temp / "sbatch.state"),
                }
            )
            result = subprocess.run(
                ["bash", str(test_root / "workflow_slurm" / "submit_train_eval_cv.sh"), "--experiment-id", "stub-submit"],
                text=True,
                capture_output=True,
                check=True,
                env=env,
            )
            submission = json.loads(result.stdout.splitlines()[-1])
            self.assertEqual(submission["array_job_id"], "8100")
            self.assertEqual(submission["aggregate_job_id"], "8101")
            calls = (temp / "sbatch.log").read_text(encoding="utf-8").splitlines()
            self.assertIn("--array=0-4", calls[0])
            self.assertIn("--parsable", calls[0])
            self.assertIn("--dependency=afterany:8100", calls[1])
            selected_motifs = (temp / "runs" / "stub-submit" / "config" / "motifs.tsv").read_text(
                encoding="utf-8"
            )
            self.assertIn("PRE\tUGUA[A|U|C]AUA", selected_motifs)
            self.assertIn("ARE_heptamer\tUAUUUAU", selected_motifs)
            self.assertNotIn("let7_7mer_m8", selected_motifs)
            self.assertIn("MOTIF_SPECS_FILE=", calls[0])
            receipt = json.loads(
                (temp / "runs" / "stub-submit" / "submission.json").read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["array_job_id"], "8100")


if __name__ == "__main__":
    unittest.main()
