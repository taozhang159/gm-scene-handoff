"""将解包后的 GMGame 技能安装到个人目录；不修改项目或执行 Git 写入。"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
import tomllib
import uuid

from project_locator import resolve_project


NAME = "gm-scene-handoff"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_package(package):
    package = Path(package).resolve()
    manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
    if manifest.get("name") != NAME or manifest.get("schema_version") != 1:
        raise ValueError("不是受支持的 gm-scene-handoff 安装包")
    files = manifest.get("files", {})
    if not {"SKILL.md", "scripts/handoff.py", "scripts/install.py",
            "scripts/project_locator.py", "references/Workflow.md"}.issubset(files):
        raise ValueError("安装包缺少必要文件")
    for name, expected in files.items():
        parts = PurePosixPath(name)
        if parts.is_absolute() or ".." in parts.parts or "\\" in name or ":" in name:
            raise ValueError("安装包包含不安全路径：" + name)
        path = package / name
        if path.is_symlink() or not path.resolve().is_relative_to(package):
            raise ValueError("安装包包含外部链接：" + name)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError("安装包文件缺失或校验失败：" + name)
    actual = {p.relative_to(package).as_posix() for p in package.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts}
    if actual != set(files) | {"package.json"}:
        raise ValueError("安装包包含清单外文件，请重新下载并解包")
    return manifest


def path_key(value):
    return os.path.normcase(str(Path(value).expanduser().resolve()))


def skill_config(text, flags):
    """只更新目标技能的启用状态；保留其它配置与注释，复杂格式拒绝误写。"""
    before = tomllib.loads(text)
    wanted = {path_key(p): enabled for p, enabled in flags.items()}
    entries = before.get("skills", {}).get("config", [])
    keys = [path_key(row["path"]) for row in entries]
    if len(keys) != len(set(keys)):
        raise ValueError("Codex 配置存在重复 skills.config 路径，请先合并重复项")
    starts = list(re.finditer(r"(?m)^[ \t]*\[", text))
    pieces, offset, changed = [], 0, set()
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        block = text[match.start():end]
        if not re.match(r"\[\[skills\.config\]\][ \t]*(?:#[^\n]*)?\r?\n", block.lstrip()):
            continue
        try:
            row = tomllib.loads(block)["skills"]["config"][0]
        except (tomllib.TOMLDecodeError, KeyError):
            continue
        key = path_key(row["path"])
        if key not in wanted:
            continue
        value = str(wanted[key]).lower()
        replaced, count = re.subn(r"(?m)^([ \t]*enabled[ \t]*=[ \t]*)(true|false)",
                                  lambda m: m[1] + value, block)
        if not count:
            replaced = block.rstrip() + "\nenabled = " + value + "\n\n"
        pieces.extend((text[offset:match.start()], replaced))
        offset = end
        changed.add(key)
    pieces.append(text[offset:])
    result = "".join(pieces)
    for path, enabled in flags.items():
        key = path_key(path)
        if key in changed:
            continue
        if key in keys:
            raise ValueError("无法保留原格式更新技能配置，请由 Codex 手动处理：" + str(path))
        result = result.rstrip() + "\n\n[[skills.config]]\npath = " + json.dumps(
            Path(path).as_posix(), ensure_ascii=False) + "\nenabled = " + str(enabled).lower() + "\n"
    after = tomllib.loads(result)
    expected = copy.deepcopy(before)
    rows = expected.setdefault("skills", {}).setdefault("config", [])
    for path, enabled in flags.items():
        row = next((r for r in rows if path_key(r["path"]) == path_key(path)), None)
        if row is None:
            rows.append({"path": Path(path).as_posix(), "enabled": enabled})
        else:
            row["enabled"] = enabled
    if after != expected:
        raise ValueError("配置更新影响了无关内容，已取消安装")
    return result


def atomic_write(path, content):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def progress_message(enabled, message):
    if enabled:
        print("[GM Scene Handoff] " + message, file=sys.stderr, flush=True)


def installed_status(package, user_home=None, *, progress=False):
    """只读检查本机安装目录，明确区分本地版本与本次取得的分发版本。"""
    progress_message(progress, "[1/3] 校验下载的发布包…")
    available = verify_package(package)
    personal = Path(user_home or Path.home()).expanduser().resolve()
    target = personal / ".agents/skills" / NAME
    result = {"name": NAME, "status": "not_installed", "version": None,
              "available_version": available["version"], "installed": str(target),
              "files_verified": 0}
    progress_message(progress, "[2/3] 检查本地安装目录与文件完整性…")
    if target.exists():
        current = verify_package(target)
        result.update(status="installed", version=current["version"],
                      files_verified=len(current["files"]))
    progress_message(progress, "[3/3] 查询完成。")
    return result


def install(package, workspace=None, user_home=None, codex_home=None, *, progress=False):
    package = Path(package).resolve()
    progress_message(progress, "[1/5] 校验下载的发布包…")
    manifest = verify_package(package)
    progress_message(progress, "[2/5] 检查安装位置、项目及现有配置…")
    info = resolve_project(workspace) if workspace is not None else None
    repo = Path(info["repository"]) if info else None
    project = Path(info["project"]) if info else None
    personal = Path(user_home or Path.home()).expanduser().resolve()
    settings = Path(codex_home or os.environ.get("CODEX_HOME") or personal / ".codex").resolve()
    agents = (personal / ".agents").resolve()
    raw_target = agents / "skills" / NAME
    target = raw_target.resolve()
    if raw_target.is_symlink() or target != raw_target:
        raise ValueError("安装位置包含符号链接或目录连接，请使用实际个人技能目录")
    config = (settings / "config.toml").resolve()
    for path in (agents, target, settings, config):
        if repo is not None and path.is_relative_to(repo):
            raise ValueError("个人技能和配置目录必须位于 Git 项目外：" + str(path))
    if target == package or target in package.parents:
        raise ValueError("请从下载包的临时解包目录安装，不从已安装目录自我覆盖")
    if target.exists() and not target.is_dir():
        raise ValueError("技能目标位置不是目录")
    # 精确屏蔽此仓库可能在根目录、Unity 目录和中间目录发现的同名旧技能。
    folders = ([project, *[p for p in project.parents if p == repo or p.is_relative_to(repo)]]
               if project is not None else [])
    old = {folder / prefix / NAME / "SKILL.md"
           for folder in folders for prefix in (".agents/skills", ".codex/skills")}
    legacy = settings / "skills" / NAME / "SKILL.md"
    if legacy.exists() and legacy.resolve() != target / "SKILL.md":
        old.add(legacy)
    flags = {p.resolve(): False for p in sorted(old)}
    flags[target / "SKILL.md"] = True
    original = config.read_bytes() if config.exists() else None
    updated = skill_config((original or b"").decode("utf-8-sig"), flags).encode("utf-8")
    # 同一版本且内容、配置均完整时不重复写盘或创建备份。
    current_manifest = None
    if target.is_dir():
        try:
            current_manifest = verify_package(target)
        except (ValueError, OSError):
            pass  # 损坏或有本地修改的旧目录仍完整备份后再修复。
    if current_manifest == manifest and updated == original:
        progress_message(progress, "检查完成，版本、文件与配置均一致，无需更新。")
        return {"name": NAME, "version": manifest["version"], "status": "unchanged",
                "previous_version": manifest["version"],
                "installed": str(target), "config": str(config), "backup": None,
                "project": info, "disabled_skills": [str(p) for p in flags if not flags[p]],
                "restart_codex": False}
    agents.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    settings.mkdir(parents=True, exist_ok=True)
    backup_root = (agents / "skill-backups").resolve()
    if not backup_root.is_relative_to(agents) or (repo is not None and backup_root.is_relative_to(repo)):
        raise ValueError("备份目录必须位于项目外的个人 .agents 目录")
    backup = backup_root / (NAME + "-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    progress_message(progress, "[3/5] 准备备份并复制新版本…")
    backup.mkdir(parents=True)
    if original is not None:
        (backup / "config.toml").write_bytes(original)
    moved = False
    published = False
    with tempfile.TemporaryDirectory(prefix="handoff-install-", dir=agents) as temporary:
        staged = Path(temporary) / NAME
        staged.mkdir()
        for name in [*manifest["files"], "package.json"]:
            destination = staged / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(package / name, destination)
        progress_message(progress, "[4/5] 校验复制后的文件…")
        verify_package(staged)
        current = config.read_bytes() if config.exists() else None
        if current != original:
            raise ValueError("Codex 配置在安装期间变化，已取消，请重试")
        try:
            progress_message(progress, "[5/5] 保存旧版备份并更新个人技能及配置…")
            if target.exists():
                target.rename(backup / NAME)
                moved = True
            staged.rename(target)
            published = True
            atomic_write(config, updated)
        except Exception:
            # 只移动本次发布的目录回临时区，不递归删除用户既有目录。
            if published:
                target.rename(staged)
            if moved:
                (backup / NAME).rename(target)
            raise
    receipt = {"name": NAME, "version": manifest["version"], "status": "installed", "installed": str(target),
               "previous_version": current_manifest["version"] if current_manifest else None,
               "config": str(config), "backup": str(backup), "project": info,
               "disabled_skills": [str(p) for p in flags if not flags[p]],
               "restart_codex": True,
               "unity_mcp": "安装未验证 Unity MCP；合并前须核对活动 Editor 项目与依赖"}
    (backup / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    progress_message(progress, "安装处理完成。")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--workspace", help="安装并停用指定 GMGame 仓库内的同名旧技能")
    scope.add_argument("--global", dest="global_install", action="store_true",
                       help="仅安装到个人目录，可在没有 GMGame 仓库时使用")
    parser.add_argument("--status", action="store_true", help="只读查询本机安装版本与文件完整性")
    parser.add_argument("--progress", action="store_true", help="向 stderr 实时输出执行阶段")
    parser.add_argument("--user-home", help="仅在非默认用户目录或安装验证时指定")
    parser.add_argument("--codex-home", help="默认使用 CODEX_HOME 或用户 .codex 目录")
    args = parser.parse_args()
    try:
        package = Path(__file__).resolve().parents[1]
        result = (installed_status(package, args.user_home, progress=args.progress) if args.status else
                  install(package, args.workspace, args.user_home, args.codex_home, progress=args.progress))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")
