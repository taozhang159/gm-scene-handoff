> 本页随独立安装版发布；`<PROJECT>` 是定位后的 Unity 项目，`<REPO>` 是仓库根。`$skillRoot` 是本技能安装目录，工具必须从此目录调用。

# 执行辅助工具与续跑

执行合并时按需读本页，工具仍为个人安装目录的 `scripts/handoff.py`。这些命令只读取业务文件、写入指定证据，不执行 Git 合并、场景写回、存档恢复、删除或 Editor 解锁。场景基准、语义裁决和验证要求仍按 [合并流程](merge-workflow.md) 与 [场景记录](scene-sync.md)。维护源码：[handoff_steps.py](../scripts/handoff_steps.py)。

## 阶段与失败处理

按“固定输入 → 受控合并与场景应用 → 导入就绪 → 验证 → 恢复汇总 → 提交推送”推进。在需要等待用户、遇到中断或完成较大阶段时保存 checkpoint；不为每条查询增加记录。工具已经返回有效路径和身份时，后续直接引用，不反复输出完整快照、场景 YAML 或用例列表。

每个修改动作必须检查退出码并验证结果，再执行依赖步骤。PowerShell 的原生命令非零退出不一定触发 `$ErrorActionPreference`，使用下列显式检查；不要把写回、删除、校验和解锁串在不检查退出码的一串命令中：

```powershell
python -B -X utf8 $tool scene-guard-check --project $project --guard "$evidence/scene-guard.json" --candidates "$evidence/candidate-hashes.json" --output "$evidence/scene-check-before-import.json"
if ($LASTEXITCODE -ne 0) { throw '场景保护检查未通过；停止依赖步骤，保留现场及锁恢复方法' }
# 只有结构/引用检查、此检查以及当前 Editor 状态均通过，才按原流程恢复刷新。
```

Git merge 的非零退出可能表示冲突；先分类并完成原冲突流程，不能把它当成功，也不盲目重跑合并。不得在无条件 finally 中解锁并导入冲突文件。取消时按原流程协商保留/恢复现场。

## 按需读取与紧凑输出

- 先用文件清单、name-status/shortstat 和规则目录定位范围，再读取相关差异与章节；已加载且未变化的规则不重复全文读取。独立的只读查询可批量并行，写入、状态切换和依赖检查保持顺序，每步确认成功。
- 原始 MCP 响应、测试明细和诊断日志完整落盘，对话返回状态、计数、失败用例、关键断言及证据路径；必要时再读取对应上下文。不要为减少输出截断原始证据，也不要把大型 JSON 内联进 shell 命令；使用文件写入工具或支持流式输入的接口，确认写入完成且可解析后再接入验证工具。
- Unity 脏资源查询优先输出项目资产的路径、类型与数量，内置资源和 Library 对象单列数量，异常再展开。完整检查未保存场景与相关可持久化资源；不能把内置字体/Shader 等脏标志直接当成需保存所有资产的理由，也不能据过滤后的摘要断言整个 Editor 无修改。
- 空白告警、冲突标记、引用和场景语义分别检查。Unity 序列化文件的既有空白告警只输出分类摘要并按差异归因，不为清零告警批量改写 YAML/`.meta`；冲突及实际结构/引用错误仍必须处理。

## 场景保护的标准检查

`scene-guard-create` 在接收分支已完成远程对齐、尚未合入开发内容时调用；sync 则在当前开发分支合入主分支前调用。要求 HEAD 等于 baseline，场景没有本地修改。它从 baseline、refs、索引和磁盘取并集，固定非目标场景的字节、索引和不存在状态；所有 Git 路径使用 NUL 分隔，支持中文、空格及重命名路径。

白名单文件格式为 `{"files":["Assets/GMScenes/Test/目标场景.unity","Assets/GMScenes/Test/目标场景.unity.meta"]}`。路径根据本轮方向与已核实配对填写。`--refs` 传固定来源 SHA 和涉及移动/删除的历史 SHA，不猜来源。该辅助工具只接管既有目标场景；新增、删除、移动及缺少配对场景仍按原流程裁决，不扩大白名单绕过限制。

```powershell
python -B -X utf8 $tool scene-guard-create --project $project --baseline $targetBefore --refs $sourceCommit --allowlist "$evidence/scene-allowlist.json" --output "$evidence/scene-guard.json"
```

完成候选语义/引用审核后、写回之前，把批准的 R 文件 SHA-256 和原目标 `.meta` SHA-256 保存为 candidate-hashes.json：

```json
{"path_base":"project","files":{"Assets/GMScenes/Test/目标场景.unity":"批准的候选 SHA-256","Assets/GMScenes/Test/目标场景.unity.meta":"原目标元数据 SHA-256"},"deleted":[]}
```

写回并暂存明确目标路径后运行 `scene-guard-check`。它同时检查整个索引无未解决冲突、白名单外场景磁盘/索引/存在性不变、白名单与审核候选一致、目标 `.meta` 字节不变。检查返回 passed 仅证明这些条件，不证明 Unity 引用、功能或 Editor 就绪。第一次在恢复导入前检查，提交前若 Unity 或用户可能改动场景，再使用新的输出路径检查；失败证据不覆盖。不根据写回后的文件反向生成“批准候选”哈希。

## 中断后的紧凑续跑

准备阶段记录 JSON，路径均相对本轮证据目录；`evidence_files` 引用已经生成的来源快照、A/S/T/R 场景记录、保护记录及已完成验证，不重新生成同内容快照：

```json
{
  "task_id":"本轮标识",
  "phase":"scene_applied",
  "next_action":"确认原 Editor 已完成导入后进入验证",
  "lock_state":"released",
  "editor_session":"实测的进程与启动时间身份",
  "notes":"填写实际待办、冲突决定索引和原锁恢复方法；无待办也明确说明",
  "evidence_files":["source-snapshot.json","scene-sync.json","scene-guard.json"]
}
```

```powershell
python -B -X utf8 $tool checkpoint --project $project --evidence $evidence --record $checkpointInput
python -B -X utf8 $tool resume --project $project --evidence $evidence
```

checkpoint 按序保存且不覆盖历史；resume 只回传最新阶段、下一步、锁状态、证据变化、未收口票据和运行状态。检测 HEAD/分支或证据变化时返回 blocked，先检查原因；符合预期的阶段转换可在核实后新增 checkpoint。ready 只代表记录身份一致，不代表当前输入或 Editor 已验证。恢复时仍实测会话及当前输入，依照 editor-begin 的原有身份协议复用结果；不能把记录中的阶段文字当成功证明。旧任务无 checkpoint 时从已有证据重建一次，不为生成记录重做合并。

## 测试调度与结果收口

同一 Editor 串行运行所需检查。把一组测试组织成连续步骤：

1. 测试发现接口明确完成并返回完整清单后，生成计划；异步文件尚未产生时等待完成状态，不把文件缺失当解析故障反复重试。
2. 保存新鲜会话观察并调用 editor-begin。返回 reused 时跳过调度；ready 时再次确认就绪，立即调度指定选择器。
3. 保存真实调度响应与 job_id。依工具支持使用有界等待获取作业结果，通常每次等待 30–60 秒；不提高轮询频率来“提速”，没有变化时不反复读取完整结果；等待时正常向用户报告进度。
4. 确认作业完成、退出播放并恢复就绪，立即取得 sessionAfter 和完整结果，调用 editor-finish。无相关异常时，中间不插入业务探索、报告撰写或重复阅读规则。
5. 原始结果完整落盘，CLI 只返回状态、运行 ID、结果路径和耗时。inputs_changed 时先使用下方恢复清单，再按原恢复协议收尾。

工具没有内置 MCP 客户端，以上由 Agent 使用当前连接编排；不能把此流程描述成已实现的一键 MCP 调度器。run.json 自动记录 dispatch_delay_ms、job_elapsed_ms、collection_delay_ms 和 after_snapshot_ms；最后一项包含在收口延迟中，不能重复相加。

失败后遵守 [定向诊断顺序](automation-tools.md#失败后的定向诊断)，先处理各失败组，再运行最终必要覆盖。以下收尾步骤不替代失败诊断，也不能把已失败的结果恢复成通过。

## 恢复差异清单

```powershell
python -B -X utf8 $tool restore-plan --project $project --evidence $evidence --run-id $runId --output "$evidence/restore-review.json"
```

工具复用该运行的前后快照，只读取变化文件当前值，列出 before_identity、after_test_identity 和当前状态：

- matches_after_test：当前仍等于测试后的值，尚需确定是否由测试造成。
- already_restored：内容符合原身份，仍需已有归因证据及设置内存值核对。
- changed_again：出现新的修改，停止该文件恢复并查明归属，不覆盖用户并行编辑。

清单始终标记 needs_attribution，不能直接充当 cleanup.complete。它不备份/恢复用户数据，也不删除新增文件；新增测试档确认归属后移到本任务备份目录。实际恢复依据测试前已保存的原字节，不从经过换行规范化的 Git blob 盲目替换原文件。先区分 Git 内容差异和磁盘字节差异：只有暂存表示变化且受测字节完全一致时，汇总可复用结果；CRLF/LF 互换仍是字节变化，不能自动当作相同。不要在测试通过后仅为清理状态执行 git restore 改写换行；先核对归因及原字节，确认为 Git 内容相同的格式副作用时可保留受测字节、刷新准确路径的索引，并确认暂存没有内容差异。对已确认的导入器空白、换行或设置差异分别判断，不忽略整个类型或 ProjectSettings。内存值、磁盘值和用户数据核对完成后，再用现有 cleanup/summarize 协议收口。

## Unity 项目与 Sources 的统一清单

`manifest` 和 `summarize --files` 均接受显式 path_base，默认 project 兼容旧格式：

```json
{
  "path_base":"repository",
  "files":["GMGame/GMGameProject/Assets/实际交付文件","Sources/Chapter_04/实际源文件"],
  "deleted":[]
}
```

```powershell
python -B -X utf8 $tool manifest --project $project --files "$evidence/delivery-files.json" --output "$evidence/delivery-hashes.json"
```

不需要独立预检清单时直接把上述 delivery-files.json 交给 summarize，避免重复哈希。repository 根由定位后的项目取得，不接受任意外部根。路径不得越界，单份清单不能混用两种相对根；summarize 会按该根自动加入便携验证证据，verify 也按记录的根核对。Sources 不因此变成 Unity 受测输入，不改变快照覆盖范围。

## 最终收尾

最终必要测试通过后，按以下顺序集中完成，复用原始结果和已有快照：

1. 立即完成 editor-finish；inputs_changed 时取得恢复清单并归因，按原协议恢复设置内存值、磁盘字节和用户数据。已证明且精确恢复的工具副作用不触发重复测试；未知变化或实际修复改变受测输入时，仍须完成相应最终验证。
2. 核对最终场景保护、引用及完整 Git 差异，确认没有未解决冲突或无关写入；确认恢复完成后记录 cleanup.complete。保留必要的导入前与提交前场景检查，不因追求一次收尾省略。
3. 用同一份验证记录完成报告、必要的目录链接及交付文件列表；报告区分自动验证、人工待验与构建状态。报告中的结果提交 SHA/推送状态可引用本机后续核验记录或在最终回复说明，避免为填入提交自身 SHA 反复改报告、重做提交。
4. 报告与交付文件确定后生成 summarize --require-complete 并运行 verify，再提交、推送和核对远程 SHA。--require-complete 在缺少有效检查时返回有限的差异路径、运行状态及目标身份，且不创建输出目录；先处理具体原因，沿用同一输出路径收尾，不为报告失败先跑一遍业务测试。默认不带该参数仍兼容历史不完整汇总。文件哈希不能包含哈希清单自身；成功汇总后不再改写已纳入清单的文件。确需修改时重新生成受影响汇总并 verify；是否重跑测试由受测输入身份决定，报告文字修改不自动触发游戏回归。

自动生成的验证报告已含调度、作业、收口及其中快照的耗时表。交付说明引用该报告和原记录，只补充业务范围、场景裁决、清理与人工待验；不另行手工重算全套测试计数或复制大型 JSON。

这里合并的是编排步骤，不省略来源快照、A/S/T/R 裁决、非目标场景保护、完整输入核验、必要测试、用户数据恢复或远程 SHA 核验。

## 计时边界

定位项目和确定任务 ID 后立即记录 started，再开始长时间差异分析及准备；续跑沿用已有起点。保持原里程碑兼容，可增加 git_complete、scene_applied、import_ready、report_complete。只在相应动作实际成功后立即记录；merged 必须晚于场景应用及保护检查成功。validation_complete 表示最终必要验证已确认有效（包括必要的输入恢复核验），cleanup_complete 表示全部恢复核对完成，report_complete 单独记录报告完成，不能把写报告时间都算作跑测试。测试本身耗时取 run.json 的作业起止。

每个里程碑只记一次，返工/等待原因写在续跑记录，不回填猜测时间。时间包含等待与编排，不承诺固定分钟数。优化验证使用临时仓库和模拟会话；真实收益需要同覆盖的后续交付计时。

计时器只读取连续编号的 `000.json` 等记录，忽略同目录的命名作业 JSON；编号缺失、损坏、任务不符和时间倒退仍报错。新任务宜将计时放在 `handoff-timings/<task_id>/timing/`，原始响应放相邻目录；旧任务直接续跑原目录，不迁移或重置起点。
