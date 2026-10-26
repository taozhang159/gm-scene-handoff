"""接入当前 Editor 的 MCP 证据；不启动、关闭 Editor，不修改场景或 Git。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import math
from pathlib import Path
import time
import uuid

from handoff_core import (HandoffError, VERSION, digest, exclusive, file_hash, inside,
                          load_plan, local_state, now, project_info, read_json,
                          snapshot, write_json)


def session_observation(path, project, requirements):
    """读取由当前 MCP 实测采集的会话；不把计划声明当作能力证明。"""
    value = read_json(path)
    if (not value.get("project_path")
            or Path(value["project_path"]).resolve() != Path(project).resolve()
            or any(not isinstance(value.get(k), str) or not value[k].strip()
                   for k in ("session_id", "instance_id"))):
        raise HandoffError("MCP 会话缺少身份或连接到其他项目")
    stamp = datetime.fromisoformat(value["observed_at"])
    if stamp.utcoffset() is None or not 0 <= time.time() - stamp.timestamp() <= 120:
        raise HandoffError("Editor 状态不是最近 120 秒内的实测结果")
    for key in ("playing", "compiling", "updating", "dirty_scenes"):
        if value.get(key) is not False:
            raise HandoffError("Editor 未就绪：" + key)
    capabilities = value.get("capabilities", {})
    for name, needed in requirements.items():
        if needed and capabilities.get(name) is not True:
            raise HandoffError("当前 Editor 未证明测试能力：" + name)
    return value


def check_for(plan, check_id):
    checks = [c for c in plan["checks"] if c["id"] == check_id]
    if len(checks) != 1 or checks[0].get("backend") != "editor_mcp":
        raise HandoffError("editor-begin 需要唯一的 editor_mcp 检查项")
    check = checks[0]
    if check["mode"] not in ("EditMode", "PlayMode"):
        raise HandoffError("当前 MCP 适配器只接入 EditMode/PlayMode 完整用例结果")
    return check


def begin(args):
    # 延迟导入避免与 CLI 的循环导入，并复用原有结果身份协议。
    from handoff import plan_identity, matching_run, run_records
    plan = load_plan(args.plan)
    check = check_for(plan, args.check)
    info = project_info(args.project)
    evidence = Path(args.evidence).resolve()
    if not evidence.is_relative_to(info["project"] / "Docs/SceneHandoffs"):
        raise HandoffError("证据目录须位于项目 Docs/SceneHandoffs 下")
    with exclusive(local_state(info) / "runner.lock"):
        observed = session_observation(args.session, args.project, check.get("requirements", {}))
        plan_hash = plan_identity(evidence, plan)
        directory = evidence / "validation"
        # 已有未收口作业时立即返回，避免先扫描整组输入后才发现不能调度。
        for path in directory.glob("*/ticket.json"):
            if not path.with_name("run.json").exists():
                raise HandoffError("仍有未收口的 Editor 检查；先接回结果或记录中断：" + path.parent.name)
        inputs = snapshot(args.project, plan["scope_authorization"],
                          full_content=plan.get("full_content_snapshot", False))
        # 扫描期间 Editor 可能进入编译/导入；实际调度前须再核验并保持同一会话。
        records = run_records(evidence)
        previous = matching_run(records, args.project, evidence, check,
                                plan_hash, inputs["input_snapshot_id"])
        if (previous and previous["target_commit"] == inputs["commit"]
                and previous.get("target_branch") == inputs["branch"]):
            return {"status": "reused", "run_id": previous["run_id"]}
        failed = [r for r in records if r["check"] == check and r["plan_hash"] == plan_hash
                  and r["input_snapshot_id"] == inputs["input_snapshot_id"] and r["status"] == "failed"]
        recovery_hash = None
        if failed:
            recovery_path = getattr(args, "recovery_evidence", None)
            if not recovery_path:
                raise HandoffError("相同检查/输入已有失败；先定向诊断或提供真实环境修复记录")
            recovery = read_json(recovery_path)
            if (recovery.get("task_id") != plan["task_id"]
                    or recovery.get("failed_run_id") != failed[-1]["run_id"]
                    or not recovery.get("details") or not recovery.get("evidence")):
                raise HandoffError("环境修复记录缺少任务、失败运行或实际修复证据")
            recovery_hash = file_hash(recovery_path)
            if any(r.get("recovery_sha256") == recovery_hash for r in failed):
                raise HandoffError("相同修复条件下仍然失败，不能无变化重试")
        run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
        portable = directory / run_id
        write_json(portable / "inputs.json", inputs)
        write_json(portable / "plan.json", plan)
        ticket = {"run_id": run_id, "task_id": plan["task_id"], "check": check,
                  "plan_hash": plan_hash, "target_commit": inputs["commit"],
                  "target_branch": inputs["branch"], "project_path": info["project_path"],
                  "input_snapshot_id": inputs["input_snapshot_id"],
                  "inputs_sha256": file_hash(portable / "inputs.json"),
                  "recovery_sha256": recovery_hash,
                  "session_id": observed["session_id"], "instance_id": observed["instance_id"],
                  "session_observation_sha256": file_hash(args.session), "started_at": now()}
        write_json(portable / "ticket.json", ticket)
        return {"status": "ready", "run_id": run_id,
                "ticket": (portable / "ticket.json").relative_to(evidence).as_posix(),
                "note": "通过同一 MCP 会话运行指定检查，保存调度响应和完整 get_test_job 原始结果。"}


def job_result(job, dispatch, ticket):
    """支持 Coplay get_test_job 的原始 data 对象，不接受手写 passed 摘要。"""
    check = ticket["check"]
    if (not dispatch.get("job_id") or job.get("job_id") != dispatch["job_id"]
            or job.get("mode") != check["mode"]):
        raise HandoffError("MCP 作业 ID 或测试模式不符")
    began = datetime.fromisoformat(ticket["started_at"]).timestamp() * 1000
    start, end = job.get("started_unix_ms"), job.get("finished_unix_ms")
    if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
            or not math.isfinite(start) or not math.isfinite(end)
            or not began <= start <= end <= time.time() * 1000 + 1000):
        raise HandoffError("MCP 结果过期、尚未结束或时间身份不符")
    if job.get("status") not in ("succeeded", "failed"):
        raise HandoffError("MCP 作业尚未完成")
    result = job.get("result") or {}
    if result.get("mode") != check["mode"]:
        raise HandoffError("结果模式与计划不符")
    tests = result.get("results") or []
    names = [t.get("fullName") for t in tests]
    expected = check["expected_tests"]
    if len(names) != len(set(names)) or set(names) != set(expected):
        raise HandoffError("实际用例与运行前确定的完整用例清单不符（缺失、重复或额外用例）")
    counts = Counter(t.get("state") for t in tests)
    summary = result.get("summary") or {}
    if (not tests or len(tests) < check.get("min_tests", 1)
            or summary.get("total") != len(tests)
            or summary.get("passed") != counts["Passed"]
            or summary.get("failed") != counts["Failed"]
            or summary.get("skipped") != len(tests) - counts["Passed"] - counts["Failed"]):
        raise HandoffError("MCP 用例数或汇总计数不一致")
    duration = summary.get("durationSeconds")
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
        raise HandoffError("MCP 用例耗时无效")
    passed = (job["status"] == "succeeded" and not job.get("error")
              and summary.get("resultState") == "Passed" and counts["Passed"] == len(tests))
    return {"status": "passed" if passed else "failed", "total": len(tests),
            "passed": counts["Passed"], "failed": counts["Failed"],
            "skipped": summary["skipped"], "duration": duration,
            "tests": [{"name": t["fullName"], "result": t["state"],
                       "duration": t.get("durationSeconds")} for t in tests]}


def finish(args):
    from handoff import plan_identity
    info = project_info(args.project)
    evidence = Path(args.evidence).resolve()
    if not evidence.is_relative_to(info["project"] / "Docs/SceneHandoffs"):
        raise HandoffError("证据目录须位于项目 Docs/SceneHandoffs 下")
    portable = inside(evidence, "validation/" + args.run_id)
    with exclusive(local_state(info) / "runner.lock"):
        if (portable / "run.json").exists():
            raise HandoffError("此运行已收口；不覆盖原始结果")
        ticket = read_json(portable / "ticket.json")
        plan = read_json(portable / "plan.json")
        if ticket["run_id"] != args.run_id or file_hash(portable / "inputs.json") != ticket["inputs_sha256"]:
            raise HandoffError("运行票据/输入快照已损坏")
        if plan_identity(evidence, plan) != ticket["plan_hash"] or ticket["check"] != check_for(plan, ticket["check"]["id"]):
            raise HandoffError("运行计划或来源证据已变化")
        observed = session_observation(args.session, args.project, {})
        if (ticket["project_path"] != info["project_path"]
                or observed["session_id"] != ticket["session_id"]
                or observed["instance_id"] != ticket["instance_id"]):
            raise HandoffError("MCP 会话已切换；不能接纳另一个 Editor 的结果")
        job, dispatch = read_json(args.result), read_json(args.dispatch)
        # 归档原始 JSON，摘要哈希绑定原始结果；不丢弃失败和跳过项。
        for name, value in (("mcp-job.json", job), ("mcp-dispatch.json", dispatch)):
            path = portable / name
            if path.exists():
                if read_json(path) != value:
                    raise HandoffError("不能覆盖已归档的原始作业证据")
            else:
                write_json(path, value)
        summary = job_result(job, dispatch, ticket)
        summary["raw_sha256"] = file_hash(portable / "mcp-job.json")
        after = snapshot(args.project, plan["scope_authorization"],
                         full_content=plan.get("full_content_snapshot", False))
        write_json(portable / "result.json", summary)
        write_json(portable / "inputs-after.json", after)
        changed = (after["input_snapshot_id"] != ticket["input_snapshot_id"]
                   or after["commit"] != ticket["target_commit"]
                   or after["branch"] != ticket["target_branch"])
        record = {**ticket, "schema_version": 1, "tool_version": VERSION,
                  "backend": "editor_mcp", "purpose": plan.get("purpose", "final"),
                  "mode": ticket["check"]["mode"], "ended_at": now(),
                  "total_elapsed_ms": round((time.time() - datetime.fromisoformat(ticket["started_at"]).timestamp()) * 1000),
                  "job_id": job["job_id"], "exit_state": "editor_kept_open",
                  "session_after_sha256": file_hash(args.session),
                  "raw_result": (portable / "mcp-job.json").relative_to(info["project"]).as_posix(),
                  "result_file": (portable / "result.json").relative_to(evidence).as_posix(),
                  "result_sha256": file_hash(portable / "result.json"),
                  "validation_status": summary["status"], "inputs_changed_during_run": changed,
                  "status": "inputs_changed" if changed else summary["status"]}
        ticket_ms = datetime.fromisoformat(ticket["started_at"]).timestamp() * 1000
        finish_ms = datetime.fromisoformat(record["ended_at"]).timestamp() * 1000
        record["timing"] = {
            "dispatch_delay_ms": round(job["started_unix_ms"] - ticket_ms),
            "job_elapsed_ms": round(job["finished_unix_ms"] - job["started_unix_ms"]),
            "collection_delay_ms": round(finish_ms - job["finished_unix_ms"]),
            "after_snapshot_ms": after["elapsed_ms"],
            "note": "collection_delay 包含收尾快照；各耗时存在包含关系，不能全部相加。"}
        write_json(portable / "run.json", record)
        return record


def cancel(args):
    """记录未完成检查；不会停止 MCP 作业或 Editor。"""
    info = project_info(args.project)
    evidence = Path(args.evidence).resolve()
    if not evidence.is_relative_to(info["project"] / "Docs/SceneHandoffs"):
        raise HandoffError("证据目录须位于项目 Docs/SceneHandoffs 下")
    portable = inside(evidence, "validation/" + args.run_id)
    with exclusive(local_state(info) / "runner.lock"):
        if (portable / "run.json").exists() or not args.reason.strip():
            raise HandoffError("运行已收口或缺少中断原因")
        ticket = read_json(portable / "ticket.json")
        write_json(portable / "result.json", {"status": "incomplete", "tests": []})
        row = {**ticket, "status": "interrupted", "reason": args.reason,
               "ended_at": now(), "total_elapsed_ms": round((time.time() - datetime.fromisoformat(ticket["started_at"]).timestamp()) * 1000),
               "exit_state": "editor_kept_open", "result_file": (portable / "result.json").relative_to(evidence).as_posix(),
               "result_sha256": file_hash(portable / "result.json")}
        write_json(portable / "run.json", row)
        return row
