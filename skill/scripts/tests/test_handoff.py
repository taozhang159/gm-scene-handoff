"""隔离 Git 仓库、真实模拟子进程及故障证据测试；不启动 Unity。"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import handoff
import handoff_core as core
import unity_runner as runner


def xml_text(*, passed=True, stale=False, empty=False):
    stamp = (datetime.now(timezone.utc) - timedelta(days=1 if stale else 0)).isoformat()
    total = 0 if empty else 1
    root = ET.Element("test-run", {"total": str(total), "passed": str(total if passed else 0),
                                  "failed": str(0 if passed else total),
                                  "result": "Passed" if passed else "Failed(Child)",
                                  "start-time": stamp, "end-time": stamp, "duration": "0.01"})
    if total:
        ET.SubElement(root, "test-case", {"fullname": "Fixture.保持状态", "result": "Passed" if passed else "Failed",
                                         "duration": "0.01"})
    return ET.tostring(root, encoding="unicode")


class TempCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gm-handoff-test-")
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        # 递归清理前确认仅覆盖本用例自行创建的临时根目录。
        self.assertTrue(self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertTrue(self.root.name.startswith("gm-handoff-test-"))
        self.temp.cleanup()


class EvidenceTests(TempCase):
    def test_xml_pass_failure_zero_stale_and_truncated(self):
        result = self.root / "result.xml"
        for passed in (True, False):
            result.write_text(xml_text(passed=passed), encoding="utf-8")
            value = runner.parse_result(result, "EditMode", "run", "snapshot", time.time())
            self.assertEqual(value["status"], "passed" if passed else "failed")
        for text in (xml_text(empty=True), xml_text(stale=True), "<test-run>"):
            result.write_text(text, encoding="utf-8")
            with self.assertRaises((ValueError, ET.ParseError)):
                runner.parse_result(result, "EditMode", "run", "snapshot", time.time())

    def test_xml_counts_and_skipped_are_not_pass(self):
        result = self.root / "result.xml"
        result.write_text(xml_text().replace('passed="1"', 'passed="0"'), encoding="utf-8")
        with self.assertRaises(ValueError):
            runner.parse_result(result, "EditMode", "run", "snapshot", time.time())
        text = xml_text().replace('passed="1"', 'passed="0"').replace('result="Passed"', 'result="Skipped"')
        result.write_text(text, encoding="utf-8")
        self.assertEqual(runner.parse_result(result, "EditMode", "run", "snapshot", time.time())["status"], "failed")

    def test_audit_requires_matching_run_and_input(self):
        result = self.root / "result.json"
        core.write_json(result, {"run_id": "run", "input_snapshot_id": "snapshot",
                                 "complete": True, "status": "passed"})
        self.assertEqual(runner.parse_result(result, "audit", "run", "snapshot", time.time())["status"], "passed")
        with self.assertRaises(ValueError):
            runner.parse_result(result, "audit", "other", "snapshot", time.time())

    def test_manifest_detects_changes_deletions_and_escape(self):
        (self.root / "文件.txt").write_text("original", encoding="utf-8")
        data = handoff.manifest(self.root, {"files": ["文件.txt"], "deleted": ["removed.txt"]})
        self.assertEqual(handoff.verify_manifest(self.root, data)["files_checked"], 1)
        (self.root / "文件.txt").write_text("changed", encoding="utf-8")
        with self.assertRaises(core.HandoffError):
            handoff.verify_manifest(self.root, data)
        (self.root / "removed.txt").touch()
        with self.assertRaises(core.HandoffError):
            handoff.manifest(self.root, {"deleted": ["removed.txt"]})
        for name in ("../outside", str(self.root / "absolute"), "bad\\path"):
            with self.assertRaises(core.HandoffError):
                core.inside(self.root, name)

    @unittest.skipUnless(os.name == "nt", "Windows 环境修复")
    def test_environment_is_child_only_and_preserves_valid_values(self):
        valid = str(self.root)
        env = {key: valid for key in ("TEMP", "TMP", "USERPROFILE", "PROGRAMDATA")}
        child, diagnostics = runner.child_environment(env)
        self.assertNotIn("ALLUSERSPROFILE", env)
        self.assertEqual(child["ALLUSERSPROFILE"], valid)
        self.assertEqual(diagnostics["ALLUSERSPROFILE"], "child_only_from_PROGRAMDATA")
        other = self.root / "other"
        other.mkdir()
        env["ALLUSERSPROFILE"] = str(other)
        self.assertEqual(runner.child_environment(env)[0]["ALLUSERSPROFILE"], str(other))
        env["ALLUSERSPROFILE"] = str(self.root / "missing")
        with self.assertRaises(core.HandoffError):
            runner.child_environment(env)
        del env["ALLUSERSPROFILE"]
        env["PROGRAMDATA"] = str(self.root / "missing")
        with self.assertRaises(core.HandoffError):
            runner.child_environment(env)

    def test_test_command_has_no_quit_and_preserves_filter(self):
        check = {"mode": "PlayMode", "test_filter": "A;中文.B"}
        args = runner.command("Unity.exe", self.root / "path with space", check, "result.xml", "log.txt", "r", "s", "Win64")
        self.assertNotIn("-quit", args)
        self.assertNotIn("-noUpm", args)
        self.assertEqual(args[args.index("-testFilter") + 1], "A;中文.B")

    def test_timeouts_cannot_be_nan_or_infinite(self):
        for value in ("nan", "inf", "0", "-1"):
            with self.assertRaises(argparse.ArgumentTypeError):
                handoff.positive(value)


FAKE_CHILD = r'''
import json, pathlib, sys, time
data = json.loads(sys.argv[1])
if data.get("log"):
    pathlib.Path(data["log_path"]).write_text(data["log"], encoding="utf-8")
if data.get("xml"):
    pathlib.Path(data["result_path"]).write_text(data["xml"], encoding="utf-8")
time.sleep(data.get("sleep", 0.1))
sys.exit(data.get("code", 0))
'''


class ProcessTests(TempCase):
    def start(self, **kwargs):
        self.result = self.root / "结果.xml"
        self.log = self.root / "日志.log"
        if kwargs.get("log", "").startswith("Input System module"):
            kwargs["log"] = "Saving results to: " + str(self.result) + "\n" + kwargs["log"]
        self.launched = time.time()
        args = [sys.executable, "-c", FAKE_CHILD,
                json.dumps({"result_path": str(self.result), "log_path": str(self.log), **kwargs})]
        self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.identity = runner.process_identity(self.process)
        self.addCleanup(self.finish_child)

    def finish_child(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=10)

    def observe(self, **kwargs):
        return runner.monitor(self.process, self.result, self.log, "EditMode", "r", "s", self.launched,
                              self.identity, poll_seconds=0.01, idle_timeout=0.3, exit_grace=0.1, **kwargs)

    def test_successful_real_child(self):
        self.start(xml=xml_text())
        self.process.wait(timeout=5)
        self.assertEqual(self.observe()["status"], "passed")

    def test_complete_child_stuck_in_shutdown_is_stopped(self):
        self.start(xml=xml_text(), sleep=15, log="Input System module state changed to: ShutdownInProgress")
        result = self.observe()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["exit_state"], "terminated_after_results")
        self.assertIsNotNone(self.process.poll())

    def test_complete_child_without_shutdown_is_preserved(self):
        self.start(xml=xml_text(), sleep=15)
        self.assertEqual(self.observe()["status"], "blocked_process")
        self.assertIsNone(self.process.poll())

    def test_shutdown_before_results_is_not_exit_evidence(self):
        self.start(xml=xml_text(), sleep=15, log="initialization\nApplication is shutting down")
        self.assertEqual(self.observe()["status"], "blocked_process")
        self.assertIsNone(self.process.poll())

    def test_pid_identity_change_never_terminates(self):
        self.start(sleep=15)
        with patch.object(runner, "process_identity", return_value={"pid": self.process.pid, "created": "reused"}):
            self.assertFalse(runner.terminate_completed(self.process, self.identity, self.process.args))
        self.assertIsNone(self.process.poll())

    def test_no_result_or_crash_after_result_is_not_pass(self):
        self.start(xml=xml_text(), code=1)
        # 本用例验证非零退出码，避免模拟 sleep=0.1 与退出宽限=0.1 竞争。
        # 未退出进程的保留行为由独立用例覆盖。
        self.process.wait(timeout=5)
        self.assertEqual(self.observe()["status"], "incomplete")

    def test_zero_exit_without_result_is_not_pass(self):
        self.start()
        self.process.wait(timeout=5)
        self.assertEqual(self.observe()["status"], "incomplete")

    def test_stale_xml_is_not_pass(self):
        self.start(xml=xml_text(stale=True))
        self.process.wait(timeout=5)
        self.assertEqual(self.observe()["status"], "incomplete")

    def test_environment_failure_classification(self):
        self.start(code=1, log="Failed to resolve packages: No packages loaded.")
        self.assertEqual(self.observe()["failure_kind"], "package_resolution")

    def test_timeout_preserves_unfinished_child(self):
        self.start(sleep=15, log="Importing assets")
        self.assertEqual(self.observe()["exit_state"], "still_running")
        self.assertIsNone(self.process.poll())

    def test_same_workspace_has_exclusive_lock(self):
        path = self.root / "runner.lock"
        with core.exclusive(path):
            script = "import sys; sys.path.insert(0,sys.argv[1]); from handoff_core import exclusive; " \
                     "\nwith exclusive(sys.argv[2]): print('incorrectly acquired')"
            result = subprocess.run([sys.executable, "-B", "-c", script,
                                     str(Path(core.__file__).parent), str(path)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        with core.exclusive(path):
            pass


class WorkspaceTests(TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.root / "仓库 with spaces"
        self.repo.mkdir()
        self.source = self.repo / "Game"
        for name in core.INPUT_ROOTS:
            (self.source / name).mkdir(parents=True)
        (self.source / "Assets/asset.txt").write_text("asset", encoding="utf-8")
        (self.source / "Packages/manifest.json").write_text('{"dependencies": {}}')
        (self.source / "Packages/packages-lock.json").write_text('{"dependencies": {}}')
        (self.source / "ProjectSettings/ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.62f2c1\n")
        (self.repo / ".gitignore").write_text("Game/Library/\nGame/Temp/\n")
        core.git(self.repo, "init")
        core.git(self.repo, "config", "user.name", "Isolated Test")
        core.git(self.repo, "config", "user.email", "test@example.invalid")
        core.git(self.repo, "add", ".")
        core.git(self.repo, "commit", "-m", "fixture")
        self.target_root = self.root / "独立 验证"
        core.git(self.repo, "worktree", "add", "--detach", str(self.target_root), "HEAD")
        self.project = self.target_root / "Game"

    def work(self, **kwargs):
        return core.workspace(self.source, self.project, "tester-73", "Win64", **kwargs)

    def test_dirty_input_invalidates_same_head(self):
        one = core.snapshot(self.source, "all changes")
        (self.source / "Assets/asset.txt").write_text("changed", encoding="utf-8")
        two = core.snapshot(self.source, "all changes")
        self.assertEqual(one["commit"], two["commit"])
        self.assertNotEqual(one["input_snapshot_id"], two["input_snapshot_id"])
        self.assertNotEqual(one["dirty_snapshot_hash"], two["dirty_snapshot_hash"])
        self.assertTrue(one["files"]["Assets/asset.txt"].startswith("git:"))
        self.assertEqual(two["files"]["Assets/asset.txt"], core.file_hash(self.source / "Assets/asset.txt"))

    def test_committed_form_of_tested_bytes_can_be_verified(self):
        path = self.project / "Assets/asset.txt"
        path.write_text("tested change")
        tested = core.snapshot(self.project, "fixture")
        core.git(self.target_root, "add", "Game/Assets/asset.txt")
        core.git(self.target_root, "commit", "-m", "save tested bytes")
        current = core.snapshot(self.project, "fixture")
        self.assertTrue(core.snapshot_matches(tested, current, self.project))
        path.write_text("different bytes")
        self.assertFalse(core.snapshot_matches(tested, core.snapshot(self.project, "fixture"), self.project))

    def test_full_content_option_reads_clean_file_bytes(self):
        full = core.snapshot(self.project, "fixture", full_content=True)
        self.assertTrue(full["full_content"])
        self.assertEqual(full["files"]["Assets/asset.txt"], core.file_hash(self.project / "Assets/asset.txt"))

    def test_clean_cache_reuse_and_dependency_change(self):
        self.work(claim=True)
        (self.project / "Library").mkdir()
        self.assertEqual(self.work()["cache"], "incremental_candidate")
        (self.project / "Packages/packages-lock.json").write_text('{"dependencies": {"new": {}}}')
        self.assertEqual(self.work()["cache"], "requires_import_or_rebuild")

    def test_external_local_packages_are_not_silently_omitted(self):
        (self.project / "Packages/manifest.json").write_text('{"dependencies": {"custom": "file:../../external"}}')
        with self.assertRaisesRegex(core.HandoffError, "file:"):
            core.snapshot(self.project, "fixture")

    def test_unowned_dirty_project_and_source_are_blocked(self):
        (self.project / "Assets/unrelated.txt").write_text("preserve")
        with self.assertRaises(core.HandoffError):
            self.work(claim=True)
        self.assertEqual((self.project / "Assets/unrelated.txt").read_text(), "preserve")
        with self.assertRaises(core.HandoffError):
            core.workspace(self.source, self.source, "tester", "Win64")

    def test_active_editor_and_lockfile_block_without_deleting(self):
        for project in (self.project, None):
            with self.assertRaises(core.HandoffError):
                self.work(active_projects=[project])
        lock = self.project / "Temp/UnityLockfile"
        lock.parent.mkdir()
        lock.touch()
        with self.assertRaises(core.HandoffError):
            self.work()
        self.assertTrue(lock.exists())

    def test_linked_library_cannot_share_source_cache(self):
        source_library = self.source / "Library"
        source_library.mkdir()
        linked_library = self.project / "Library"
        if os.name == "nt":
            result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(linked_library), str(source_library)],
                                    capture_output=True)
            self.assertEqual(result.returncode, 0)
        else:
            linked_library.symlink_to(source_library, target_is_directory=True)
        with self.assertRaisesRegex(core.HandoffError, "禁止共享验证缓存"):
            self.work(claim=True)
        self.assertTrue(source_library.exists())

    def test_new_task_can_claim_only_clean_inactive_cache(self):
        self.work(claim=True)
        with self.assertRaises(core.HandoffError):
            core.workspace(self.source, self.project, "next-task", "Win64")
        (self.project / "Library").mkdir()
        receipt = core.workspace(self.source, self.project, "next-task", "Win64", claim=True)
        self.assertEqual(receipt["cache"], "incremental_candidate")
        self.assertTrue((self.project / "Library").is_dir())

    def prepare_run(self):
        self.work(claim=True)
        self.evidence = self.project / "Docs/SceneHandoffs/isolated-test"
        self.evidence.mkdir(parents=True)
        source_snapshot = core.snapshot(self.source, "all committed fixture files")
        core.write_json(self.evidence / "source.json", source_snapshot)
        core.write_json(self.evidence / "protection.json", {
            "task_id": "tester-73", "method": "isolated", "status": "prepared",
            "details": "仅启动模拟 Python 子进程；没有 Unity 和用户数据写入。"})
        self.plan = {"task_id": "tester-73", "source_commit": source_snapshot["commit"],
                     "source_snapshot": "source.json", "target_base_commit": source_snapshot["commit"],
                     "scope_authorization": "all fixture files", "target_platform": "Win64",
                     "protection_record": "protection.json",
                     "checks": [{"id": "edit", "mode": "EditMode", "reason": "isolated runner contract"}]}
        core.write_json(self.evidence / "plan.json", self.plan)
        core.write_json(self.evidence / "target.json", core.snapshot(self.project, "all fixture files"))
        return argparse.Namespace(source=self.source, project=self.project, plan=self.evidence / "plan.json",
                                  evidence=self.evidence, snapshot=self.evidence / "target.json", check="edit",
                                  editor=None, recovery_evidence=None, idle_timeout=2, test_timeout=2, exit_grace=0.2,
                                  allow_editor_launch=True)

    def fake_command(self, editor, project, check, result, log, *args):
        return [sys.executable, "-c", FAKE_CHILD, json.dumps({"result_path": str(result),
                "log_path": str(log), "xml": xml_text(), "sleep": 0.05})]

    def run_fake(self, args, command=None):
        with patch.object(runner, "editors", return_value=[]), \
             patch.object(runner, "locate_editor", return_value=Path(sys.executable)), \
             patch.object(runner, "command", side_effect=command or self.fake_command):
            return handoff.do_run(args)

    def test_end_to_end_run_resume_report_and_final_input_invalidation(self):
        args = self.prepare_run()
        source_before = core.snapshot(self.source, "source remains untouched")
        first = self.run_fake(args)
        self.assertEqual(first["status"], "passed")
        self.assertEqual(self.run_fake(args)["status"], "reused")
        core.write_json(self.evidence / "cleanup.json", {"task_id": "tester-73", "status": "complete",
                                                        "user_data_verified": True, "details": "No user data accessed"})
        core.write_json(self.evidence / "files.json", {"files": ["Assets/asset.txt"], "deleted": ["Assets/removed.txt"]})
        report_args = argparse.Namespace(project=self.project, evidence=self.evidence, plan=args.plan,
                    cleanup_record=self.evidence / "cleanup.json", files=self.evidence / "files.json",
                    output=self.evidence / "summary-1")
        self.assertEqual(handoff.do_summarize(report_args)["status"], "validation_complete")
        report_dir = Path(report_args.output)
        manifest = core.read_json(report_dir / "result-file-hashes.json")
        handoff.verify_manifest(self.project, manifest, report_dir)
        (report_dir / "验证结果与计时报告.md").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(core.HandoffError, "汇总报告/JSON 被修改"):
            handoff.verify_manifest(self.project, manifest, report_dir)
        self.assertEqual(core.snapshot(self.source, "unchanged")["input_snapshot_id"], source_before["input_snapshot_id"])
        with self.assertRaises(core.HandoffError):
            handoff.do_summarize(report_args)
        (self.project / "Assets/asset.txt").write_text("changed after testing")
        report_args.output = self.evidence / "summary-2"
        self.assertEqual(handoff.do_summarize(report_args)["missing_checks"], ["edit"])
        with self.assertRaises(core.HandoffError):
            self.run_fake(args)

    def test_same_environment_failure_stops_retry(self):
        args = self.prepare_run()
        def failing(editor, project, check, result, log, *other):
            return [sys.executable, "-c", FAKE_CHILD, json.dumps({"result_path": str(result),
                    "log_path": str(log), "log": "Failed to resolve packages: No packages loaded", "code": 1})]
        self.assertEqual(self.run_fake(args, failing)["status"], "environment_blocked")
        with self.assertRaisesRegex(core.HandoffError, "相同输入/环境已有失败"):
            self.run_fake(args, failing)

    def test_modified_result_is_not_reused(self):
        args = self.prepare_run()
        first = self.run_fake(args)
        (self.evidence / first["result_file"]).write_text("{}")
        with self.assertRaisesRegex(core.HandoffError, "哈希不一致"):
            self.run_fake(args)

    def test_head_advance_cannot_leave_resume_stuck_on_old_record(self):
        args = self.prepare_run()
        first = self.run_fake(args)
        (self.target_root / "description.md").write_text("documentation only")
        core.git(self.target_root, "add", "description.md")
        core.git(self.target_root, "commit", "-m", "documentation")
        updated = core.snapshot(self.project, "fixture")
        core.write_json(args.snapshot, updated, replace=True)
        second = self.run_fake(args)
        self.assertEqual(second["status"], "passed")
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(second["target_commit"], updated["commit"])

    def test_restored_side_effect_needs_exact_attribution(self):
        args = self.prepare_run()
        first = self.run_fake(args)
        directory = self.evidence / "validation" / first["run_id"]
        first["status"] = "inputs_changed"
        first["validation_status"] = "passed"
        first["record_file"] = (directory / "run.json").relative_to(self.evidence).as_posix()
        before = core.read_json(directory / "inputs.json")
        after = core.read_json(directory / "inputs-after.json")
        after["files"]["Assets/asset.txt"] = "side-effect-hash"
        core.write_json(directory / "inputs-after.json", after, replace=True)
        params = ([first], self.project, self.evidence, first["check"], first["plan_hash"], first["input_snapshot_id"])
        self.assertIsNone(handoff.restored_run(*params, {}))
        proof = {"restored_files": {"Assets/asset.txt": {"run_id": first["run_id"],
                 "before_identity": before["files"]["Assets/asset.txt"], "after_test_identity": "side-effect-hash",
                 "attribution": "已确认由该测试生成，精确恢复原字节"}}}
        self.assertEqual(handoff.restored_run(*params, proof)["run_id"], first["run_id"])
        proof["restored_files"]["Assets/asset.txt"]["before_identity"] = "wrong"
        self.assertIsNone(handoff.restored_run(*params, proof))


if __name__ == "__main__":
    unittest.main(verbosity=2)
