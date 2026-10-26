"""计时续跑、任务隔离和不完整交付检查，不启动 Unity。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import handoff_timing as timing
from handoff_core import HandoffError


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "中文 计时"

    def test_resume_and_elapsed_not_sum_of_nested_stages(self):
        with patch.object(timing, "now", side_effect=[
            "2026-09-22T10:00:00+08:00", "2026-09-22T10:02:00+08:00",
            "2026-09-22T10:05:00+08:00"]):
            timing.mark(self.root, "team-task", "started")
            timing.mark(self.root, "team-task", "merged")
            partial = timing.report(self.root, "team-task")
            self.assertFalse(partial["complete"])
            self.assertEqual(partial["wall_elapsed_seconds"], 120)
            timing.mark(self.root, "team-task", "finished")
        result = timing.report(self.root, "team-task")
        self.assertEqual(result["wall_elapsed_seconds"], 300)
        self.assertTrue(result["complete"])
        self.assertNotIn("push_verified", [r["event"] for r in result["events"]])

    def test_wrong_task_duplicate_and_closed_task_preserve_bytes(self):
        timing.mark(self.root, "a", "started")
        original = (self.root / "000.json").read_bytes()
        for task, event in [("b", "merged"), ("a", "started")]:
            with self.assertRaises(HandoffError):
                timing.mark(self.root, task, event)
        self.assertEqual((self.root / "000.json").read_bytes(), original)
        timing.mark(self.root, "a", "finished")
        with self.assertRaises(HandoffError):
            timing.mark(self.root, "a", "push_verified")

    def test_clock_rollback_rejected(self):
        with patch.object(timing, "now", return_value="2099-01-01T00:00:00+08:00"):
            timing.mark(self.root, "a", "started")
        with self.assertRaises(HandoffError):
            timing.mark(self.root, "a", "merged")
        self.assertEqual(len(list(self.root.glob("*.json"))), 1)

    def test_missing_start_rejected(self):
        with self.assertRaises(HandoffError):
            timing.mark(self.root, "a", "finished")
        with self.assertRaises(HandoffError):
            timing.report(self.root, "a")

    def test_detailed_milestones_keep_original_lifecycle(self):
        for event in ("started", "prepared", "git_complete", "scene_applied", "merged",
                      "import_ready", "validation_complete", "cleanup_complete", "report_complete", "finished"):
            timing.mark(self.root, "detailed", event)
        result = timing.report(self.root, "detailed")
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["events"]), 10)

    def test_cli_across_processes_and_failure_exit(self):
        command = [sys.executable, "-B", "-X", "utf8", timing.__file__,
                   "--directory", str(self.root), "--task-id", "portable"]
        result = subprocess.run(command + ["--event", "started"], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(command, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["complete"])
        result = subprocess.run(command + ["--event", "started"], capture_output=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
