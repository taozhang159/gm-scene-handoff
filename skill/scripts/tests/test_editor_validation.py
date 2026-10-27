"""原目录 MCP 结果协议与动态场景发现测试；不连接或启动 Unity。"""

import argparse
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import editor_validation as editor
import handoff
import handoff_core as core


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gm-editor-test-")
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "原项目"
        for name in core.INPUT_ROOTS:
            (self.project / name).mkdir(parents=True)
        (self.project / "Assets/data.txt").write_text("initial")
        core.write_json(self.project / "Packages/manifest.json", {"dependencies": {}})
        core.write_json(self.project / "Packages/packages-lock.json", {})
        (self.project / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.62f2c1\n")
        core.git(self.root, "init")
        core.git(self.root, "config", "user.name", "Test")
        core.git(self.root, "config", "user.email", "test@example.invalid")
        self.commit("initial")
        self.evidence = self.project / "Docs/SceneHandoffs/test"
        source = core.snapshot(self.project, "fixture")
        core.write_json(self.evidence / "source.json", source)
        core.write_json(self.evidence / "protection.json", {
            "task_id": "test", "status": "prepared", "method": "isolated",
            "details": "模拟数据，没有用户存档写入"})
        self.plan = {"task_id": "test", "source_commit": source["commit"],
                     "target_base_commit": source["commit"], "source_snapshot": "source.json",
                     "protection_record": "protection.json", "target_platform": "Win64",
                     "scope_authorization": "fixture", "purpose": "final",
                     "checks": [{"id": "check", "backend": "editor_mcp", "mode": "EditMode",
                                 "reason": "fixture", "expected_tests": ["Fixture.A", "Fixture.B"],
                                 "requirements": {"foreground_window": True}}]}
        core.write_json(self.evidence / "plan.json", self.plan)
        self.session_path = self.root / ".git/session.json"
        self.session = {"project_path": str(self.project), "session_id": "pid-start",
                        "instance_id": "instance", "observed_at": core.now(),
                        "playing": False, "compiling": False, "updating": False,
                        "dirty_scenes": False, "capabilities": {"foreground_window": True}}
        core.write_json(self.session_path, self.session)
        self.args = argparse.Namespace(project=self.project, evidence=self.evidence,
                                       plan=self.evidence / "plan.json", check="check", session=self.session_path)

    def tearDown(self):
        self.assertTrue(self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertTrue(self.root.name.startswith("gm-editor-test-"))
        self.temp.cleanup()

    def commit(self, message):
        core.git(self.root, "add", ".")
        core.git(self.root, "commit", "-m", message)
        return core.git(self.root, "rev-parse", "HEAD")

    def start(self):
        result = editor.begin(self.args)
        self.run_id = result["run_id"]
        self.ticket = core.read_json(self.evidence / result["ticket"])
        return result

    def job(self):
        stamp = time.time() * 1000
        return {"job_id": "job", "status": "succeeded", "mode": "EditMode",
                "started_unix_ms": stamp, "finished_unix_ms": stamp,
                "result": {"mode": "EditMode", "summary": {"total": 2, "passed": 2, "failed": 0,
                           "skipped": 0, "durationSeconds": 0.01, "resultState": "Passed"},
                           "results": [{"fullName": n, "state": "Passed", "durationSeconds": 0.005}
                                       for n in ("Fixture.A", "Fixture.B")]}}

    def finish(self, job=None):
        core.write_json(self.root / ".git/job.json", job or self.job(), replace=True)
        core.write_json(self.root / ".git/dispatch.json", {"job_id": "job"}, replace=True)
        return editor.finish(argparse.Namespace(project=self.project, evidence=self.evidence,
                             run_id=self.run_id, session=self.session_path,
                             dispatch=self.root / ".git/dispatch.json", result=self.root / ".git/job.json"))

    def test_original_project_roundtrip_reuse_and_summary(self):
        before = core.git(self.root, "worktree", "list", "--porcelain")
        self.start()
        self.assertEqual(self.finish()["status"], "passed")
        self.assertEqual(editor.begin(self.args)["status"], "reused")
        self.assertEqual(core.git(self.root, "worktree", "list", "--porcelain"), before)
        core.write_json(self.evidence / "cleanup.json", {"task_id": "test", "status": "complete",
                        "user_data_verified": True, "details": "模拟测试无副作用"})
        core.write_json(self.evidence / "files.json", {"files": ["Assets/data.txt"]})
        result = handoff.do_summarize(argparse.Namespace(project=self.project, evidence=self.evidence,
                     plan=self.args.plan, cleanup_record=self.evidence / "cleanup.json",
                     files=self.evidence / "files.json", output=self.evidence / "summary"))
        self.assertEqual(result["effective_count"], 2)
        self.assertEqual(result["status"], "validation_complete")

    def test_default_batch_cannot_launch(self):
        with self.assertRaises(core.HandoffError):
            handoff.do_run(argparse.Namespace())

    def test_report_changes_not_scanned_as_runtime_input(self):
        before = core.snapshot(self.project, "fixture")
        (self.evidence / "large-report.txt").write_text("report" * 100)
        after = core.snapshot(self.project, "fixture")
        self.assertEqual(before["input_snapshot_id"], after["input_snapshot_id"])
        self.assertEqual(before["dirty_snapshot_hash"], after["dirty_snapshot_hash"])
        self.assertTrue(core.dirty_files(core.project_info(self.project)))
        (self.project / "ProjectSettings/new.asset").write_text("actual change")
        changed = core.snapshot(self.project, "fixture")
        self.assertNotEqual(after["input_snapshot_id"], changed["input_snapshot_id"])

    def test_session_wrong_project_stale_dirty_or_missing_capability(self):
        for field, value in (("project_path", str(self.root)), ("playing", True),
                             ("dirty_scenes", True), ("compiling", True),
                             ("observed_at", (datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat()),
                             ("capabilities", {})):
            with self.subTest(field=field):
                core.write_json(self.session_path, {**self.session, field: value}, replace=True)
                with self.assertRaises(core.HandoffError):
                    editor.begin(self.args)

    def test_session_switch_rejects_result(self):
        self.start()
        core.write_json(self.session_path, {**self.session, "session_id": "other"}, replace=True)
        with self.assertRaises(core.HandoffError):
            self.finish()

    def test_input_change_invalidates(self):
        self.start()
        (self.project / "Assets/data.txt").write_text("changed")
        self.assertEqual(self.finish()["status"], "inputs_changed")

    def test_branch_change_at_same_head_invalidates(self):
        self.start()
        core.git(self.root, "switch", "-c", "another")
        self.assertEqual(self.finish()["status"], "inputs_changed")

    def test_missing_duplicate_extra_zero_counts_and_old_job_rejected(self):
        self.start()
        for kind in ("missing", "duplicate", "extra", "zero", "count", "old", "job", "mode"):
            job = self.job()
            if kind == "missing": job["result"]["results"].pop()
            if kind == "duplicate": job["result"]["results"][1]["fullName"] = "Fixture.A"
            if kind == "extra": job["result"]["results"].append({"fullName": "Other", "state": "Passed"})
            if kind == "zero": job["result"]["results"] = []
            if kind == "count": job["result"]["summary"]["passed"] = 1
            if kind == "old": job["started_unix_ms"] = 1
            if kind == "job": job["job_id"] = "old"
            if kind == "mode": job["mode"] = "PlayMode"
            with self.subTest(kind=kind), self.assertRaises(core.HandoffError):
                editor.job_result(job, {"job_id": "job"}, self.ticket)

    def test_failure_and_skip_not_success(self):
        self.start()
        for state in ("Failed", "Skipped"):
            job = self.job()
            job["result"]["results"][0]["state"] = state
            summary = job["result"]["summary"]
            summary.update(passed=1, failed=int(state == "Failed"), skipped=int(state == "Skipped"))
            self.assertEqual(editor.job_result(job, {"job_id": "job"}, self.ticket)["status"], "failed")

    def test_labeled_failure_is_archived_and_blocks_unchanged_retry(self):
        self.start()
        job = self.job()
        job["result"]["results"][0]["state"] = "Failed:Error"
        job["result"]["summary"].update(passed=1, failed=1, resultState="Failed")
        result = self.finish(job)
        self.assertEqual(result["status"], "failed")
        saved = core.read_json(self.evidence / result["result_file"])
        self.assertEqual(saved["failed"], 1)
        self.assertEqual(saved["tests"][0]["result"], "Failed:Error")
        with self.assertRaisesRegex(core.HandoffError, "已有失败"):
            editor.begin(self.args)

    def test_labeled_failure_does_not_hide_wrong_summary(self):
        self.start()
        job = self.job()
        job["result"]["results"][0]["state"] = "Failed:Error"
        with self.assertRaisesRegex(core.HandoffError, "计数"):
            editor.job_result(job, {"job_id": "job"}, self.ticket)

    def summary_args(self):
        core.write_json(self.evidence / "cleanup.json", {"task_id": "test", "status": "complete",
                        "user_data_verified": True, "details": "模拟恢复"})
        core.write_json(self.evidence / "files.json", {"files": ["Assets/data.txt"]})
        return argparse.Namespace(project=self.project, evidence=self.evidence, plan=self.args.plan,
                                  cleanup_record=self.evidence / "cleanup.json", files=self.evidence / "files.json",
                                  output=self.evidence / "summary", require_complete=True)

    def test_summary_guard_leaves_no_output_and_reuses_after_exact_restore(self):
        self.start()
        self.finish()
        args = self.summary_args()
        p = self.project / "Assets/data.txt"
        original = p.read_bytes()
        p.write_bytes(b"different")
        with self.assertRaisesRegex(core.HandoffError, "Assets/data.txt"):
            handoff.do_summarize(args)
        self.assertFalse(args.output.exists())
        p.write_bytes(original)
        self.assertEqual(handoff.do_summarize(args)["status"], "validation_complete")

    def test_exact_bytes_reuse_after_index_refresh_but_not_newlines(self):
        core.git(self.root, "config", "core.autocrlf", "true")
        p = self.project / "Assets/data.txt"
        p.write_bytes(b"initial\r\n")
        self.commit("text fixture")
        p.write_bytes(b"initial\n")
        self.start()
        self.finish()
        args = self.summary_args()
        core.git(self.root, "add", "--", "原项目/Assets/data.txt")
        self.assertEqual(handoff.do_summarize(args)["status"], "validation_complete")
        p.write_bytes(b"initial\r\n")
        args.output = self.evidence / "summary-newline"
        with self.assertRaisesRegex(core.HandoffError, "未创建输出"):
            handoff.do_summarize(args)
        self.assertFalse(args.output.exists())

    def test_summary_does_not_hide_new_failure_with_old_equivalent_pass(self):
        core.git(self.root, "config", "core.autocrlf", "true")
        p = self.project / "Assets/data.txt"
        p.write_bytes(b"initial\r\n")
        self.commit("text fixture")
        p.write_bytes(b"initial\n")
        self.start()
        self.finish()
        core.git(self.root, "add", "--", "原项目/Assets/data.txt")
        self.start()
        job = self.job()
        job["result"]["results"][0]["state"] = "Failed:Error"
        job["result"]["summary"].update(passed=1, failed=1, resultState="Failed")
        self.finish(job)
        args = self.summary_args()
        with self.assertRaisesRegex(core.HandoffError, "未创建输出"):
            handoff.do_summarize(args)
        self.assertFalse(args.output.exists())

    def test_summary_guard_rejects_target_branch_change(self):
        self.start()
        self.finish()
        core.git(self.root, "switch", "-c", "different-target")
        args = self.summary_args()
        with self.assertRaisesRegex(core.HandoffError, "target_matches"):
            handoff.do_summarize(args)
        self.assertFalse(args.output.exists())

    def test_unchanged_failure_requires_diagnosis_or_recovery(self):
        self.start()
        job = self.job()
        job["result"]["results"][0]["state"] = "Failed"
        job["result"]["summary"].update(passed=1, failed=1)
        self.assertEqual(self.finish(job)["status"], "failed")
        with self.assertRaises(core.HandoffError):
            editor.begin(self.args)
        proof = self.evidence / "recovery.json"
        core.write_json(proof, {"task_id": "test", "failed_run_id": self.run_id,
                               "details": "模拟环境已恢复", "evidence": "模拟观察记录"})
        self.args.recovery_evidence = proof
        self.assertEqual(editor.begin(self.args)["status"], "ready")

    def test_pending_blocks_and_cancel_closes_without_success(self):
        self.start()
        with self.assertRaises(core.HandoffError):
            editor.begin(self.args)
        result = editor.cancel(argparse.Namespace(project=self.project, evidence=self.evidence,
                               run_id=self.run_id, reason="模拟断连，原始错误已保留"))
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(editor.begin(self.args)["status"], "ready")

    def test_plan_requires_exact_inventory_and_routes_capabilities(self):
        for mutation in ("inventory", "backend", "purpose"):
            plan = copy.deepcopy(self.plan)
            if mutation == "inventory": del plan["checks"][0]["expected_tests"]
            if mutation == "backend": plan["checks"][0]["backend"] = "batch"
            if mutation == "purpose": plan["purpose"] = "anything"
            core.write_json(self.args.plan, plan, replace=True)
            with self.assertRaises(core.HandoffError):
                core.load_plan(self.args.plan)

    def test_diagnostic_cannot_be_final_summary(self):
        self.plan["purpose"] = "diagnostic"
        core.write_json(self.args.plan, self.plan, replace=True)
        with self.assertRaises(core.HandoffError):
            handoff.do_summarize(self.args)

    def test_discovery_all_numbers_author_nested_and_ambiguous(self):
        scene_root = self.project / "Assets/GMScenes/Test"
        names = ["Chapter_04/TestScene_all_004.unity", "Chapter_04/TestScene_all_004_li43.unity",
                 "TestScene_all_005.unity", "TestScene_all_006_li43.unity", "TestScene_all_004_zhang57.unity"]
        for name in names:
            path = scene_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("%YAML 1.1\n")
        first = self.commit("scenes")
        (scene_root / "TestScene_all_004.unity").write_text("duplicate")
        second = self.commit("duplicate")
        result = core.scene_pairs(self.project, "li43", [first, second])["versions"]
        self.assertEqual([s["status"] for s in result[0]["scenes"]], ["paired", "missing_personal", "missing_base"])
        self.assertEqual(result[1]["scenes"][0]["status"], "ambiguous")
        self.assertNotIn("zhang57", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
