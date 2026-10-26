> 本页随独立安装版发布；`<PROJECT>` 是定位后的 Unity 项目，`<REPO>` 是仓库根。`$skillRoot` 是本技能安装目录，工具必须从此目录调用。

# 历史隔离批处理工具参考

本页仅供维护已有批处理证据、工具回归测试或用户另行明确授权的旧任务使用。两个原目录合并操作不走本页，不创建隔离区、不启动/关闭 Unity，不执行工作区释放。运行旧 run 命令还须显式传 --allow-editor-launch；不能将该开关当作用户授权。

# 原批处理说明

执行合并或需要批处理验证时读取本页。仅修改说明文档不运行 Unity。入口为个人安装目录中的 `scripts/handoff.py`（[维护源码](../scripts/handoff.py)），Python 3.11+，只使用标准库。Windows 支持 Editor 预检与进程管理；快照和证据处理没有 Unity 依赖。下文 `$skillRoot` 为当前使用的个人技能安装目录。

本工具不执行 Git 合并、场景迁移、用户数据备份/恢复、提交、推送或工作区删除。三方语义、范围授权和两层验收继续遵守 [执行合并流程](merge-workflow.md)。第一版没有通用场景合并器，也不自动缩减测试覆盖。

## 路由与停止条件

1. 优先复用连接到**目标验证项目**的 Unity MCP；核对项目路径。该路由继续使用 MCP 的测试结果，不为接入本工具额外启动 Editor。
2. 需要独立批处理时，使用本页启动器，测试和已有 Editor 审计共用预检、唯一结果目录、进程归属及退出管理。同一目标只有一个受控写入者。
3. 同类环境/编译失败且条件未变时，工具拒绝重复启动。先诊断，有具体修复再试；外部条件修复不能由文件/环境变化表示时，以 `--recovery-evidence` 指向实际修复记录。不能只新建空文件或改参数绕过停止条件。
4. 结果完整与 Editor 退出是两个状态。仅在本轮结果写出之后出现退出标志、超过宽限期且原生进程句柄/开始时间仍匹配时，结束本任务已完成的 Editor，记录退出异常。结果缺失、崩溃、旧 XML、截断、零用例、跳过用例和审计身份不符均不能报通过。
5. 超时、中断或无法证明进入退出阶段时，记录阻断并保留进程；下一轮先检查占用。不得按进程名批量终止、删除 Unity 锁或接管用户 Editor。
6. 达到本轮要求的停止点后结束；没有新输入或具体疑点，不继续扩展测试和整理报告。工具通过仅表示计划内验证通过，不代表人工验收、完整性验收、提交或推送完成。

## 工作区与缓存

用 `git worktree list --porcelain` 选择同仓库、同项目相对路径的独立 linked worktree。不要每次都新建或全量复制 Library。已打开的开发项目不能作为目标。

工具的 `workspace` 默认只读检查。`--claim` 在空闲、干净工作区登记任务归属；同一任务续跑保留变更。另一任务要复用时，仅允许显式登记干净且空闲的工作区，旧归属记录保留。无关脏文件、未提交交付或活跃 Editor 会阻止接管，不自动 reset、detach 或移除工作树。

登记、独占锁和进程记录放在该 worktree 的 Git 管理目录，不进入仓库交付数据。操作系统文件锁会在启动器退出后释放；Unity 自己的锁不由工具删除。

缓存状态：

| 输出 | 含义 |
|---|---|
| `absent` | 尚无 Library，允许正常首次导入 |
| `incremental_candidate` | 项目身份、Unity 版本、宿主、目标平台、包清单/锁和项目设置匹配，可尝试增量导入；不保证缓存内部完好 |
| `requires_import_or_rebuild` | 条件有变化或没有可核实历史；交给正常解析/导入，不直接认定有效 |

Library 只提供导入缓存，不提供“测试已通过”的证明。旧验证必须匹配实际输入及计划。Library 内部损坏时保存日志，改用独立重建或其他已确认工作区，并记录恢复；不改开发项目缓存、不使用 `-noUpm` 绕过解析、不无条件删除旧缓存。本工具不自动复制或清理 Library。

候选满足归属、干净和空闲条件后，优先选择同版本、同平台且曾完成目标验证的工作区；同一任务复用原候选。不为每次合并另建一个冷缓存目录，也不为了预热在应用最终候选前额外启动 Unity。准备阶段记录所选工作区、缓存状态及选择理由。

缓存诊断分开看 `run.json` 的 `snapshot_elapsed_ms`、`test_dispatch_after_ms`、`total_elapsed_ms` 和结果 JSON 的 `duration`。调度前时间包含启动、导入、编译与框架准备，不能全称为导入时间；只有 Editor 日志能支持具体归因。若 incremental_candidate 仍明显慢于该机器相同条件的近期成功记录，检查包解析、资源导入和编译日志，记录已证实原因或“未定位”，不删除缓存尝试提速。没有可比记录时建立本机基线，不承诺固定分钟数。

## 最小使用顺序

下面的变量由本轮真实路径和任务标识填写，不将示例值当默认作者或分支。命令可以从任意工作目录运行；`$tool` 应指向本次维护版本的脚本。先完成工作区登记，再写入交付证据和应用合并结果。

```powershell
$tool = Join-Path $skillRoot 'scripts/handoff.py'
python -B -X utf8 $tool workspace --source $sourceProject --project $targetProject --task-id $taskId --platform Win64 --claim
python -B -X utf8 $tool snapshot --project $sourceProject --scope $scope --output "$evidence/source-snapshot.json"
# 按原流程固定/归档来源、合并、检查场景，并准备用户数据保护。
python -B -X utf8 $tool snapshot --project $targetProject --scope $scope --output "$evidence/target-inputs.json"
python -B -X utf8 $tool preflight --source $sourceProject --project $targetProject --plan "$evidence/validation-plan.json" --evidence $evidence --editor $editor
python -B -X utf8 $tool run --source $sourceProject --project $targetProject --plan "$evidence/validation-plan.json" --evidence $evidence --snapshot "$evidence/target-inputs.json" --check edit --editor $editor
```

`$evidence` 必须位于目标项目 `Docs/SceneHandoffs/<本轮目录>/`。来源快照记录完整 SHA、脏文件路径与字节哈希；**不包含未提交内容原件**，原流程要求的来源归档仍须保存。不要让源项目和目标项目同时写入本轮输入。

快照覆盖 Assets、Packages、ProjectSettings 的全部文件身份及工具版本：通过 Git 工作区状态识别变化，干净已跟踪文件记录 `git:<blob>`，未提交和未跟踪文件记录实际字节 SHA-256，不以 HEAD 代替输入，也不维护只有 mtime 的自制缓存。未知新文件同样纳入。来源脏文件的原字节哈希单独保存。包含外部链接或 `file:` 包依赖的输入先明确支持范围，不能把未捕获的依赖认定为已固定。

需要对干净文件也逐字节核验时，快照命令加 `--full-content`，计划加 `full_content_snapshot: true`，本轮始终使用该模式。大项目的全量资源读取可能耗时较长，不为每个阶段无条件增加该成本。普通模式的干净文本身份遵循 Git 的行尾/过滤规则；LFS 实体和资源完整性仍按原流程检查。恢复到原字节的已提交文件可由 `verify` 定向核验，不因提交本身重新读取所有资源。

Editor 从项目 ProjectVersion.txt 读取版本，依次使用明确的 `--editor`、`UNITY_EDITOR_PATH`、已运行 Editor 的安装位置和常规 Hub 安装位置，检查可执行文件产品版本。路径不会写入便携报告。Windows 已有效的环境目录不覆盖；ALLUSERSPROFILE 缺失时，仅对子进程使用有效 PROGRAMDATA，不更改系统变量。诊断只显示有效性，不导出环境或凭据。

### 验证计划

`validation-plan.json` 由实际改动确定检查项和理由，示例中的 SHA 须换成固定的完整提交号：

```json
{
  "task_id": "本轮唯一标识",
  "source_commit": "<完整来源SHA>",
  "source_snapshot": "source-snapshot.json",
  "target_base_commit": "<固定目标基线SHA>",
  "scope_authorization": "本轮用户已授权的来源与未提交范围",
  "target_platform": "Win64",
  "protection_record": "user-data-protection.json",
  "checks": [
    {"id": "edit", "mode": "EditMode", "reason": "本轮变更涉及的逻辑验证", "assembly_names": "<实际程序集>", "min_tests": 1},
    {"id": "play", "mode": "PlayMode", "reason": "本轮场景交互和恢复验证", "test_filter": "<实际测试类或表达式>", "min_tests": 1}
  ]
}
```

省略 `assembly_names`、`test_filter` 表示该模式全部测试；不要把示例占位符传给 Unity。`min_tests` 是防止错误筛选的数量下限，不能代替覆盖范围核对。每个 check 单独调用 `run --check <id>`；不在同一项目并行执行。第一版不强行把 EditMode、PlayMode 与审计塞进单个 Editor 会话。

开始运行前，提供 `user-data-protection.json`，至少包含 `task_id`、`status: "prepared"`、`method: "backup"` 或 `"isolated"`、`details`。其中说明已经实际完成的存档和章节偏好保护及其证据位置。工具核对归属、状态并绑定文件哈希；该记录不是自动完成备份的功能。隔离配置应在目标快照前生效，其后恢复配置是否影响有效输入，按原流程判断。

### Editor 审计适配

已有审计入口可以使用 `mode: "audit"` 和 `execute_method: "Namespace.Type.Method"`。方法读取 `-handoffResultPath`、`-handoffRunId`、`-handoffInputSnapshotId` 参数，在所有检查结束后输出 JSON：`run_id`、`input_snapshot_id`、`complete: true`、`status: "passed"` 或 `"failed"`，并保存实际检查明细。

完整结果写出后打印 `[GMHandoff] result-complete <本轮run_id>`，再正常返回退出。结果后仍没有可核实退出标志时，启动器保留进程并报告阻断。尚未适配的审计继续走原工具；不能仅写上述字段而省略真实检查。本轮没有新增或注入 C# 审计脚本。

### 计时、续跑与结果

每次启动产生唯一 run_id，原始 XML/审计 JSON 和 Editor 日志放在目标 `Library/HandoffValidation/<run_id>/`。便携目录 `validation/<run_id>/` 保存运行前后快照、计划、规范化结果和 `run.json`；失败不覆盖。便携摘要不复制原始错误文本、环境或绝对进程路径；跨机器交付仍需按原流程脱敏归档原始证据，保留原始哈希。

`run` 默认复用同检查、同计划、同实际输入且原始结果/摘要哈希均有效的最后一次通过；后来的失败不能被早先通过掩盖。工具/包/配置/测试或目标 HEAD 变化都需重新判断。本版不自动跨不同输入拼接通过项，依赖不明时扩大复测。

时间参数分别是 `--idle-timeout`（默认 600 秒，无日志进展）、`--test-timeout`（默认 1800 秒，从测试调度日志起）、`--exit-grace`（默认 45 秒，完整结果后的退出宽限）。持续导入且有进展不使用固定总时限截断。测试调度时间可能含框架准备，不能称为纯测试时间；纯用例执行时间取 XML duration。采用单调时钟计时，事件时间带时区，run.json 同时记录快照、调度、结果出现和总耗时。默认值需结合团队机器调整，不是性能承诺。

## 恢复、汇总与只读校验

### 定向诊断与最终回归

保留原 `validation-plan.json`。诊断计划另存为 `diagnostic-plan-<序号>.json`，沿用真实 task_id、来源和数据保护记录，使用独立 check id、`test_filter` 或 `assembly_names`，在 reason 写明原失败 run_id、修复与选择范围。仍经 snapshot/preflight/run，在同一目标项目串行执行，保留失败记录；筛选为零不能算通过。测试相互污染时筛选整个相关类或程序集，不能只跑孤立方法掩盖问题。

修复完成后使用原交付计划生成最终快照并运行计划项；最终 summarize 只传原计划。诊断计划的哈希不同，其结果不能填补最终计划项，也不允许跨快照拼接。没有输入变化且原计划已有有效结果时沿用现有复用机制。报告中的诊断运行单独引用，不计入最终有效用例数量。

### 全过程计时

使用个人安装目录中的 [handoff_timing.py](../scripts/handoff_timing.py) 记录真实里程碑，不回填猜测时间。它只计时，不执行或证明 Git、验证和解除占用操作。任务启动时在源工作区 Git 管理目录保存记录，路径通过 `git -C <源项目> rev-parse --absolute-git-dir` 取得；在其下为本轮唯一 task_id 创建 `handoff-timings/<task_id>`。task_id 使用不含路径分隔符的安全名称。同一任务串行写入，续跑不重记 started，也不覆盖旧记录。

```powershell
$timer = Join-Path $skillRoot 'scripts/handoff_timing.py'
# $timingDir 为上述 Git 管理目录下本轮独有目录，不写进受测输入。
python -B -X utf8 $timer --directory $timingDir --task-id $taskId --event started
# 实际完成对应步骤后记录：prepared、merged、validation_complete、cleanup_complete、
# committed、push_verified、released；不适用或未成功的步骤省略，不能提前记录。
python -B -X utf8 $timer --directory $timingDir --task-id $taskId --event finished
python -B -X utf8 $timer --directory $timingDir --task-id $taskId
```

prepared 表示范围和工作区准备完成；merged 表示候选合并与场景迁移完成；validation_complete 只在原交付计划通过后记录。push_verified 必须有远程 SHA 核对，released 必须有工作区占用核对；仅本地交付无需这两项。finished 表示达到用户要求的停止点，不能单凭该事件声称已推送。阻断时不记 finished，汇总标记尚未结束。

最终回复报告 started 到 finished 的墙钟跨度及各实际里程碑，注明包含等待；无 finished 时只报告到最后记录点。运行内部使用原有单调时钟，跨进程里程碑使用带时区的系统时间；系统时钟调整会影响跨度，回退时工具拒绝新增记录，应保留并说明。并行工作和嵌套时间不相加。记录从中途才开始时明确覆盖区间，不冒充端到端耗时。

提交前可将当时的只读汇总归档到本轮证据目录；提交、推送、解除占用的后续事件留在 Git 管理目录并在最终回复报告，避免为补最终时间循环提交。该本机记录不会随 Git 推送，同事获取的是工具和规则。

### 恢复与汇总命令

先按原流程恢复确认属于本轮的材质/配置/用户数据副作用，再提供 `cleanup.json`（至少 `task_id`、`status: "complete"`、`user_data_verified: true`、`details`）。并行外部修改不能自动还原。文件清单 `delivery-files.json` 使用项目相对路径：

```json
{"files": ["<本轮交付文件>"], "deleted": ["<明确授权删除的文件>"]}
```

```powershell
python -B -X utf8 $tool summarize --project $targetProject --evidence $evidence --plan "$evidence/validation-plan.json" --cleanup-record "$evidence/cleanup.json" --files "$evidence/delivery-files.json" --output "$evidence/summary-<本轮时间>"
python -B -X utf8 $tool verify --project $targetProject --manifest "$evidence/summary-<本轮时间>/result-file-hashes.json"
```

汇总重新扫描最终实际输入，输出 `test-results.json`、`tested-inputs.json`、`result-file-hashes.json`、`验证结果与计时报告.md` 和不自引用的 `summary-hashes.json`。保留常用文件名及 runs/effective_count/effective_tests 字段；旧交付的专用检查器并非通用格式接口，不自动重写旧 JSON 或升级旧 schema。原来的合并清单、核验依据和合并报告引用这些结果，不再手工抄录同一组测试数字。

若测试期间产生了可归因副作用，`run.json` 会标为 `inputs_changed`。只有最终输入精确恢复到受测快照，且 cleanup 的 `restored_files` 为每个变化路径记录 `run_id`、`before_identity`、`after_test_identity`（取对应快照的文件身份）和非空 `attribution`，汇总才可采纳其实际通过结果；不自动恢复、不把尚未解释的变化算通过。运行时隔离配置与最终交付输入不同且未证明等效时，本版保守地要求补充验证，不自动豁免。

`validation_complete` 仅指所有计划项存在有效结果。缺项输出 `validation_incomplete` 和非零退出码；即使已有用例全部通过，也不隐藏缺项。所有命令失败使用非零退出码。`verify` 核对交付文件、删除落实、依赖证据以及汇总报告/JSON 的哈希；结果清单不包含自身。已有汇总目录不覆盖，后续报告使用新目录。报告不自动记录最终提交号，避免循环改文档。

## 工具自身验证

```powershell
python -B -X utf8 -m unittest discover -s "$skillRoot/scripts/tests" -v
```

用例使用独立临时 Git 仓库、中文/空格路径和真实 Python 子进程，覆盖错误结果、进程残留、进程身份变化、同项目互斥、缓存变化、未提交输入变化、重试停止、续跑及报告篡改。它们不启动 Unity，不代表本机真实合并已测得加速。真实 Unity 性能应在经选择的隔离项目上，用相同来源、目标、测试计划分别记录冷/热缓存；已有开发 Editor 不用作该验证。
