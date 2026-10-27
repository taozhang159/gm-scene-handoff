"""记录交付里程碑；不执行 Git、Unity 或发布操作。"""

import argparse
from datetime import datetime
import json
import re
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from handoff_core import HandoffError, now, read_json, write_json


EVENTS = ("started", "prepared", "git_complete", "scene_applied", "merged", "import_ready",
          "validation_complete", "cleanup_complete", "report_complete",
          "committed", "push_verified", "released", "finished")


def records(directory, task_id):
    # 只读取本工具的连续编号记录，原始作业 JSON 不参与计时。
    paths = sorted(p for p in Path(directory).glob("*.json") if re.fullmatch(r"[0-9]{3,}\.json", p.name))
    if [p.name for p in paths] != [f"{i:03d}.json" for i in range(len(paths))]:
        raise HandoffError("计时记录编号缺失或不连续；保留历史并检查")
    rows = [read_json(p) for p in paths]
    previous = None
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not all(k in row for k in ("at", "task_id", "event")):
            raise HandoffError("编号计时记录格式损坏；不能当作无关 JSON 忽略")
        stamp = datetime.fromisoformat(row["at"])
        if (row["task_id"] != task_id or row["event"] not in EVENTS
                or row["event"] in seen or stamp.utcoffset() is None
                or (previous is not None and stamp < previous)):
            raise HandoffError("计时记录身份、事件或时钟不一致；保留原记录并检查")
        seen.add(row["event"])
        previous = stamp
    if rows and (rows[0]["event"] != "started"
                 or any(r["event"] == "finished" for r in rows[:-1])):
        raise HandoffError("计时记录必须从 started 开始，并在 finished 结束")
    return rows


def mark(directory, task_id, event):
    rows = records(directory, task_id)
    if (event not in EVENTS or any(r["event"] == event for r in rows)
            or (not rows and event != "started")
            or (rows and rows[-1]["event"] == "finished")):
        raise HandoffError("事件重复或生命周期不符；续跑沿用原记录，不重置起点")
    at = now()
    if rows and datetime.fromisoformat(at) < datetime.fromisoformat(rows[-1]["at"]):
        raise HandoffError("系统时钟回退；不能生成误导耗时")
    row = {"schema_version": 1, "task_id": task_id, "event": event, "at": at}
    # 同一任务串行写入；序号文件独占创建，竞争时失败，不覆盖历史。
    write_json(Path(directory) / f"{len(rows):03d}.json", row)
    return row


def report(directory, task_id):
    rows = records(directory, task_id)
    if not rows:
        raise HandoffError("没有计时记录")
    start = datetime.fromisoformat(rows[0]["at"])
    end = datetime.fromisoformat(rows[-1]["at"])
    return {"task_id": task_id, "complete": rows[-1]["event"] == "finished",
            "started_at": rows[0]["at"], "last_recorded_at": rows[-1]["at"],
            "wall_elapsed_seconds": (end - start).total_seconds(),
            "events": rows,
            "limitations": "系统墙钟跨度，包含等待及并行工作；不是纯执行时间。事件仅为调用者记录，不证明验证或推送成功。"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--event", choices=EVENTS, help="省略时只读汇总")
    args = parser.parse_args(argv)
    try:
        value = (mark(args.directory, args.task_id, args.event) if args.event
                 else report(args.directory, args.task_id))
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (HandoffError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
