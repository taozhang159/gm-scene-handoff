"""固定执行步骤的证据工具。只读业务文件；不合并、不恢复、不控制 Editor。"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

from handoff_core import (HandoffError, digest, exclusive, file_hash, git, inside,
                          local_state, now, project_info, read_json, write_json)


COMMANDS = ("scene-guard-create", "scene-guard-check", "checkpoint", "resume", "restore-plan")


def add_commands(commands):
    fields = {
        "scene-guard-create": ("project", "baseline", "allowlist", "output"),
        "scene-guard-check": ("project", "guard", "candidates", "output"),
        "checkpoint": ("project", "evidence", "record"),
        "resume": ("project", "evidence"),
        "restore-plan": ("project", "evidence", "run-id", "output"),
    }
    for name, required in fields.items():
        parser = commands.add_parser(name, help=__doc__)
        for field in required:
            parser.add_argument("--" + field, required=True)
        if name == "scene-guard-create":
            parser.add_argument("--refs", nargs="+", required=True,
                                help="固定来源及涉及移动/删除的历史提交，不接受省略来源")


def dispatch(args):
    return {"scene-guard-create": guard_create, "scene-guard-check": guard_check,
            "checkpoint": checkpoint, "resume": resume, "restore-plan": restore_plan}[args.command](args)


def scene_path(name):
    return name.startswith("Assets/") and name.endswith((".unity", ".unity.meta"))


def tree_scenes(info, ref):
    commit = git(info["root"], "rev-parse", "--verify", ref + "^{commit}")
    prefix = info["project_path"] + "/" if info["project_path"] != "." else ""
    rows = {}
    raw = git(info["root"], "ls-tree", "-r", "-z", commit, "--", prefix + "Assets", binary=True)
    for entry in raw.decode("utf-8").split("\0"):
        if not entry:
            continue
        header, name = entry.split("\t", 1)
        mode, kind, blob = header.split()
        name = name[len(prefix):]
        if scene_path(name):
            if kind != "blob" or mode != "100644":
                raise HandoffError("不支持的场景文件模式：" + name)
            rows[name] = blob
    return commit, rows


def index_scenes(project):
    rows = {}
    for entry in git(project, "ls-files", "--stage", "-z", "--", "Assets", binary=True).decode("utf-8").split("\0"):
        if not entry:
            continue
        header, name = entry.split("\t", 1)
        if scene_path(name):
            mode, blob, stage = header.split()
            if stage != "0" or mode != "100644":
                raise HandoffError("场景索引存在冲突或不支持的模式：" + name)
            rows[name] = blob
    return rows


def disk_scenes(project):
    return {p.relative_to(project).as_posix() for p in (project / "Assets").rglob("*.unity*")
            if scene_path(p.relative_to(project).as_posix())}


def disk_hash(project, name):
    path = inside(project, name)
    raw = Path(project) / name
    for component in (raw, *raw.parents):
        if component == Path(project):
            break
        if component.is_symlink() or (hasattr(component, "is_junction") and component.is_junction()):
            raise HandoffError("场景路径含链接；须先明确真实身份：" + name)
    if path.exists() and not path.is_file():
        raise HandoffError("场景路径不是普通文件：" + name)
    return file_hash(path) if path.is_file() else None


def filtered_blob(project, name):
    """沿用 Git 对该路径的转换规则，避免中文路径及 CRLF 导致错误比较；不写对象库。"""
    path = inside(project, name)
    if not path.is_file():
        return None
    result = subprocess.run(["git", "-C", str(project), "hash-object", "--path=" + name, "--stdin"],
                            input=path.read_bytes(), capture_output=True, timeout=120)
    if result.returncode:
        raise HandoffError("无法核对工作树与索引：" + name)
    return result.stdout.decode("ascii").strip()


def guard_create(args):
    info = project_info(args.project)
    baseline, original = tree_scenes(info, args.baseline)
    if baseline != info["commit"]:
        raise HandoffError("先完成目标远程对齐，再在实际接收起点创建场景保护记录")
    requested = read_json(args.allowlist)
    allowed = requested.get("files")
    if not isinstance(allowed, list) or len(set(allowed)) != len(allowed):
        raise HandoffError("allowlist.files 必须为无重复的项目相对路径数组")
    allowed = set(allowed)
    for name in allowed:
        inside(info["project"], name)
        paired = name[:-5] if name.endswith(".meta") else name + ".meta"
        if not scene_path(name) or paired not in allowed or name not in original:
            raise HandoffError("本工具只支持成对的既有目标场景；新增/删除/迁移须按原流程另行裁决：" + name)
    paths = set(original)
    refs = []
    for ref in args.refs:
        commit, rows = tree_scenes(info, ref)
        paths.update(rows)
        refs.append(commit)
    index = index_scenes(info["project"])
    if index != original or disk_scenes(info["project"]) != set(original):
        raise HandoffError("接收起点的场景索引/路径有本地变化；先处理归属，不自动覆盖")
    # status/diff 使用 -z；捕获 Git 规范化前的实际磁盘哈希，后续保护要求字节不变。
    dirty = git(info["project"], "diff", "--relative", "--name-only", "-z", "HEAD", "--", "Assets", binary=True)
    if any(scene_path(n) for n in dirty.decode("utf-8").split("\0") if n):
        raise HandoffError("接收起点仍有未保存到检查点的场景变化")
    entries = {name: {"blob": original.get(name), "disk_sha256": disk_hash(info["project"], name)}
               for name in sorted(paths)}
    if info["commit"] != git(info["project"], "rev-parse", "HEAD") or index != index_scenes(info["project"]):
        raise HandoffError("记录期间 HEAD 或场景索引变化，停止并行编辑后重试")
    value = {"schema_version": 1, "project_path": info["project_path"], "branch": info["branch"],
             "baseline": baseline, "refs": refs, "allowlist": sorted(allowed), "entries": entries,
             "created_at": now(), "policy": "directional-v1"}
    value["identity"] = digest(value)
    write_json(args.output, value)
    return {"status": "passed", "protected": len(paths - allowed), "allowed": len(allowed),
            "output": str(args.output)}


def guard_check(args):
    info = project_info(args.project)
    value = read_json(args.guard)
    identity = value.pop("identity")
    if digest(value) != identity or value["project_path"] != info["project_path"] or value["branch"] != info["branch"]:
        raise HandoffError("场景保护记录身份、项目或接收分支不匹配")
    git(info["root"], "merge-base", "--is-ancestor", value["baseline"], info["commit"])
    # 未解决的代码/资源冲突也不允许恢复导入。
    if git(info["root"], "ls-files", "--unmerged", "-z", binary=True):
        raise HandoffError("索引仍有未解决冲突；不得继续依赖步骤或解除导入保护")
    selected = read_json(args.candidates)
    allowed = set(value["allowlist"])
    if (selected.get("path_base", "project") != "project" or selected.get("deleted")
            or set(selected.get("files", {})) != allowed):
        raise HandoffError("审核后候选哈希清单必须精确覆盖白名单，使用 project 根且不能包含删除")
    index = index_scenes(info["project"])
    paths = set(value["entries"]) | set(index) | disk_scenes(info["project"])
    failures = []
    for name in sorted(paths):
        original = value["entries"].get(name, {"blob": None, "disk_sha256": None})
        actual = disk_hash(info["project"], name)
        if name in allowed:
            expected = selected["files"][name]
            if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
                raise HandoffError("候选清单必须包含 SHA-256：" + name)
            if actual != expected or index.get(name) != filtered_blob(info["project"], name):
                failures.append({"path": name, "reason": "目标磁盘/索引与审核候选不一致"})
            if name.endswith(".meta") and (actual != original["disk_sha256"] or index.get(name) != original["blob"]):
                failures.append({"path": name, "reason": "目标场景身份元数据被改动"})
        elif actual != original["disk_sha256"] or index.get(name) != original["blob"]:
            failures.append({"path": name, "reason": "白名单外场景的磁盘/索引/存在性改变"})
    output = {"status": "failed" if failures else "passed", "guard_identity": identity,
              "baseline": value["baseline"], "checked_commit": info["commit"],
              "checked_at": now(), "checked_paths": len(paths), "failures": failures,
              "limitations": "仅证明路径、字节、索引和目标身份；不证明候选语义、引用或 Editor 就绪。"}
    write_json(args.output, output)
    return {**output, "output": str(args.output)}


def evidence_root(info, evidence):
    path = Path(evidence).resolve()
    base = info["project"] / "Docs/SceneHandoffs"
    if not path.is_relative_to(base) or path == base:
        raise HandoffError("本轮证据须位于 Docs/SceneHandoffs 的任务子目录")
    return path


def checkpoint(args):
    info = project_info(args.project)
    evidence = evidence_root(info, args.evidence)
    record = read_json(args.record)
    for name in ("task_id", "phase", "next_action", "lock_state", "editor_session"):
        if not isinstance(record.get(name), str) or not record[name].strip():
            raise HandoffError("续跑记录缺少 " + name)
    if record["lock_state"] not in ("held", "released", "unknown"):
        raise HandoffError("lock_state 使用 held/released/unknown，并在 notes 写恢复方法")
    if not isinstance(record.get("notes"), str) or not record["notes"].strip():
        raise HandoffError("notes 须说明未完成事项及锁的恢复办法")
    files = record.get("evidence_files")
    if not isinstance(files, list) or not files or len(set(files)) != len(files):
        raise HandoffError("evidence_files 须引用本轮已有的固定输入、场景及验证证据")
    hashes = {name: file_hash(inside(evidence, name)) for name in files}
    with exclusive(local_state(info) / "steps.lock"):
        directory = evidence / "checkpoints"
        prior = sorted(directory.glob("*.json"))
        if prior and read_json(prior[-1])["task_id"] != record["task_id"]:
            raise HandoffError("本轮续跑记录属于另一任务")
        value = {"schema_version": 1, "task_id": record["task_id"], "phase": record["phase"],
                 "next_action": record["next_action"], "lock_state": record["lock_state"],
                 "editor_session": record["editor_session"], "notes": record["notes"],
                 "project_path": info["project_path"], "branch": info["branch"], "commit": info["commit"],
                 "recorded_at": now(), "evidence_files": hashes}
        write_json(directory / f"{len(prior):04d}.json", value)
    return {"status": "passed", "phase": value["phase"], "next_action": value["next_action"],
            "note": "仅保存续跑线索，不把调用者的阶段说明当作成功证明。"}


def resume(args):
    info = project_info(args.project)
    evidence = evidence_root(info, args.evidence)
    prior = sorted((evidence / "checkpoints").glob("*.json"))
    if not prior:
        raise HandoffError("没有续跑记录；先读取已有证据，不重跑合并来生成记录")
    value = read_json(prior[-1])
    changed = []
    for name, expected in value["evidence_files"].items():
        path = inside(evidence, name)
        if not path.is_file() or file_hash(path) != expected:
            changed.append(name)
    same_git = all(value[k] == info[k] for k in ("project_path", "branch", "commit"))
    pending, runs = [], []
    for ticket in sorted((evidence / "validation").glob("*/ticket.json")):
        run = ticket.with_name("run.json")
        if not run.is_file():
            pending.append(ticket.parent.name)
        else:
            data = read_json(run)
            runs.append({"run_id": data["run_id"], "status": data["status"]})
    return {"status": "ready" if same_git and not changed else "blocked",
            "task_id": value["task_id"], "phase": value["phase"], "next_action": value["next_action"],
            "lock_state": value["lock_state"], "editor_session": value["editor_session"],
            "notes": value["notes"], "git_identity_matches": same_git, "changed_evidence": changed,
            "open_tickets": pending, "runs": runs,
            "required_live_checks": ["实际 Editor 会话、锁与就绪状态", "当前输入字节和场景身份"],
            "limitations": "ready 只表示续跑证据可读且身份一致，不授权跳过输入校验或重跑未收口测试。"}


def matches_identity(project, name, expected):
    path = inside(project, name)
    if expected is None:
        return not path.exists()
    if not path.is_file():
        return False
    if expected.startswith("git:"):
        return filtered_blob(project, name) == expected[4:]
    return file_hash(path) == expected


def restore_plan(args):
    info = project_info(args.project)
    evidence = evidence_root(info, args.evidence)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
        raise HandoffError("run-id 必须为单个运行标识")
    directory = inside(evidence, "validation/" + args.run_id)
    run = read_json(directory / "run.json")
    before, after = read_json(directory / "inputs.json"), read_json(directory / "inputs-after.json")
    if (run["run_id"] != args.run_id or run["input_snapshot_id"] != before["input_snapshot_id"]
            or run["inputs_sha256"] != file_hash(directory / "inputs.json")):
        raise HandoffError("运行记录与原输入快照身份不一致")
    for snap in (before, after):
        if snap["input_snapshot_id"] != digest({"files": snap["files"], "tools": snap["tools"]}):
            raise HandoffError("快照内容哈希不一致")
        if any(snap[k] != info[k] for k in ("project_path", "branch", "commit")):
            raise HandoffError("分支、HEAD 或项目变化，不能按测试副作用恢复")
    if before["tools"] != after["tools"]:
        raise HandoffError("工具版本发生变化，文件恢复不能使该测试结果重新有效")
    changes = []
    for name in sorted(set(before["files"]) | set(after["files"])):
        old, new = before["files"].get(name), after["files"].get(name)
        if old == new:
            continue
        state = ("already_restored" if matches_identity(info["project"], name, old) else
                 "matches_after_test" if matches_identity(info["project"], name, new) else "changed_again")
        changes.append({"path": name, "before_identity": old, "after_test_identity": new,
                        "current_state": state, "attribution": None,
                        "action": "review_and_archive" if old is None else "review_before_restore"})
    value = {"schema_version": 1, "task_id": run["task_id"], "run_id": args.run_id,
             "status": "needs_attribution", "changes": changes,
             "settings_memory_and_disk_verified": False, "user_data_verified": False,
             "limitations": "只生成差异清单，不归因、不恢复、不删除，也不能作为 cleanup.complete。"}
    write_json(args.output, value)
    return {"status": "ready", "changes": len(changes),
            "changed_again": [r["path"] for r in changes if r["current_state"] == "changed_again"],
            "output": str(args.output), "note": value["limitations"]}
