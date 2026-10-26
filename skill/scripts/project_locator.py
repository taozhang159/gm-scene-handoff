"""从仓库根、Unity 项目或其子目录只读定位 GMGame，不绑定机器路径。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def git(directory, *args):
    result = subprocess.run(["git", "-C", str(directory), *args],
                            capture_output=True, encoding="utf-8", timeout=30)
    if result.returncode:
        raise ValueError("无法读取项目 Git 信息：" + result.stderr.strip())
    return result.stdout.strip()


def resolve_project(workspace):
    start = Path(workspace).expanduser().resolve(strict=True)
    if not start.is_dir():
        raise ValueError("--workspace 必须是目录")
    root = Path(git(start, "rev-parse", "--show-toplevel")).resolve()
    # 只在当前 Git 仓库中检查明确的项目位置，不递归猜测其他 Unity 项目。
    candidates = [root / "GMGame/GMGameProject", root]
    found = [p for p in candidates if all((p / d).is_dir() for d in
             ("Assets/GMScenes", "Packages", "ProjectSettings"))
             and (p / "ProjectSettings/ProjectVersion.txt").is_file()]
    if len(found) != 1:
        raise ValueError("未找到唯一的 GMGame 项目，请检查仓库内 GMGame/GMGameProject")
    project = found[0].resolve()
    if not project.is_relative_to(root):
        raise ValueError("Unity 项目不能通过链接指向仓库外")
    return {"repository": str(root), "project": str(project),
            "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            "commit": git(root, "rev-parse", "HEAD")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(resolve_project(args.workspace), ensure_ascii=False, indent=2))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + "\n")
