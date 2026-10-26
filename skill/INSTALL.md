# GM Scene Handoff 独立安装与分发

技能安装到个人目录后使用。公开分发入口为 [taozhang159/gm-scene-handoff](https://github.com/taozhang159/gm-scene-handoff)，安装和更新均使用下面的固定命令。[飞书安装文档](https://youzu.feishu.cn/wiki/CnH5wp6FJigMuUkwUuYchLhtnLg) 保留命令和使用说明，`.skill` 附件继续支持离线安装。技能仅用于 GMGame，不是任意 Unity 项目的通用合并工具。

项目不再提供 `.agents/skills/gm-scene-handoff` 技能入口。维护源码位于 `Tools/SkillSources/gm-scene-handoff/`，仅供维护、验证和重新打包，不作为项目技能加载。未安装个人版时先按下面步骤安装。

## 一行安装与更新

需要 Node.js 18+（包含 npm/npx）、Git 和 Python 3.11+。Windows、macOS、Linux 使用同一条命令：

```sh
npx --yes --prefer-online github:taozhang159/gm-scene-handoff#main install
```

可以从任意目录安装；有新发布版本时再次运行相同命令即可升级。没有 GMGame 项目时也可先安装技能，实际合并仍需要 GMGame、Unity 和 Unity MCP。`main` 只承载校验通过的完整发布包，不作为日常源码开发分支。

如果游戏仓库还存在同名旧技能，在该仓库中运行以下命令，额外停用项目内旧入口：

```sh
npx --yes --prefer-online github:taozhang159/gm-scene-handoff#main install --workspace .
```

安装器会自动寻找 Python 3.11+，也可用 `--python` 指定。`install` 和 `update` 等效；`--help` 查看参数，`--json` 输出安装结果。文件与配置均已完整一致时，不重复创建备份。未显示新版时重启 Codex。

标准安装位置为当前用户的 `~/.agents/skills/gm-scene-handoff/`，Windows 通常为 `%USERPROFILE%\.agents\skills\gm-scene-handoff`。该位置已有技能时先备份再更新，没有则创建并安装。若此前使用 `--user-home` 自定义了用户目录，更新和查询时需传入相同参数；安装器不会全盘搜索任意位置的副本。

## 确认本地版本

```sh
npx --yes --prefer-online github:taozhang159/gm-scene-handoff#main status
```

`status` 只读查询实际安装版本、目录和文件完整性，并显示本次下载包版本。没有安装时明确提示未安装，不会写入文件或配置。`--version` 仅显示下载的分发包版本，不能代替 `status` 判断本地安装情况。

首次安装提示 `安装完成：GM Scene Handoff 1.2.1`；升级提示例如 `更新完成：GM Scene Handoff 1.2.0 → 1.2.1`，并显示安装位置和备份位置。版本相同且文件完整时提示已经是当前发布版本。

给同事的简短提示词：

> 请安装或更新 https://github.com/taozhang159/gm-scene-handoff 中的 gm-scene-handoff，使用仓库的一行命令；完成后运行 status，告诉我本地版本和安装路径。只安装更新，不执行场景合并。

## 附件离线安装

1. 将附件下载到本地。
2. 在 Codex 中打开 `small-game-puzzle` 仓库根目录，也可以打开其 `GMGame/GMGameProject` 子目录。
3. 把下载文件的完整路径发给 Codex，输入：

> 请安装我下载的 gm-scene-handoff.skill（文件路径：填入实际完整路径）。将它作为 ZIP 解包到项目外的临时目录，先阅读包内 INSTALL.md、package.json 和安装脚本，再按说明安装到个人技能目录，用于当前 GMGame 仓库。检查包完整性，停用此仓库同名旧版，只安装技能，不合并、不提交、不推送。

4. 安装程序会输出版本、安装位置、项目位置、配置备份和停用的旧技能路径。安装程序修改了个人技能配置后，重启 Codex；打开原仓库，在设置的技能列表中查找 **GM Scene Handoff（独立安装版）**，确认路径在个人目录，且已启用。具体 UI 分组可能随客户端版本变化，应出现在个人技能范围，不需要出现在项目专属分组。

`.skill` 在这里是 ZIP 归档后缀，不是 Windows 可执行安装器；无需双击，也不依赖操作系统的文件关联。Codex 按说明运行包内脚本。下载文件的位置不是安装位置。

## 安装执行细节（供 Codex 使用）

需要 Git 和 Python 3.11+。先检查归档条目全部位于 `gm-scene-handoff/` 下且无绝对路径、`..`、符号链接，再解包；不要直接覆盖任何已安装目录。安装程序只使用 Python 标准库。

```powershell
# 以下变量由实际下载位置、解包结果和当前工作区确定，不照抄占位符。
python -B -X utf8 "$unpacked/gm-scene-handoff/scripts/install.py" --workspace "$workspace"
# 没有 GMGame 仓库时只安装个人技能：
python -B -X utf8 "$unpacked/gm-scene-handoff/scripts/install.py" --global
```

安装位置为当前用户 `~/.agents/skills/gm-scene-handoff/`，位于游戏 Git 仓库外。个人配置使用 `$CODEX_HOME/config.toml`，未设置时用 `~/.codex/config.toml`。安装器会：

- 校验包清单内全部文件 SHA-256；指定 workspace 时识别仓库根和 Unity 项目。SHA-256 用于完整性核对，不代表发布者签名。
- 安装完整说明、脚本、流程快照及 UI 元数据。
- 在个人配置中启用独立安装版；指定 workspace 时按绝对路径停用此仓库根、Unity 目录及中间目录中的同名项目技能。若存在旧个人 `~/.codex/skills/gm-scene-handoff`，也停用该入口。未来这些位置出现同名文件也继续停用。不会删除或修改项目内旧文件。
- 更新已有独立安装版之前，把旧目录和原个人配置保存在 `~/.agents/skill-backups/`，备份不在技能发现目录内。
- 不切分支，不执行 Git 合并、提交、推送，不写入游戏项目，不启动或关闭 Unity。

配置有无法安全保留的特殊格式或重复路径时，安装器报错并停止。由 Codex 检查相关 `skills.config` 项后处理，不覆盖整个配置文件。重装可用于升级；合并进行中先完成或妥善结束该轮，再升级技能。

## 日常使用

从设置选择个人目录中的 **GM Scene Handoff（独立安装版）**，或明确说“使用个人目录安装的 `$gm-scene-handoff`”：

- 同步基础分支：“使用个人目录安装的 gm-scene-handoff，将最新 develop_base 合并到当前开发分支，并同步到我的个人测试场景。”
- 交付开发分支：“使用个人目录安装的 gm-scene-handoff，将当前开发分支交付到 develop_base，把个人场景增量合入对应基础场景。”
- 只读检查：“使用个人目录安装的 gm-scene-handoff，只分析当前分支与 develop_base 的差异和冲突，不改文件、不提交。”

实际合并需要匹配项目版本的 Unity Editor 保持打开，并配置可控制该项目的 Unity MCP；安装包不会安装 Unity 或配置 MCP 凭据。默认沿用现有技能：验证通过后创建结果提交，并自动推送本次目标分支；如需等待人工验收或不推送，调用时明确说明。

技能安装在项目外，因此两个方向的 Git 合并及分支切换不会改动已安装技能的文件。项目内容变化仍可能影响合并条件、测试可用性与兼容性，执行时要做现有预检，不能把“技能文件不变”理解为所有合并都必定成功。

## 版本、维护与回退

**1.2.1**：在 1.2.0 的 npx 安装入口基础上，增加 `status` 本地版本和完整性查询、升级前后版本提示及简短安装提示词。保留无项目安装、幂等检查、校验、备份、失败回滚及配置保护。合并规则与工具逻辑沿用 1.1.1，安装器测试不代表真实场景合并或 Unity 业务回归。

1.2.0 已在 macOS 验证 15 项安装与分发测试，以及 npm 打包后的实际 npx 安装和重复执行。1.2.1 新增本地版本只读检查、损坏文件识别和升级提示测试。完整工具测试中的 15 项历史批处理进程测试依赖 Windows/Linux 进程接口，在 macOS 不适用；历史 Unity 批处理启动器仍只支持 Windows。当前推荐的已打开 Unity Editor + MCP 合并流程保持原样。

包版本见 `package.json` 的 `version`；发布者同时保留完整文件哈希与源提交信息。源码继续维护在项目 `Tools/SkillSources/gm-scene-handoff/` 和 `Docs/Workflows/SceneHandoff/`；包内参考文档是发布时生成的快照，不单独手改。

构建入口为项目内 `Tools/SkillSources/gm-scene-handoff/distribution/build_package.py`：

```powershell
python -B -X utf8 "$project/Tools/SkillSources/gm-scene-handoff/distribution/build_package.py" --version <新版本号> --output "$project/Docs/Workflows/SceneHandoff/Distribution/gm-scene-handoff.skill"
```

公开包的构建入口为同目录下的 `build_public_package.py`：

```sh
python -B -X utf8 "$project/Tools/SkillSources/gm-scene-handoff/distribution/build_public_package.py" --version 1.2.1 --repository taozhang159/gm-scene-handoff --output "项目外的新暂存目录"
```

该命令只生成独立分发目录，不上传、不复制游戏工程。版本更新时先修改版本说明，运行适用的打包与安装测试，再生成新版本目录，将确认的分发内容发布到公开仓库 main。输出目录必须是新目录，不能直接覆盖现有发布或工作区。

发布前运行技能校验、打包/安装测试、已有工具测试，检查包内链接完整及可从仓库根定位 Unity 项目。实际公开下载和安装验证通过后，飞书保留固定安装命令，无需每次更换附件；成员通过重复运行命令升级，不随游戏分支自动升级。

2026-10-09 将项目发现目录迁到维护目录后，已发布的 v1.0.0 包保持原字节和版本；它已自带完整运行文件，不依赖项目旧技能目录。包内维护路径及历史交付证据记录发布时的位置；当前源码路径以本页为准。删除项目入口需随 Git 更新传到其他分支；尚未更新的分支由安装器在个人配置中停用旧入口。

回退时先停止技能任务，再让 Codex 根据安装输出的备份恢复旧技能目录。个人配置仅恢复本次涉及的技能启用项，不能用旧配置整份覆盖安装后新增的其它设置。新电脑、新用户或搬迁项目后重新执行安装，以刷新对应项目的旧版停用路径。

Codex 的个人技能发现及配置规则见 [官方技能说明](https://learn.chatgpt.com/docs/build-skills)。本包按本地技能目录安装，不声明为官方插件安装格式，也不承诺所有客户端都支持直接导入 `.skill` 文件。
