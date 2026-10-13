from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from autoresearch_harness.folds import EXPECTED_MOTIFS, complete_fold, prepare_experiment
from autoresearch_harness.frontier import compute_frontier, dominates, record_scored_experiment
from autoresearch_harness.scoring import score_experiment
from autoresearch_harness.supervisor import is_quota_error, quota_delay_seconds


class HarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "workflow").mkdir()
        self.motifs = self.root / "workflow" / "motifs.tsv"
        self.motifs.write_text(
            "# label\tmotif\n"
            + "".join(f"{label}\t{motif}\n" for label, motif in EXPECTED_MOTIFS),
            encoding="utf-8",
        )
        self.config = self.root / "candidate.json"
        self.config_payload = {
            "dataset": "OVERWRITTEN",
            "output_dir": "OVERWRITTEN",
            "model": {"name": "saluki_exact", "params": {"filters": 8}},
            "epochs": 1,
            "seed": 42,
        }
        self.config.write_text(json.dumps(self.config_payload), encoding="utf-8")
        self.experiment = prepare_experiment(self.root, "test-candidate", self.config)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_fold(self, fold: int, *, nonfinite: bool = False, omit_checkpoint: bool = False) -> None:
        attempt = self.experiment / "attempts" / f"fold{fold}" / "attempt1"
        fold_root = attempt / "cv" / f"fold{fold}"
        (fold_root / "model").mkdir(parents=True)
        (fold_root / "eval").mkdir()
        (fold_root / "dataset").mkdir()
        if not omit_checkpoint:
            (fold_root / "model" / "best.pt").write_bytes(b"checkpoint")
        indices = [2 * fold, 2 * fold + 1]
        with (fold_root / "eval" / "test_predictions.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(["index", "id", "prediction", "target"])
            for index in indices:
                writer.writerow([index, f"tx{index}", 2.0 * index + 1.0, float(index)])
        (fold_root / "dataset" / "splits.json").write_text(
            json.dumps({"train": [], "val": [], "test": indices}), encoding="utf-8"
        )
        fold_config = dict(self.config_payload)
        fold_config["dataset"] = str(fold_root / "dataset")
        fold_config["output_dir"] = str(fold_root / "model")
        fold_config["seed"] = int(self.config_payload["seed"]) + fold
        (fold_root / "train_config.json").write_text(json.dumps(fold_config), encoding="utf-8")

        for motif_number, (label, motif) in enumerate(EXPECTED_MOTIFS, start=1):
            motif_root = attempt / "interpret" / "motif_ablation" / label
            motif_root.mkdir(parents=True)
            effects = np.asarray([-0.1 * motif_number, -0.1 * motif_number])
            if nonfinite and motif_number == 1:
                effects[0] = np.nan
            np.save(motif_root / "effects.npy", effects)
            (motif_root / "summary.json").write_text(
                json.dumps({"analysis": "motif_ablation", "effect_definition": "A - R", "n_instances": 2, "region": "3utr"}),
                encoding="utf-8",
            )
            (motif_root / "instances.csv").write_text(
                "instance_index,seq_index,motif,start,end,valid_length,region\n"
                f"0,0,{motif},1,2,10,3utr\n1,1,{motif},1,2,10,3utr\n",
                encoding="utf-8",
            )
        complete_fold(self.experiment, attempt, fold, self.motifs)

    def test_scores_pooled_cv_and_all_nine_motifs(self) -> None:
        for fold in range(5):
            self.make_fold(fold)
        metrics = score_experiment(self.experiment, self.motifs)
        self.assertAlmostEqual(metrics["prediction"]["pooled_pearson"], 1.0)
        self.assertEqual(metrics["prediction"]["n_examples"], 10)
        self.assertEqual(len(metrics["motif_recovery"]["motif_medians"]), 9)
        self.assertAlmostEqual(metrics["motif_recovery"]["worst_motif_median"], -0.1)
        self.assertEqual(metrics["motif_recovery"]["near_zero_motif_medians"], [])
        self.assertTrue(metrics["motif_recovery"]["all_motif_medians_negative"])
        record_scored_experiment(self.root, "test-candidate")
        record_scored_experiment(self.root, "test-candidate")
        ledger = (self.root / "runtime" / "experiments.jsonl").read_text(encoding="utf-8")
        self.assertEqual(len(ledger.splitlines()), 1)

    def test_missing_artifact_is_rejected(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.make_fold(0, omit_checkpoint=True)

    def test_nonfinite_effect_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.make_fold(0, nonfinite=True)

    def test_pareto_dominance_uses_both_tolerances(self) -> None:
        def row(name: str, pearson: float, motif: float) -> dict:
            return {"experiment_id": name, "status": "scored", "metrics": {"valid": True, "prediction": {"pooled_pearson": pearson}, "motif_recovery": {"worst_motif_median": motif}}}

        strong = row("strong", 0.8, -0.2)
        weak = row("weak", 0.7, -0.1)
        tied = row("tied", 0.80005, -0.1999995)
        self.assertTrue(dominates(strong, weak))
        self.assertFalse(dominates(strong, tied))
        self.assertEqual({item["experiment_id"] for item in compute_frontier([strong, weak])}, {"strong"})

    def test_quota_detection_and_backoff(self) -> None:
        self.assertTrue(is_quota_error("HTTP 429: usage limit exhausted"))
        self.assertEqual(quota_delay_seconds("retry after 3 minutes", 0), 180)
        self.assertEqual(quota_delay_seconds("quota", 0), 15 * 60)
        self.assertEqual(quota_delay_seconds("quota", 3), 2 * 60 * 60)


if __name__ == "__main__":
    unittest.main()
