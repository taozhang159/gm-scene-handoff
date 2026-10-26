"""场景交付的快照、工作区身份和证据工具；不执行 Git 合并或场景改写。"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import time
from datetime import datetime


VERSION = "1.2"
INPUT_ROOTS = ("Assets", "Packages", "ProjectSettings")


class HandoffError(RuntimeError):
    pass


def now():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value, *, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not replace:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        return
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.replace(temporary, path)


def inside(root, relative):
    """拒绝越界、绝对路径及符号链接指向的外部文件。"""
    root = Path(root).resolve()
    relative = str(relative)
    if Path(relative).is_absolute() or "\\" in relative:
        raise HandoffError("路径必须使用相对路径和正斜线：" + relative)
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise HandoffError("路径超出指定根目录：" + relative)
    return path


def git(project, *args, binary=False):
    result = subprocess.run(["git", "-C", str(project), *args], capture_output=True,
                            timeout=120)
    if result.returncode:
        raise HandoffError("Git 只读检查失败：" + " ".join(args[:2]))
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def project_info(project):
    project = Path(project).resolve()
    for name in INPUT_ROOTS:
        if not (project / name).is_dir():
            raise HandoffError("不是完整 Unity 项目，缺少 " + name)
    root = Path(git(project, "rev-parse", "--show-toplevel")).resolve()
    git_dir = Path(git(project, "rev-parse", "--absolute-git-dir")).resolve()
    common = Path(git(project, "rev-parse", "--path-format=absolute",
                      "--git-common-dir")).resolve()
    return {"project": project, "root": root, "git_dir": git_dir, "common": common,
            "project_path": project.relative_to(root).as_posix(),
            "commit": git(project, "rev-parse", "HEAD"),
            "branch": git(project, "symbolic-ref", "--quiet", "--short", "HEAD")
            if git(project, "rev-parse", "--abbrev-ref", "HEAD") != "HEAD" else None}


def dirty_files(info, *, input_only=False):
    # -z 保留中文、空格和重命名路径；使用内容哈希识别同一 HEAD 下的变化。
    prefix = "" if info["project_path"] == "." else info["project_path"] + "/"
    pathspec = ["--", *[prefix + name for name in INPUT_ROOTS]] if input_only else []
    tokens = git(info["root"], "status", "--porcelain=v1", "-z",
                 "--untracked-files=all", *pathspec, binary=True).decode("utf-8").split("\0")
    rows = []
    i = 0
    while i < len(tokens) and tokens[i]:
        status, name = tokens[i][:2], tokens[i][3:]
        path = inside(info["root"], name)
        row = {"path": name, "status": status,
               "sha256": file_hash(path) if path.is_file() else None}
        i += 1
        if "R" in status or "C" in status:
            row["old_path"] = tokens[i]
            i += 1
        rows.append(row)
    return sorted(rows, key=lambda x: x["path"])


def unity_version(project):
    text = (Path(project) / "ProjectSettings/ProjectVersion.txt").read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        if line.startswith("m_EditorVersion:"):
            return line.split(":", 1)[1].strip()
    raise HandoffError("ProjectVersion.txt 缺少 Editor 版本")


def compatibility(project, platform):
    project = Path(project)
    for name in ("manifest.json", "packages-lock.json"):
        read_json(project / "Packages" / name)
    return {"unity": unity_version(project), "host": os.name, "target_platform": platform,
            "packages": {name: file_hash(project / "Packages" / name)
                         for name in ("manifest.json", "packages-lock.json")},
            "settings": {p.name: file_hash(p) for p in sorted((project / "ProjectSettings").iterdir())
                         if p.is_file()}}


def snapshot(project, scope, *, full_content=False):
    started, tick = now(), time.monotonic()
    info = project_info(project)
    dependencies = read_json(info["project"] / "Packages/manifest.json").get("dependencies", {})
    if any(isinstance(value, str) and value.startswith("file:") for value in dependencies.values()):
        raise HandoffError("第一版不自动固定 file: 包依赖；请使用已明确外部输入的验证路径")
    before = dirty_files(info, input_only=True)
    dirty_paths = {row["path"] for row in before}
    tracked = {}
    for entry in git(info["project"], "ls-files", "--stage", "-z", "--", *INPUT_ROOTS,
                     binary=True).decode("utf-8").split("\0"):
        if not entry:
            continue
        header, name = entry.split("\t", 1)
        mode, blob, stage = header.split()
        if stage != "0":
            raise HandoffError("存在未解决的 Git 冲突：" + name)
        tracked[name] = blob
    files = {}
    hashed_bytes = 0
    for name in INPUT_ROOTS:
        for path in sorted((info["project"] / name).rglob("*")):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise HandoffError("输入包含链接，请先明确外部依赖：" + str(path))
            if not path.is_file():
                continue
            relative = path.relative_to(info["project"]).as_posix()
            inside(info["project"], relative)
            before_stat = path.stat()
            repository_name = path.relative_to(info["root"]).as_posix()
            if not full_content and relative in tracked and repository_name not in dirty_paths:
                files[relative] = "git:" + tracked[relative]
            else:
                files[relative] = file_hash(path)
                hashed_bytes += before_stat.st_size
            after_stat = path.stat()
            if (before_stat.st_size, before_stat.st_mtime_ns) != (after_stat.st_size, after_stat.st_mtime_ns):
                raise HandoffError("快照期间文件发生变化：" + relative)
    if before != dirty_files(info, input_only=True) or info["commit"] != git(project, "rev-parse", "HEAD"):
        raise HandoffError("快照期间工作区发生变化，请停止并行写入后重试")
    # 运行器或解析器变化也使旧验证失效；文档不影响运行输入。
    tool_hashes = {p.name: file_hash(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    inputs = {"files": files, "tools": tool_hashes}
    return {"schema_version": 1, "created_at": started, "ended_at": now(),
            "elapsed_ms": round((time.monotonic() - tick) * 1000),
            "project_path": info["project_path"], "commit": info["commit"],
            "branch": info["branch"], "scope_authorization": scope,
            "full_content": full_content, "hashed_bytes": hashed_bytes,
            "dirty_scope": "project_inputs", "dirty_files": before, "dirty_snapshot_hash": digest(before),
            "input_snapshot_id": digest(inputs), **inputs}


def snapshot_matches(expected, current, project):
    if expected["tools"] != current["tools"] or expected["files"].keys() != current["files"].keys():
        return False
    for name, identity in expected["files"].items():
        actual = current["files"][name]
        if identity == actual:
            continue
        # 提交后原脏文件成为干净 Git 文件；仅对这些文件重新核对原受测字节。
        if not identity.startswith("git:") and actual.startswith("git:"):
            if file_hash(inside(project, name)) == identity:
                continue
        return False
    return True


def local_state(info):
    return info["git_dir"] / "gm-scene-handoff" / digest(info["project_path"])[:16]


@contextlib.contextmanager
def exclusive(path):
    """OS 文件锁随进程退出释放；不删除 Unity 的锁文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise HandoffError("已有交付工具占用该验证工作区") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def workspace(source, project, task_id, platform, *, claim=False, active_projects=()):
    src, dst = project_info(source), project_info(project)
    if src["project"] == dst["project"] or src["root"] == dst["root"]:
        raise HandoffError("验证目标必须是独立 worktree，不能使用源开发项目")
    if src["common"] != dst["common"] or src["project_path"] != dst["project_path"]:
        raise HandoffError("验证项目与来源的仓库身份或项目相对路径不匹配")
    if dst["git_dir"] == dst["common"]:
        raise HandoffError("第一版只接管独立 linked worktree")
    library = dst["project"] / "Library"
    if not library.resolve().is_relative_to(dst["project"]) or library.resolve() == (src["project"] / "Library").resolve():
        raise HandoffError("Library 指向项目外或来源缓存，禁止共享验证缓存")
    for active in active_projects:
        if active is None or Path(active).resolve() == dst["project"]:
            raise HandoffError("目标被 Unity 使用，或有无法确认项目路径的 Editor")
    if (dst["project"] / "Temp/UnityLockfile").exists():
        raise HandoffError("目标存在 UnityLockfile；请核实占用，不自动删除")
    state = local_state(dst)
    receipt_path = state / "workspace.json"
    receipt = read_json(receipt_path) if receipt_path.exists() else None
    identity = {"project": str(dst["project"]), "common": str(dst["common"]),
                "task_id": task_id}
    dirty = dirty_files(dst)
    current = compatibility(project, platform)
    if receipt and any(receipt.get(k) != v for k, v in identity.items()):
        same_project = all(receipt.get(k) == identity[k] for k in ("project", "common"))
        if not (claim and same_project and not dirty):
            raise HandoffError("工作区属于另一任务或身份已变；仅可显式登记干净且空闲的同项目工作区")
        write_json(state / "owners" / (digest(receipt) + ".json"), receipt,
                   replace=(state / "owners" / (digest(receipt) + ".json")).exists())
        receipt = {**receipt, **identity, "created_at": now()}
        write_json(receipt_path, receipt, replace=True)
    if not receipt and dirty:
        raise HandoffError("未登记工作区含未提交文件，不能自动接管")
    if claim and not receipt:
        write_json(receipt_path, {**identity, "created_at": now(), "compatibility": current})
        receipt = read_json(receipt_path)
    old = receipt.get("last_validated_compatibility", receipt["compatibility"]) if receipt else None
    cache = "absent"
    if (dst["project"] / "Library").is_dir():
        cache = "incremental_candidate" if old == current else "requires_import_or_rebuild"
    return {"project_path": dst["project_path"], "task_id": task_id,
            "registered": receipt is not None, "dirty_files": dirty,
            "cache": cache, "compatibility": current,
            "note": "缓存只用于增量导入，不代表测试通过；同任务脏文件仍须核对范围。"}


def load_plan(path):
    plan = read_json(path)
    if not isinstance(plan.get("task_id"), str) or not plan["task_id"].strip():
        raise HandoffError("计划缺少 task_id")
    for field in ("source_commit", "target_base_commit"):
        value = plan.get(field, "")
        if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
            raise HandoffError("计划须固定完整 SHA：" + field)
    if not plan.get("scope_authorization") or not plan.get("target_platform") or not plan.get("source_snapshot"):
        raise HandoffError("计划缺少范围授权摘要、目标平台或来源快照")
    if not isinstance(plan.get("full_content_snapshot", False), bool):
        raise HandoffError("full_content_snapshot 必须为布尔值")
    if plan.get("purpose", "final") not in ("final", "diagnostic"):
        raise HandoffError("purpose 必须为 final 或 diagnostic")
    checks = plan.get("checks", [])
    if not isinstance(checks, list) or not checks or any(
            not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"].strip()
            for c in checks):
        raise HandoffError("验证计划必须包含有效的检查 ID")
    if len({c["id"] for c in checks}) != len(checks):
        raise HandoffError("验证计划必须包含唯一的检查 ID")
    for check in checks:
        backend = check.get("backend", "batch")
        if backend not in ("batch", "editor_mcp"):
            raise HandoffError("未知验证 backend")
        requirements = check.get("requirements", {})
        if (not isinstance(requirements, dict) or any(
                k not in ("cursor_lock", "camera_render", "foreground_window") or not isinstance(v, bool)
                for k, v in requirements.items())):
            raise HandoffError("测试能力声明无效")
        if backend == "batch" and any(requirements.values()):
            raise HandoffError("需要交互/渲染能力的检查必须走当前 Editor MCP")
        if backend == "editor_mcp":
            expected = check.get("expected_tests", [])
            if (not isinstance(expected, list) or not expected
                    or any(not isinstance(n, str) or not n.strip() for n in expected)
                    or len(expected) != len(set(expected))):
                raise HandoffError("MCP 检查须提供运行前确定的完整 expected_tests 清单")
        if not isinstance(check["id"], str) or not check["id"].strip():
            raise HandoffError("检查 ID 必须为非空字符串")
        if not check.get("reason") or check.get("mode") not in ("EditMode", "PlayMode", "audit"):
            raise HandoffError("每项检查须有 mode 和选择理由")
        if not isinstance(check.get("min_tests", 1), int) or check.get("min_tests", 1) < 1:
            raise HandoffError("min_tests 必须大于零")
        if check["mode"] == "audit" and not check.get("execute_method"):
            raise HandoffError("audit 检查须指定已有的 execute_method")
        for key in ("execute_method", "test_filter", "assembly_names"):
            if key in check and not isinstance(check[key], str):
                raise HandoffError(key + " 必须是字符串")
    return plan


def scene_pairs(project, author, refs):
    """固定提交下递归发现配对，不根据操作者身份猜作者，不修改文件。"""
    if not author or not author.strip() or any(c in author for c in "/\\\r\n"):
        raise HandoffError("须提供明确的个人场景作者后缀")
    info = project_info(project)
    prefix = "" if info["project_path"] == "." else info["project_path"] + "/"
    result = []
    for ref in refs:
        commit = git(project, "rev-parse", "--verify", ref + "^{commit}")
        names = git(info["root"], "ls-tree", "-r", "--name-only", "-z", commit,
                    "--", prefix + "Assets/GMScenes/Test/", binary=True).decode("utf-8").split("\0")
        groups = {}
        for name in names:
            match = re.fullmatch(r"TestScene_all_(\d{3})(?:_(.+))?\.unity", Path(name).name)
            if not match or match[2] not in (None, author):
                continue
            group = groups.setdefault(match[1], {"base": [], "personal": []})
            group["personal" if match[2] else "base"].append(name[len(prefix):])
        scenes = []
        for number, group in sorted(groups.items()):
            counts = [len(group[k]) for k in ("base", "personal")]
            status = ("ambiguous" if max(counts) > 1 else
                      "missing_base" if not counts[0] else
                      "missing_personal" if not counts[1] else "paired")
            scenes.append({"number": number, **group, "status": status})
        result.append({"commit": commit, "scenes": scenes})
    return {"author": author, "project_path": info["project_path"], "versions": result}


def protection_record(evidence, plan):
    relative = plan.get("protection_record")
    if not relative:
        raise HandoffError("运行前须提供存档和章节偏好的保护记录")
    path = inside(evidence, relative)
    record = read_json(path)
    if record.get("status") != "prepared" or record.get("method") not in ("backup", "isolated"):
        raise HandoffError("用户数据保护记录尚未准备完成")
    if record.get("task_id") != plan["task_id"] or not record.get("details"):
        raise HandoffError("用户数据保护记录缺少本任务归属或措施说明")
    return file_hash(path)
