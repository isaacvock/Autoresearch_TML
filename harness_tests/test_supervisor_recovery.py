from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoresearch_harness.supervisor import default_state, run_once, save_state


class SupervisorRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_quota_pause_is_durable_and_not_retried_early(self) -> None:
        quota = subprocess.CompletedProcess(
            ["codex"], returncode=1, stdout="", stderr="HTTP 429; retry after 3 minutes"
        )
        with patch("autoresearch_harness.supervisor._invoke_codex", return_value=quota):
            state = run_once(self.root)
        self.assertEqual(state["status"], "quota_wait")
        self.assertEqual(state["quota_failures"], 1)
        persisted = json.loads((self.root / "runtime" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["next_attempt_at"], state["next_attempt_at"])
        with patch(
            "autoresearch_harness.supervisor._invoke_codex",
            side_effect=AssertionError("agent must not run before next_attempt_at"),
        ):
            waiting = run_once(self.root)
        self.assertEqual(waiting["status"], "quota_wait")

    def test_live_local_process_prevents_duplicate_agent_or_launch(self) -> None:
        state = default_state()
        state.update(
            status="running",
            active_experiment="active-test",
            execution_mode="local",
            jobs={"pid": os.getpid()},
            runs_root=str(self.root / "runs"),
        )
        save_state(self.root, state)
        with patch(
            "autoresearch_harness.supervisor._invoke_codex",
            side_effect=AssertionError("agent must not run while compute is active"),
        ):
            reconciled = run_once(self.root)
        self.assertEqual(reconciled["status"], "running")
        self.assertEqual(reconciled["active_experiment"], "active-test")

    def test_interrupted_local_submission_is_not_duplicated(self) -> None:
        state = default_state()
        state.update(
            status="submitting",
            active_experiment="uncertain-test",
            execution_mode="local",
            jobs={},
            runs_root=str(self.root / "runs"),
        )
        save_state(self.root, state)
        with patch(
            "autoresearch_harness.supervisor._invoke_codex",
            side_effect=AssertionError("uncertain submission must not be relaunched"),
        ):
            reconciled = run_once(self.root)
        self.assertEqual(reconciled["status"], "submission_uncertain")
        self.assertEqual(reconciled["active_experiment"], "uncertain-test")

    def test_stop_requested_during_agent_turn_prevents_submission(self) -> None:
        def finish_agent_after_stop(_root: Path) -> subprocess.CompletedProcess[str]:
            runtime = self.root / "runtime"
            runtime.mkdir(parents=True, exist_ok=True)
            (runtime / "STOP").touch()
            return subprocess.CompletedProcess(["codex"], returncode=0, stdout="", stderr="")

        with (
            patch("autoresearch_harness.supervisor._invoke_codex", side_effect=finish_agent_after_stop),
            patch(
                "autoresearch_harness.supervisor._launch_proposal",
                side_effect=AssertionError("a stopped campaign must not submit a proposal"),
            ),
        ):
            state = run_once(self.root)
        self.assertEqual(state["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
