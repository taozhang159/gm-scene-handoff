# GM Scene Handoff

GMGame 场景合并技能的公开分发包。版本：**1.2.2**。

## 安装与更新

先准备 Node.js 18+（含 npm/npx）、Git 和 Python 3.11+。Windows、macOS、Linux 使用同一条命令：

```sh
npx --yes --prefer-online github:taozhang159/gm-scene-handoff#main install
```

首次安装和以后升级都运行这一条命令。发布分支 main 只放完整发布包；安装器校验文件、备份旧版、更新个人技能并保留其他配置。已完整安装相同版本时不会重复写盘或备份。

安装位置为当前用户的 `~/.agents/skills/gm-scene-handoff/`（Windows 通常为 `%USERPROFILE%\.agents\skills\gm-scene-handoff`）。此目录已有技能时备份并更新，没有则创建并安装。自定义过用户目录的安装需沿用 `--user-home`，不会全盘查找其他副本。未显示新版时重启 Codex。

如果 GMGame 仓库存在同名旧技能，在该仓库中运行：

```sh
npx --yes --prefer-online github:taozhang159/gm-scene-handoff#main install --workspace .
```

可通过 `--python` 指定 Python，通过 `--user-home` / `--codex-home` 指定安装和配置目录。`--help` 显示全部选项，`--json` 输出结构化结果。

## 执行进度

程序启动后实时显示 Python 检查及校验、备份、安装阶段。`--json` 保持纯 JSON 输出。

npx 需要先获取发布包，技能不能在下载完成前输出进度。Windows PowerShell 如需立即看到等待提示和下载日志，可执行：

```powershell
Write-Host '正在从 GitHub 获取技能，请稍候…'; npx --yes --prefer-online --loglevel=http github:taozhang159/gm-scene-handoff#main install
```

查询时把最后的 `install` 改成 `status`。不显示无法测量的百分比。

## 查询本地版本

```sh
npx --yes --prefer-online github:taozhang159/gm-scene-handoff#main status
```

`status` 只读查询个人目录中的实际安装版本、路径和文件完整性，同时显示本次下载包版本；未安装时明确提示未安装，不会偷偷安装。`--version` 仅显示下载包版本，不用于判断本地版本。

安装后会输出 `安装完成：GM Scene Handoff 1.2.2`；升级时输出旧版本与新版本，例如 `更新完成：GM Scene Handoff 1.2.0 → 1.2.2`。已经完整安装相同版本时提示版本无需更新。

## 给 Codex 的简短提示词

> 请安装或更新 https://github.com/taozhang159/gm-scene-handoff 中的 gm-scene-handoff，使用仓库的一行命令；完成后运行 status，告诉我本地版本和安装路径。只安装更新，不执行场景合并。

## 使用范围

技能适用于 GMGame 的既定目录与场景流程。安装可在没有游戏仓库的机器上完成；实际合并需要有权访问的 GMGame 项目、匹配的 Unity Editor 和 Unity MCP。安装不会下载游戏工程或执行合并。

在目标项目中告诉 Codex：使用个人目录安装的 `$gm-scene-handoff`，并说明同步或交付方向。详细说明见 [INSTALL.md](skill/INSTALL.md)。

本次验证覆盖安装、更新和配置保护，未执行真实 Unity 合并回归。历史 Unity 批处理启动器仅支持 Windows；当前使用流程要求已打开的 Unity Editor 和 Unity MCP。

## 版本维护

本仓库只分发技能、运行脚本和流程说明；维护源码由发布者管理。用户始终运行上面的固定命令；飞书等说明页无需随版本替换附件。回退可使用安装输出中的备份。
