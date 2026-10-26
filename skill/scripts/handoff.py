"""gm-scene-handoff 辅助命令。使用 --help 查看入口；不合并、不提交、不推送。"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True

from handoff_core import (HandoffError, VERSION, compatibility, digest, exclusive, file_hash,
                          git, inside, load_plan, local_state, now, project_info,
                          protection_record, read_json, snapshot, workspace, write_json)
from handoff_core import snapshot_matches
import unity_runner as runner


def run_records(evidence):
    records = []
    for path in sorted((Path(evidence) / "validation").glob("*/run.json")):
        record = read_json(path)
        record["record_file"] = path.relative_to(evidence).as_posix()
        records.append(record)
    return sorted(records, key=lambda r: datetime.fromisoformat(r["started_at"]).timestamp())


def result_for(project, evidence, record):
    path = inside(evidence, record["result_file"])
    if file_hash(path) != record["result_sha256"]:
        raise HandoffError("验证结果摘要哈希不一致：" + record["result_file"])
    data = read_json(path)
    if data.get("raw_sha256"):
        raw = inside(project, record["raw_result"])
        if not raw.is_file() or file_hash(raw) != data["raw_sha256"]:
            raise HandoffError("原始结果缺失或被修改：" + record["raw_result"])
    return data


def matching_run(records, project, evidence, check, plan_hash, inputs):
    candidates = [r for r in records if r["check"] == check and r["plan_hash"] == plan_hash
                  and r["input_snapshot_id"] == inputs]
    if not candidates:
        return None
    latest = candidates[-1]
    result = result_for(project, evidence, latest)
    # 后来的失败不能被早先的通过遮盖。
    return latest if latest["status"] == "passed" and result["status"] == "passed" else None


def plan_identity(evidence, plan):
    protected = protection_record(evidence, plan)
    source_path = inside(evidence, plan["source_snapshot"])
    source = read_json(source_path)
    if (source["commit"] != plan["source_commit"]
            or source["dirty_snapshot_hash"] != digest(source["dirty_files"])
            or source["input_snapshot_id"] != digest({"files": source["files"], "tools": source["tools"]})):
        raise HandoffError("来源快照与计划或内容哈希不一致")
    return digest({"plan": plan, "protection_sha256": protected,
                   "source_snapshot_sha256": file_hash(source_path)})


def do_workspace(args):
    active = runner.editors()
    info = project_info(args.project)
    if args.claim:
        with exclusive(local_state(info) / "runner.lock"):
            return workspace(args.source, args.project, args.task_id, args.platform,
                             claim=True, active_projects=[r["project"] for r in active])
    return workspace(args.source, args.project, args.task_id, args.platform,
                     active_projects=[r["project"] for r in active])


def do_preflight(args):
    plan = load_plan(args.plan)
    active = runner.editors()
    inspection = workspace(args.source, args.project, plan["task_id"], plan["target_platform"],
                           active_projects=[r["project"] for r in active])
    editor = runner.locate_editor(args.project, args.editor, active)
    _, diagnostics = runner.child_environment()
    plan_identity(args.evidence, plan)
    return {"workspace": inspection, "editor_version": runner.editor_version(editor),
            "environment": diagnostics, "status": "ready" if inspection["registered"] else "needs_claim"}


def do_run(args):
    if not getattr(args, "allow_editor_launch", False):
        raise HandoffError("默认保持当前 Unity 打开；使用 editor-begin/editor-finish。旧批处理仅在另行授权启动 Editor 后显式使用 --allow-editor-launch")
    plan = load_plan(args.plan)
    checks = [check for check in plan["checks"] if check["id"] == args.check]
    if len(checks) != 1:
        raise HandoffError("计划中找不到唯一的检查 ID")
    check = checks[0]
    if check.get("backend", "batch") != "batch":
        raise HandoffError("editor_mcp 检查不可通过批处理启动")
    info = project_info(args.project)
    evidence = Path(args.evidence).resolve()
    # 证据必须位于目标项目中；原始日志只写入该目标自己的 Library。
    if not evidence.is_relative_to(info["project"] / "Docs/SceneHandoffs"):
        raise HandoffError("证据目录须位于目标项目 Docs/SceneHandoffs 下")
    with exclusive(local_state(info) / "runner.lock"):
        tick, began = time.monotonic(), now()
        active = runner.editors()
        inspection = workspace(args.source, args.project, plan["task_id"], plan["target_platform"],
                               active_projects=[r["project"] for r in active])
        if not inspection["registered"]:
            raise HandoffError("先在干净工作区执行 workspace --claim，再应用本轮变更")
        editor = runner.locate_editor(args.project, args.editor, active)
        env, diagnostics = runner.child_environment()
        plan_hash = plan_identity(evidence, plan)
        for commit in (plan["source_commit"], plan["target_base_commit"]):
            git(args.project, "cat-file", "-e", commit + "^{commit}")
        expected = read_json(args.snapshot)
        full_content = plan.get("full_content_snapshot", False)
        if expected.get("full_content", False) != full_content:
            raise HandoffError("目标快照与计划的全量字节核验选项不一致")
        current = snapshot(args.project, plan["scope_authorization"], full_content=full_content)
        if expected["input_snapshot_id"] != current["input_snapshot_id"]:
            raise HandoffError("目标输入已变；更新验证计划/快照后再运行")
        if expected["commit"] != current["commit"]:
            raise HandoffError("目标 HEAD 已前移；先复核基线和快照")
        previous = matching_run(run_records(evidence), args.project, evidence, check,
                                plan_hash, current["input_snapshot_id"])
        if previous and previous["target_commit"] == current["commit"]:
            return {"status": "reused", "run_id": previous["run_id"],
                    "record_file": previous["record_file"], "reason": "输入、计划及结果哈希匹配"}
        env_keys = ("ALLUSERSPROFILE", "PROGRAMDATA", "TEMP", "TMP", "USERPROFILE", "PATH")
        fingerprint = digest({"inputs": current["input_snapshot_id"],
                              "check": check, "purpose": plan.get("purpose", "final"),
                              "editor": file_hash(editor),
                              "environment": {k: env.get(k) for k in env_keys},
                              "recovery_evidence": file_hash(args.recovery_evidence)
                              if args.recovery_evidence else None})
        state_dir = local_state(info)
        attempts = [read_json(p) for p in sorted((state_dir / "attempts").glob("*.json"))]
        if any(a.get("fingerprint") == fingerprint and a.get("failure_kind") for a in attempts):
            raise HandoffError("相同输入/环境已有失败；先诊断并改变条件，不重复启动")
        run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
        portable = evidence / "validation" / run_id
        portable.mkdir(parents=True, exist_ok=False)
        raw_dir = info["project"] / "Library/HandoffValidation" / run_id
        raw_dir.mkdir(parents=True, exist_ok=False)
        result = raw_dir / ("result.json" if check["mode"] == "audit" else "results.xml")
        log = raw_dir / "editor.log"
        write_json(portable / "inputs.json", current)
        write_json(portable / "plan.json", plan)
        args_list = runner.command(editor, info["project"], check, result, log, run_id,
                                   current["input_snapshot_id"], plan["target_platform"])
        # 输入扫描可能较久，启动前重新检查 Unity 占用，缩小竞争窗口。
        workspace(args.source, args.project, plan["task_id"], plan["target_platform"],
                  active_projects=[r["project"] for r in runner.editors()])
        started_epoch = time.time()
        attempt_path = state_dir / "attempts" / (run_id + ".json")
        attempt = {"run_id": run_id, "fingerprint": fingerprint, "started_at": began,
                   "project": str(info["project"]), "arguments": args_list, "status": "launching"}
        write_json(attempt_path, attempt)
        try:
            process = subprocess.Popen(args_list, env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            attempt["pid"] = process.pid
            write_json(attempt_path, attempt, replace=True)
            identity = runner.process_identity(process)
        except Exception as exc:
            attempt.update(status="launch_failed", failure_kind="launch_failed", error=type(exc).__name__)
            write_json(attempt_path, attempt, replace=True)
            raise HandoffError("启动/进程身份记录失败，保留本机尝试记录；先检查目标占用") from exc
        attempt.update(process=identity, status="running")
        write_json(attempt_path, attempt, replace=True)
        try:
            observed = runner.monitor(process, result, log, check["mode"], run_id,
                                      current["input_snapshot_id"], started_epoch, identity,
                                      idle_timeout=args.idle_timeout, test_timeout=args.test_timeout,
                                      exit_grace=args.exit_grace, min_tests=check.get("min_tests", 1))
        except KeyboardInterrupt:
            observed = {"status": "interrupted", "result": None, "exit_state": "unknown",
                        "failure_kind": "interrupted", "reason": "中断后保留 Editor，续跑先检查占用"}
        except Exception as exc:
            observed = {"status": "runner_error", "result": None, "exit_state": "unknown",
                        "failure_kind": "runner_error", "reason": type(exc).__name__}
        attempt.update({k: v for k, v in observed.items() if k != "result"})
        write_json(attempt_path, attempt, replace=True)
        result_summary = observed.pop("result") or {"status": "incomplete", "tests": []}
        write_json(portable / "result.json", result_summary)
        # 这里只核对输入，不自动恢复任何用户文件。恢复后汇总时再校验最终输入。
        after = None
        if observed["exit_state"] in ("exited", "terminated_after_results"):
            try:
                after = snapshot(args.project, plan["scope_authorization"], full_content=full_content)
            except HandoffError as exc:
                observed["status"] = "inputs_unstable"
                observed["reason"] = "运行后输入扫描失败，请检查并行写入或未支持的依赖"
        if after:
            write_json(portable / "inputs-after.json", after)
        record = {"schema_version": 1, "tool_version": VERSION, "run_id": run_id,
                  "task_id": plan["task_id"], "check": check, "plan_hash": plan_hash,
                  "input_snapshot_id": current["input_snapshot_id"],
                  "target_commit": current["commit"], "started_at": began, "ended_at": now(),
                  "total_elapsed_ms": round((time.monotonic() - tick) * 1000),
                  "snapshot_elapsed_ms": current["elapsed_ms"], "environment": diagnostics,
                  "cache": inspection["cache"], "process_id": identity["pid"],
                  "process_created": identity["created"], "mode": check["mode"],
                  "raw_result": result.relative_to(info["project"]).as_posix(),
                  "raw_log": log.relative_to(info["project"]).as_posix(),
                  "result_file": (portable / "result.json").relative_to(evidence).as_posix(),
                  "result_sha256": file_hash(portable / "result.json"),
                  "validation_status": observed["status"],
                  "inputs_changed_during_run": after is not None and after["input_snapshot_id"] != current["input_snapshot_id"],
                  **observed}
        if record["inputs_changed_during_run"]:
            record["status"] = "inputs_changed"
        write_json(portable / "run.json", record)
        if record["status"] == "passed":
            receipt = read_json(state_dir / "workspace.json")
            receipt["last_validated_compatibility"] = compatibility(args.project, plan["target_platform"])
            write_json(state_dir / "workspace.json", receipt, replace=True)
        return record


def manifest(project, selected):
    path_base = selected.get("path_base", "project")
    if path_base not in ("project", "repository"):
        raise HandoffError("清单 path_base 仅支持 project 或 repository")
    root = project_info(project)["root"] if path_base == "repository" else Path(project)
    files, deleted = selected.get("files", []), selected.get("deleted", [])
    if len(files) != len(set(files)) or len(deleted) != len(set(deleted)) or set(files) & set(deleted):
        raise HandoffError("交付文件清单有重复或新增/删除冲突")
    values = {}
    for name in files:
        path = inside(root, name)
        if not path.is_file():
            raise HandoffError("交付文件不存在：" + name)
        values[name] = file_hash(path)
    for name in deleted:
        if inside(root, name).exists():
            raise HandoffError("预期删除文件仍存在：" + name)
    return {"schema_version": 1, "path_base": path_base, "files": values, "deleted": deleted}


def verify_manifest(project, data, summary_dir=None):
    validation_status = None
    if summary_dir:
        summary_dir = Path(summary_dir)
        for name, expected in read_json(summary_dir / "summary-hashes.json").items():
            if file_hash(core_path := inside(summary_dir, name)) != expected:
                raise HandoffError("汇总报告/JSON 被修改：" + core_path.name)
        summary = read_json(summary_dir / "test-results.json")
        tested = read_json(summary_dir / "tested-inputs.json")
        current = snapshot(project, "只读核验交付输入", full_content=tested.get("full_content", False))
        if not snapshot_matches(tested, current, project):
            raise HandoffError("最终运行输入与汇总报告不一致")
        validation_status = summary["status"]
    actual = manifest(project, {"path_base": data.get("path_base", "project"),
                                "files": list(data["files"]), "deleted": data["deleted"]})
    changed = [name for name, value in actual["files"].items() if data["files"][name] != value]
    if changed:
        raise HandoffError("结果文件哈希不一致：" + ", ".join(changed))
    return {"status": "validation_incomplete" if validation_status == "validation_incomplete" else "passed",
            "validation_status": validation_status, "files_checked": len(actual["files"]),
            "deletions_checked": len(actual["deleted"])}


def restored_run(records, project, evidence, check, plan_hash, inputs, cleanup):
    """仅接受有逐文件归因记录、且已精确恢复到受测输入的副作用。"""
    candidates = [r for r in records if r["check"] == check and r["plan_hash"] == plan_hash
                  and r["input_snapshot_id"] == inputs]
    if not candidates:
        return None
    record = candidates[-1]
    if record["status"] != "inputs_changed" or record.get("validation_status") != "passed":
        return None
    if result_for(project, evidence, record)["status"] != "passed":
        return None
    directory = inside(evidence, record["record_file"]).parent
    before_snapshot = read_json(directory / "inputs.json")
    after_snapshot = read_json(directory / "inputs-after.json")
    if (before_snapshot.get("commit") != after_snapshot.get("commit")
            or before_snapshot.get("branch") != after_snapshot.get("branch")):
        return None
    before = before_snapshot["files"]
    after = after_snapshot["files"]
    changes = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    restored = cleanup.get("restored_files", {})
    for name in changes:
        proof = restored.get(name, {})
        if (proof.get("before_identity") != before.get(name) or proof.get("after_test_identity") != after.get(name)
                or proof.get("run_id") != record["run_id"] or not proof.get("attribution")):
            return None
    return record


def do_summarize(args):
    plan = load_plan(args.plan)
    if plan.get("purpose", "final") != "final":
        raise HandoffError("诊断计划不能作为最终交付汇总")
    evidence = Path(args.evidence).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise HandoffError("汇总输出目录已存在；使用新的结果目录，保留历史证据")
    if not output.is_relative_to(evidence):
        raise HandoffError("汇总输出须位于本轮证据目录内")
    plan_hash = plan_identity(evidence, plan)
    cleanup = read_json(args.cleanup_record)
    if (cleanup.get("task_id") != plan["task_id"] or cleanup.get("status") != "complete"
            or not cleanup.get("details") or cleanup.get("user_data_verified") is not True):
        raise HandoffError("先完成本轮副作用恢复并提供用户数据核验记录")
    current = snapshot(args.project, plan["scope_authorization"],
                       full_content=plan.get("full_content_snapshot", False))
    records = run_records(evidence)
    effective, missing, tests = [], [], {}
    for check in plan["checks"]:
        record = matching_run(records, args.project, evidence, check, plan_hash, current["input_snapshot_id"])
        if not record:
            record = restored_run(records, args.project, evidence, check, plan_hash,
                                  current["input_snapshot_id"], cleanup)
        if (not record or record["target_commit"] != current["commit"]
                or ("target_branch" in record and record["target_branch"] != current["branch"])):
            missing.append(check["id"])
            continue
        effective.append(record["run_id"])
        for test in result_for(args.project, evidence, record)["tests"]:
            tests[check["mode"] + ":" + test["name"]] = {**test, "run": record["run_id"],
                                                         "input_snapshot_id": current["input_snapshot_id"]}
    status = "validation_complete" if not missing else "validation_incomplete"
    selected = manifest(args.project, read_json(args.files))
    project = Path(args.project).resolve()
    manifest_root = project_info(project)["root"] if selected["path_base"] == "repository" else project
    evidence_files = [Path(args.plan).resolve(), Path(args.cleanup_record).resolve(),
                      inside(evidence, plan["source_snapshot"]), inside(evidence, plan["protection_record"])]
    for record in records:
        directory = inside(evidence, record["record_file"]).parent
        evidence_files.extend(p for p in directory.iterdir() if p.is_file())
    for path in evidence_files:
        if not path.is_relative_to(project):
            raise HandoffError("便携汇总依赖必须放在目标项目内")
        selected["files"][path.relative_to(manifest_root).as_posix()] = file_hash(path)
    summaries = []
    for record in records:
        data = result_for(args.project, evidence, record)
        summaries.append({"file": record["result_file"], "run_id": record["run_id"],
                          "status": record["status"], "input_snapshot_id": record["input_snapshot_id"],
                          "total": data.get("total", 0), "passed": data.get("passed", 0),
                          "failed": data.get("failed", 0), "duration": data.get("duration"),
                          "started_at": record["started_at"], "ended_at": record["ended_at"],
                          "elapsed_ms": record["total_elapsed_ms"], "exit_state": record["exit_state"],
                          "timing": record.get("timing")})
    payload = {"schema_version": 1, "task_id": plan["task_id"], "status": status,
               "source_commit": plan["source_commit"], "target_base_commit": plan["target_base_commit"],
               "target_commit": current["commit"], "input_snapshot_id": current["input_snapshot_id"],
               "plan_hash": plan_hash, "runs": summaries, "effective_run_ids": effective,
               "effective_count": len(tests), "effective_passed": len(tests),
               "effective_failed": [], "effective_tests": tests, "missing_checks": missing,
               "cleanup_sha256": file_hash(args.cleanup_record), "created_at": now(),
               "limitations": ["只汇总计划内验证；场景迁移完整性和人工验收仍按原流程核对。",
                               "不跨输入快照拼接旧通过项；跳过/未决/零用例不算通过。",
                               "原始 XML/审计 JSON 和日志保存在目标 Library；跨机器交付另行脱敏归档。"]}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "tested-inputs.json", current)
    write_json(output / "test-results.json", payload)
    write_json(output / "result-file-hashes.json", selected)
    lines = ["# 验证结果与计时报告", "", f"状态：{status}", "",
             f"固定来源：`{plan['source_commit']}`；目标基线：`{plan['target_base_commit']}`。",
             f"目标输入快照：`{current['input_snapshot_id']}`。",
             f"有效用例：{len(tests)}；尚无有效结果的计划项：{', '.join(missing) or '无'}。", "",
             "| 运行 | 状态 | 用例通过/总数 | 总耗时（秒） | 退出状态 |",
             "|---|---|---|---:|---|"]
    for row in summaries:
        lines.append(f"| {row['run_id']} | {row['status']} | {row['passed']}/{row['total']} | "
                     f"{row['elapsed_ms'] / 1000:.3f} | {row['exit_state']} |")
    lines += ["", "耗时包含快照、预检和进程等待；XML duration 单列于 JSON，不能把并行或嵌套阶段简单相加。",
              "退出异常保留于表中。该报告不声明已提交、已推送、人工验收通过或全部场景无回归。", "",
              *["- " + text for text in payload["limitations"]], ""]
    (output / "验证结果与计时报告.md").write_text("\n".join(lines), encoding="utf-8")
    # 便携摘要自身的校验使用另一份清单，避免自引用。
    write_json(output / "summary-hashes.json", {p.name: file_hash(p) for p in sorted(output.iterdir()) if p.is_file()})
    return {"status": status, "effective_count": len(tests), "missing_checks": missing,
            "output": output.relative_to(evidence).as_posix()}


def positive(value):
    value = float(value)
    if value <= 0 or not math.isfinite(value):
        raise argparse.ArgumentTypeError("时间必须大于零")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    from handoff_steps import add_commands, dispatch as step_dispatch, COMMANDS
    add_commands(commands)
    files = commands.add_parser("manifest", help="按 project/repository 显式根生成交付清单")
    for field in ("project", "files", "output"):
        files.add_argument("--" + field, required=True)
    scenes = commands.add_parser("scenes", help="固定提交中动态发现全部编号场景对")
    scenes.add_argument("--project", required=True)
    scenes.add_argument("--author", required=True)
    scenes.add_argument("--refs", nargs="+", required=True)
    for name in ("editor-begin", "editor-finish", "editor-cancel"):
        editor_parser = commands.add_parser(name, help="复用当前 Editor 的 MCP 验证证据；不启动或关闭 Unity")
        for field in ("project", "evidence"):
            editor_parser.add_argument("--" + field, required=True)
        if name == "editor-begin":
            editor_parser.add_argument("--recovery-evidence", help="环境修复记录；不得用空说明绕过重试限制")
            for field in ("plan", "check", "session"):
                editor_parser.add_argument("--" + field, required=True)
        else:
            editor_parser.add_argument("--run-id", required=True)
            fields = ("session", "dispatch", "result") if name == "editor-finish" else ("reason",)
            for field in fields:
                editor_parser.add_argument("--" + field, required=True)
    snap = commands.add_parser("snapshot", help="固定实际输入及未提交文件哈希")
    snap.add_argument("--project", required=True)
    snap.add_argument("--scope", required=True)
    snap.add_argument("--output", required=True)
    snap.add_argument("--full-content", action="store_true", help="读取全部输入字节；大项目仅按需使用")
    work = commands.add_parser("workspace", help="检查/登记独立 worktree；不创建、重置或复制缓存")
    work.add_argument("--source", required=True)
    work.add_argument("--project", required=True)
    work.add_argument("--task-id", required=True)
    work.add_argument("--platform", required=True)
    work.add_argument("--claim", action="store_true")
    for name in ("preflight", "run"):
        command_parser = commands.add_parser(name)
        for field in ("source", "project", "plan", "evidence"):
            command_parser.add_argument("--" + field, required=True)
        command_parser.add_argument("--editor")
        if name == "run":
            command_parser.add_argument("--allow-editor-launch", action="store_true",
                                        help="仅另行授权的旧隔离批处理；两个原目录合并入口禁止使用")
            command_parser.add_argument("--snapshot", required=True)
            command_parser.add_argument("--check", required=True)
            command_parser.add_argument("--recovery-evidence")
            command_parser.add_argument("--idle-timeout", type=positive, default=600)
            command_parser.add_argument("--test-timeout", type=positive, default=1800)
            command_parser.add_argument("--exit-grace", type=positive, default=45)
    report = commands.add_parser("summarize")
    for field in ("project", "evidence", "plan", "cleanup-record", "files", "output"):
        report.add_argument("--" + field, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--project", required=True)
    verify.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in COMMANDS:
            result = step_dispatch(args)
        elif args.command == "manifest":
            selected = manifest(args.project, read_json(args.files))
            write_json(args.output, selected)
            result = {"status": "passed", "path_base": selected["path_base"],
                      "files_checked": len(selected["files"]), "output": args.output}
        elif args.command == "scenes":
            from handoff_core import scene_pairs
            result = scene_pairs(args.project, args.author, args.refs)
        elif args.command.startswith("editor-"):
            import editor_validation
            result = {"editor-begin": editor_validation.begin,
                      "editor-finish": editor_validation.finish,
                      "editor-cancel": editor_validation.cancel}[args.command](args)
            if args.command == "editor-finish":
                result = {key: result[key] for key in ("status", "run_id", "validation_status",
                          "inputs_changed_during_run", "result_file", "timing")}
        elif args.command == "snapshot":
            result = snapshot(args.project, args.scope, full_content=args.full_content)
            write_json(args.output, result)
            result = {k: result[k] for k in ("input_snapshot_id", "dirty_snapshot_hash", "elapsed_ms")}
        elif args.command == "workspace":
            result = do_workspace(args)
        elif args.command == "preflight":
            result = do_preflight(args)
        elif args.command == "run":
            result = do_run(args)
        elif args.command == "summarize":
            result = do_summarize(args)
        else:
            directory = Path(args.manifest).resolve().parent
            result = verify_manifest(args.project, read_json(args.manifest),
                                     directory if (directory / "summary-hashes.json").is_file() else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status", "passed") in ("passed", "ready", "reused", "validation_complete") else 2
    except (HandoffError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
