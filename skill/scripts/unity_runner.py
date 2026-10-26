"""Windows Unity 子进程管理。仅通过本次 Popen 的原生句柄结束已完成进程。"""

from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

from handoff_core import HandoffError, file_hash, now, unity_version


def powershell(script, env=None):
    if os.name != "nt":
        raise HandoffError("此版本的 Unity 启动器仅支持 Windows")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                             "$ErrorActionPreference='Stop'; " + script],
                            env=env, capture_output=True, encoding="utf-8", errors="replace",
                            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise HandoffError("Windows 进程/版本检查失败；未启动或结束任何 Editor")
    return result.stdout.strip()


def windows_argv(command):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer:
        raise HandoffError("无法解析 Editor 项目参数")
    try:
        return [pointer[i] for i in range(count.value)]
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(pointer)


def editors():
    raw = powershell("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
                     "@(Get-CimInstance Win32_Process -Filter \"Name = 'Unity.exe'\" | "
                     "Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine) | "
                     "ConvertTo-Json -Compress")
    data = json.loads(raw) if raw else []
    if isinstance(data, dict):
        data = [data]
    rows = []
    for item in data:
        args = windows_argv(item["CommandLine"]) if item.get("CommandLine") else []
        folded = [arg.lower() for arg in args]
        index = folded.index("-projectpath") if "-projectpath" in folded else -1
        project = str(Path(args[index + 1]).resolve()) if 0 <= index < len(args) - 1 else None
        rows.append({"pid": item["ProcessId"], "started_at": item["CreationDate"],
                     "editor": item.get("ExecutablePath"), "project": project})
    return rows


def editor_version(editor):
    env = os.environ.copy()
    env["GM_HANDOFF_EDITOR_FILE"] = str(editor)
    version = powershell("[Diagnostics.FileVersionInfo]::GetVersionInfo("
                         "$env:GM_HANDOFF_EDITOR_FILE).ProductVersion", env)
    return version.split("_", 1)[0]


def locate_editor(project, explicit, running):
    version = unity_version(project)
    candidates = [explicit] if explicit else []
    if not explicit:
        candidates += [os.environ.get("UNITY_EDITOR_PATH")]
        candidates += [row["editor"] for row in running]
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if root:
                candidates.append(str(Path(root) / "Unity/Hub/Editor" / version / "Editor/Unity.exe"))
    for candidate in dict.fromkeys(filter(None, candidates)):
        path = Path(candidate).resolve()
        if path.name.lower() == "unity.exe" and path.is_file() and editor_version(path) == version:
            return path
    raise HandoffError("未找到匹配 " + version + " 的 Editor；用 --editor 指定本机 Unity.exe")


def child_environment(environment=None):
    env = dict(os.environ if environment is None else environment)
    diagnostics = {}
    if os.name == "nt":
        for key in ("TEMP", "TMP", "USERPROFILE"):
            value = env.get(key)
            if not value or not Path(value).is_dir():
                raise HandoffError("子进程环境目录无效：" + key)
            diagnostics[key] = "valid"
        value = env.get("ALLUSERSPROFILE")
        if value:
            if not Path(value).is_dir():
                raise HandoffError("ALLUSERSPROFILE 已设置但目录无效，未覆盖")
            diagnostics["ALLUSERSPROFILE"] = "valid"
        else:
            candidate = env.get("PROGRAMDATA")
            if not candidate or not Path(candidate).is_dir():
                raise HandoffError("ALLUSERSPROFILE 缺失且 PROGRAMDATA 不是有效目录")
            env["ALLUSERSPROFILE"] = candidate
            diagnostics["ALLUSERSPROFILE"] = "child_only_from_PROGRAMDATA"
    return env, diagnostics


def process_identity(process):
    if os.name == "nt":
        creation, exit_time, kernel_time, user_time = (ctypes.c_uint64() for _ in range(4))
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.c_void_p] * 4
        if not kernel.GetProcessTimes(int(process._handle), ctypes.byref(creation),
                                      ctypes.byref(exit_time), ctypes.byref(kernel_time),
                                      ctypes.byref(user_time)):
            raise HandoffError("无法核验本任务进程开始时间")
        return {"pid": process.pid, "created": creation.value}
    # Linux 仅供工具隔离测试；正式 Editor 启动仍由 Windows 预检限制。
    stat = Path(f"/proc/{process.pid}/stat").read_text()
    return {"pid": process.pid, "created": stat[stat.rfind(")") + 2:].split()[19]}


def terminate_completed(process, identity, expected_args):
    if process.poll() is not None:
        return True
    if process.args != expected_args or process_identity(process) != identity:
        return False
    # Windows Popen 持有创建时的原生句柄；绝不按 PID 重新打开并终止进程。
    process.terminate()
    try:
        process.wait(timeout=10)
        return True
    except subprocess.TimeoutExpired:
        return False


def parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def parse_result(path, mode, run_id, snapshot_id, launched_at, min_tests=1):
    path = Path(path)
    if mode == "audit":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if (data.get("run_id") != run_id or data.get("input_snapshot_id") != snapshot_id
                or data.get("complete") is not True or data.get("status") not in ("passed", "failed")):
            raise ValueError("审计结果不完整或不属于本轮输入")
        return {"status": data["status"], "total": 0, "passed": 0, "failed": 0,
                "tests": [], "raw_sha256": file_hash(path)}
    root = ET.parse(path).getroot()
    if root.tag != "test-run" or not root.get("end-time"):
        raise ValueError("不是完整 NUnit test-run")
    start, end = parse_timestamp(root.attrib["start-time"]), parse_timestamp(root.attrib["end-time"])
    if start < launched_at - 2 or end < start or end > time.time() + 2:
        raise ValueError("XML 起止时间与本次启动不符")
    tests = [{"name": node.get("fullname"), "result": node.get("result"),
              "duration": node.get("duration", "0")} for node in root.iter("test-case")]
    total, passed, failed = (int(root.attrib[key]) for key in ("total", "passed", "failed"))
    if total < min_tests or total != len(tests) or passed + failed > total:
        raise ValueError("XML 用例数量不完整或未达到计划最低数量")
    if any(not t["name"] or t["result"] not in ("Passed", "Failed", "Skipped", "Inconclusive") for t in tests):
        raise ValueError("XML 用例缺少名称或完成状态")
    if len({t["name"] for t in tests}) != len(tests):
        raise ValueError("XML 用例名称重复，无法可靠汇总")
    if sum(t["result"] == "Passed" for t in tests) != passed or sum(t["result"] == "Failed" for t in tests) != failed:
        raise ValueError("XML 根节点与用例结果不一致")
    success = passed == total and root.get("result") == "Passed"
    return {"status": "passed" if success else "failed", "total": total,
            "passed": passed, "failed": failed, "tests": tests,
            "started_at": root.get("start-time"), "ended_at": root.get("end-time"),
            "duration": root.get("duration"), "raw_sha256": file_hash(path)}


def failure_kind(log):
    if "Failed to resolve packages" in log or "No packages loaded" in log:
        return "package_resolution"
    if "another Unity instance" in log:
        return "project_in_use"
    if "No valid Unity Editor license" in log or "Failed to activate/update license" in log:
        return "license"
    if "Scripts have compiler errors" in log or re.search(r"error CS\d+:", log):
        return "compilation"
    return None


def monitor(process, result_path, log_path, mode, run_id, snapshot_id, launched_at,
            identity, *, idle_timeout=600, test_timeout=1800, exit_grace=45,
            poll_seconds=1, min_tests=1):
    tick = last_progress = time.monotonic()
    previous_size = -1
    test_started = collected = None
    parsed = None
    error = None
    forced = False
    args = list(process.args)
    phase_times = {}
    log = ""
    shutdown = False
    kind = None
    while True:
        current = time.monotonic()
        log_file = Path(log_path)
        if log_file.exists():
            size = log_file.stat().st_size
            if size != previous_size:
                previous_size, last_progress = size, current
                with log_file.open("rb") as stream:
                    stream.seek(max(0, size - 262144))
                    log = stream.read().decode("utf-8", errors="replace")
                kind = failure_kind(log) or kind
                # 域重载/退出 PlayMode 也可能打印 Shutdown。仅接受本轮结果写出后的退出标志。
                completion = ("[GMHandoff] result-complete " + run_id if mode == "audit"
                              else "Saving results to: " + str(result_path))
                normalized = log.replace("\\", "/")
                boundary = normalized.rfind(completion.replace("\\", "/"))
                shutdown = shutdown or (boundary >= 0 and any(marker in normalized[boundary:] for marker in (
                    "Input System module state changed to: ShutdownInProgress",
                    "Application is shutting down", "Exiting batchmode")))
                if test_started is None and ("Running tests for " in log or '"testRunStarted"' in log):
                    test_started = current
                    phase_times["test_dispatch_after_ms"] = round((current - tick) * 1000)
        if Path(result_path).exists():
            try:
                parsed = parse_result(result_path, mode, run_id, snapshot_id, launched_at, min_tests)
                if collected is None:
                    collected = current
                    phase_times["result_after_ms"] = round((current - tick) * 1000)
            except (ValueError, KeyError, ET.ParseError, OSError) as exc:
                parsed = None
                error = type(exc).__name__ if isinstance(exc, OSError) else str(exc)
        code = process.poll()
        if code is not None:
            status = parsed["status"] if parsed and (code == 0 or forced) else "incomplete"
            if parsed and parsed["status"] == "failed":
                status = "failed"
            if kind and status != "passed":
                status = "environment_blocked" if kind != "compilation" else "compilation_failed"
            return {"status": status, "result": parsed, "exit_code": code,
                    "exit_state": "terminated_after_results" if forced else "exited",
                    "failure_kind": kind, "result_error": error if not parsed else None,
                    "elapsed_ms": round((current - tick) * 1000), **phase_times}
        if parsed and collected is not None and current - collected >= exit_grace:
            if shutdown and terminate_completed(process, identity, args):
                forced = True
                continue
            reason = "结果已收集，但未确认进入退出阶段或无法核验进程；保留进程"
            break
        if not parsed and current - last_progress >= idle_timeout:
            reason = "启动/导入或执行无日志进展，保留未完成的进程"
            break
        if not parsed and test_started is not None and current - test_started >= test_timeout:
            reason = "测试调度后超过执行时限，保留未完成的进程"
            break
        time.sleep(poll_seconds)
    return {"status": "blocked_process", "result": parsed, "exit_code": None,
            "exit_state": "still_running", "failure_kind": kind, "reason": reason,
            "result_error": error if not parsed else None,
            "elapsed_ms": round((time.monotonic() - tick) * 1000), **phase_times}


def command(editor, project, check, result, log, run_id, snapshot_id, platform):
    args = [str(editor), "-batchmode", "-forgetProjectPath", "-projectPath", str(project),
            "-logFile", str(log), "-buildTarget", platform]
    if check["mode"] == "audit":
        args += ["-executeMethod", check["execute_method"], "-quit",
                 "-handoffResultPath", str(result), "-handoffRunId", run_id,
                 "-handoffInputSnapshotId", snapshot_id]
    else:
        # Test Framework 1.1.33 明确警告 -quit 会阻断命令行测试。
        args += ["-runTests", "-testPlatform", check["mode"], "-testResults", str(result)]
        for field, flag in (("test_filter", "-testFilter"), ("assembly_names", "-assemblyNames")):
            if check.get(field):
                args += [flag, check[field]]
    return args
