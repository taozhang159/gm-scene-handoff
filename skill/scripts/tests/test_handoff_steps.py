"""仅在临时小仓库验证阶段辅助命令，不连接 Unity 或修改真实工程。"""

import argparse
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import handoff
import handoff_core as core
import handoff_steps as steps
import editor_validation as editor
import test_editor_validation as fixtures


class StepsTests(unittest.TestCase):
    setUp = fixtures.EditorTests.setUp
    tearDown = fixtures.EditorTests.tearDown
    commit = fixtures.EditorTests.commit
    start = fixtures.EditorTests.start
    job = fixtures.EditorTests.job
    finish = fixtures.EditorTests.finish

    def scenes(self):
        self.target = "Assets/GMScenes/Test/目标 场景.unity"
        self.protected = "Assets/GMScenes/Test/保留场景.unity"
        for name in (self.target, self.protected):
            path = self.project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"%YAML 1.1\n--- !u!1 &1\nGameObject:\n  m_Name: initial\n")
            Path(str(path) + ".meta").write_text("guid: " + ("a" if name == self.target else "b") * 32 + "\n")
        self.baseline = self.commit("scene baseline")
        self.allow = self.evidence / "allow.json"
        self.guard = self.evidence / "guard.json"
        core.write_json(self.allow, {"files": [self.target, self.target + ".meta"]})

    def capture(self, refs=None):
        return steps.guard_create(argparse.Namespace(project=self.project, baseline=self.baseline,
            refs=refs or [self.baseline], allowlist=self.allow, output=self.guard))

    def candidates(self):
        selected = handoff.manifest(self.project, {"files": [self.target, self.target + ".meta"]})
        self.candidate = self.evidence / "candidate.json"
        core.write_json(self.candidate, selected, replace=True)

    def check_guard(self, output="checked.json"):
        return steps.guard_check(argparse.Namespace(project=self.project, guard=self.guard,
                                candidates=self.candidate, output=self.evidence / output))

    def test_scene_guard_chinese_paths_and_approved_target(self):
        self.scenes()
        self.capture()
        (self.project / self.target).write_bytes(b"approved candidate\n")
        self.candidates()
        core.git(self.project, "add", "--", self.target)
        before = core.git(self.root, "status", "--porcelain=v1", "-z", binary=True)
        self.assertEqual(self.check_guard()["status"], "passed")
        # 输出是唯一新增；场景和索引没有被辅助工具写入。
        self.assertEqual((self.project / self.target).read_bytes(), b"approved candidate\n")
        self.assertEqual(steps.index_scenes(self.project)[self.target], steps.filtered_blob(self.project, self.target))
        self.assertTrue(before)

    def test_protected_disk_and_index_are_both_checked(self):
        self.scenes()
        self.capture()
        self.candidates()
        path = self.project / self.protected
        original = path.read_bytes()
        path.write_bytes(b"unexpected\n")
        self.assertEqual(self.check_guard("disk.json")["status"], "failed")
        core.git(self.project, "add", "--", self.protected)
        path.write_bytes(original)
        self.assertEqual(self.check_guard("index.json")["status"], "failed")

    def test_target_unstaged_or_wrong_candidate_is_rejected(self):
        self.scenes()
        self.capture()
        (self.project / self.target).write_bytes(b"candidate\n")
        self.candidates()
        self.assertEqual(self.check_guard("unstaged.json")["status"], "failed")
        core.git(self.project, "add", "--", self.target)
        (self.project / self.target).write_bytes(b"later edit\n")
        self.assertEqual(self.check_guard("later.json")["status"], "failed")

    def test_scene_meta_cannot_change_even_when_candidate_approves_it(self):
        self.scenes()
        self.capture()
        (self.project / (self.target + ".meta")).write_text("guid: " + "c" * 32)
        core.git(self.project, "add", "--", self.target + ".meta")
        self.candidates()
        result = self.check_guard()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("身份" in row["reason"] for row in result["failures"]))

    def test_untracked_scene_is_reported_not_deleted(self):
        self.scenes()
        self.capture()
        self.candidates()
        path = self.project / "Assets/新增个人.unity"
        path.write_text("user parallel work")
        self.assertEqual(self.check_guard()["status"], "failed")
        self.assertTrue(path.exists())

    def test_source_only_scene_must_stay_absent(self):
        self.scenes()
        base_branch = core.project_info(self.project)["branch"]
        core.git(self.root, "switch", "-c", "incoming")
        path = self.project / "Assets/来源个人.unity"
        path.write_text("source scene")
        incoming = self.commit("source-only scene")
        core.git(self.root, "switch", base_branch)
        # allow.json 在临时来源提交中曾被暂存，回到基线后按计划重新生成。
        core.write_json(self.allow, {"files": [self.target, self.target + ".meta"]}, replace=True)
        self.capture([incoming])
        self.assertIsNone(core.read_json(self.guard)["entries"]["Assets/来源个人.unity"]["blob"])
        self.candidates()
        self.assertEqual(self.check_guard("absent.json")["status"], "passed")
        path.write_text("source scene")
        core.git(self.project, "add", "--", "Assets/来源个人.unity")
        self.assertEqual(self.check_guard("introduced.json")["status"], "failed")

    def test_capture_rejects_unstaged_scene_in_nested_project(self):
        self.scenes()
        (self.project / self.protected).write_text("unsaved local change")
        with self.assertRaises(core.HandoffError):
            self.capture()
        self.assertFalse(self.guard.exists())

    def test_capture_rejects_unpaired_allowlist_and_wrong_baseline(self):
        self.scenes()
        core.write_json(self.allow, {"files": [self.target]}, replace=True)
        with self.assertRaises(core.HandoffError):
            self.capture()
        core.write_json(self.allow, {"files": [self.target, self.target + ".meta"]}, replace=True)
        self.commit("new head")
        with self.assertRaises(core.HandoffError):
            self.capture()

    def test_crlf_is_preserved_and_not_confused_with_index_blob(self):
        self.scenes()
        (self.project / ".gitattributes").write_text("*.unity text eol=crlf\n")
        self.baseline = self.commit("line endings")
        for name in (self.target, self.protected):
            path = self.project / name
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.capture()
        self.candidates()
        self.assertEqual(self.check_guard("crlf.json")["status"], "passed")
        path = self.project / self.protected
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        self.assertEqual(self.check_guard("changed-line-endings.json")["status"], "failed")

    def test_candidates_cannot_expand_allowlist(self):
        self.scenes()
        self.capture()
        self.candidates()
        data = core.read_json(self.candidate)
        data["files"][self.protected] = core.file_hash(self.project / self.protected)
        core.write_json(self.candidate, data, replace=True)
        with self.assertRaises(core.HandoffError):
            self.check_guard()

    def test_guard_identity_tamper_or_branch_change_fails(self):
        self.scenes()
        self.capture()
        self.candidates()
        core.git(self.root, "switch", "-c", "another")
        with self.assertRaises(core.HandoffError):
            self.check_guard()

    def test_conflicted_non_scene_resource_blocks_import_guard(self):
        self.scenes()
        self.capture()
        self.candidates()
        blob = core.git(self.project, "rev-parse", "HEAD:" + self.project.name + "/Assets/data.txt")
        name = self.project.name + "/Assets/data.txt"
        rows = f"0 {'0' * 40}\t{name}\n100644 {blob} 1\t{name}\n100644 {blob} 2\t{name}\n"
        result = subprocess.run(["git", "-C", str(self.root), "update-index", "--index-info"],
                                input=rows.encode("utf-8"), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.assertRaises(core.HandoffError):
            self.check_guard()

    def test_tampered_guard_is_rejected(self):
        self.scenes()
        self.capture()
        self.candidates()
        record = core.read_json(self.guard)
        record["entries"].pop(self.protected)
        core.write_json(self.guard, record, replace=True)
        with self.assertRaises(core.HandoffError):
            self.check_guard()

    def test_cli_failure_stops_with_nonzero_and_no_output_rewrite(self):
        self.scenes()
        self.capture()
        self.candidates()
        (self.project / self.protected).write_text("unexpected")
        command = [sys.executable, "-B", "-X", "utf8", handoff.__file__, "scene-guard-check",
                   "--project", str(self.project), "--guard", str(self.guard),
                   "--candidates", str(self.candidate), "--output", str(self.evidence / "failure.json")]
        result = subprocess.run(command, capture_output=True)
        self.assertEqual(result.returncode, 2)
        original = (self.evidence / "failure.json").read_bytes()
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
        self.assertEqual((self.evidence / "failure.json").read_bytes(), original)

    def save_checkpoint(self):
        record = self.evidence / "checkpoint-input.json"
        core.write_json(record, {"task_id": "test", "phase": "prepared", "next_action": "merge after live checks",
            "lock_state": "unknown", "editor_session": "pid-start", "notes": "核实锁状态与原恢复方法",
            "evidence_files": ["source.json", "plan.json"]}, replace=True)
        return steps.checkpoint(argparse.Namespace(project=self.project, evidence=self.evidence, record=record))

    def test_resume_preserves_history_and_detects_evidence_changes(self):
        self.save_checkpoint()
        args = argparse.Namespace(project=self.project, evidence=self.evidence)
        self.assertEqual(steps.resume(args)["status"], "ready")
        self.save_checkpoint()
        self.assertEqual(len(list((self.evidence / "checkpoints").glob("*.json"))), 2)
        (self.evidence / "plan.json").write_text("{}")
        result = steps.resume(args)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["changed_evidence"], ["plan.json"])

    def test_resume_shows_open_ticket_and_does_not_reschedule(self):
        self.save_checkpoint()
        self.start()
        result = steps.resume(argparse.Namespace(project=self.project, evidence=self.evidence))
        self.assertEqual(result["open_tickets"], [self.run_id])
        self.assertFalse((self.evidence / "validation" / self.run_id / "run.json").exists())
        core.git(self.root, "switch", "-c", "changed-branch")
        self.assertEqual(steps.resume(argparse.Namespace(project=self.project, evidence=self.evidence))["status"], "blocked")

    def test_open_ticket_rejected_before_expensive_snapshot(self):
        self.start()
        with patch.object(editor, "snapshot", side_effect=AssertionError("不应扫描")):
            with self.assertRaisesRegex(core.HandoffError, "未收口"):
                editor.begin(self.args)

    def test_existing_summary_rejected_before_expensive_snapshot(self):
        output = self.evidence / "summary"
        output.mkdir()
        with patch.object(handoff, "snapshot", side_effect=AssertionError("不应扫描")):
            with self.assertRaisesRegex(core.HandoffError, "已存在"):
                handoff.do_summarize(argparse.Namespace(project=self.project, evidence=self.evidence,
                                     plan=self.args.plan, output=output))

    def test_restore_plan_detects_parallel_edits_and_does_not_restore(self):
        self.start()
        (self.project / "Assets/data.txt").write_text("test side effect")
        self.finish()
        args = argparse.Namespace(project=self.project, evidence=self.evidence, run_id=self.run_id,
                                  output=self.evidence / "restore.json")
        steps.restore_plan(args)
        data = core.read_json(args.output)
        self.assertEqual(data["status"], "needs_attribution")
        self.assertEqual(data["changes"][0]["current_state"], "matches_after_test")
        self.assertIsNone(data["changes"][0]["attribution"])
        self.assertEqual((self.project / "Assets/data.txt").read_text(), "test side effect")
        (self.project / "Assets/data.txt").write_text("parallel user edit")
        args.output = self.evidence / "parallel.json"
        self.assertEqual(steps.restore_plan(args)["changed_again"], ["Assets/data.txt"])
        (self.project / "Assets/data.txt").write_text("initial")
        args.output = self.evidence / "restored.json"
        steps.restore_plan(args)
        self.assertEqual(core.read_json(args.output)["changes"][0]["current_state"], "already_restored")

    def test_restore_plan_added_file_requires_archive_review_and_head_is_fixed(self):
        self.start()
        (self.project / "Assets/test-only.txt").write_text("test")
        self.finish()
        args = argparse.Namespace(project=self.project, evidence=self.evidence, run_id=self.run_id,
                                  output=self.evidence / "restore.json")
        steps.restore_plan(args)
        self.assertEqual(core.read_json(args.output)["changes"][0]["action"], "review_and_archive")
        self.assertTrue((self.project / "Assets/test-only.txt").exists())
        self.commit("head moved")
        args.output = self.evidence / "head-moved.json"
        with self.assertRaises(core.HandoffError):
            steps.restore_plan(args)

    def test_repository_manifest_includes_sources_and_enforces_boundary(self):
        sources = self.root / "Sources/Chapter_04/源文件.txt"
        sources.parent.mkdir(parents=True)
        sources.write_text("source")
        name = sources.relative_to(self.root).as_posix()
        data = handoff.manifest(self.project, {"path_base": "repository", "files": [name]})
        self.assertEqual(handoff.verify_manifest(self.project, data)["status"], "passed")
        with self.assertRaises(core.HandoffError):
            handoff.manifest(self.project, {"path_base": "repository", "files": ["../outside"]})
        sources.write_text("changed")
        with self.assertRaises(core.HandoffError):
            handoff.verify_manifest(self.project, data)

    def test_repository_summary_adds_project_evidence_with_correct_prefix(self):
        source = self.root / "Sources/art.txt"
        source.parent.mkdir()
        source.write_text("editable")
        self.start()
        self.finish()
        core.write_json(self.evidence / "cleanup.json", {"task_id": "test", "status": "complete",
                        "user_data_verified": True, "details": "fixture"})
        core.write_json(self.evidence / "files.json", {"path_base": "repository", "files": ["Sources/art.txt"]})
        result = handoff.do_summarize(argparse.Namespace(project=self.project, evidence=self.evidence,
                     plan=self.args.plan, cleanup_record=self.evidence / "cleanup.json",
                     files=self.evidence / "files.json", output=self.evidence / "summary"))
        self.assertEqual(result["status"], "validation_complete")
        data = core.read_json(self.evidence / "summary/result-file-hashes.json")
        self.assertIn(self.project.name + "/Docs/SceneHandoffs/test/plan.json", data["files"])
        self.assertIn("Sources/art.txt", data["files"])
        self.assertEqual(handoff.verify_manifest(self.project, data, self.evidence / "summary")["status"], "passed")

    def test_editor_finish_records_real_job_and_collection_boundaries(self):
        self.start()
        result = self.finish()
        timing = result["timing"]
        self.assertGreaterEqual(timing["dispatch_delay_ms"], 0)
        self.assertEqual(timing["job_elapsed_ms"], 0)
        self.assertGreaterEqual(timing["collection_delay_ms"], timing["after_snapshot_ms"] - 2)


if __name__ == "__main__":
    unittest.main()
