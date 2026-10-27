> 本页随独立安装版发布；`<PROJECT>` 是定位后的 Unity 项目，`<REPO>` 是仓库根。`$skillRoot` 是本技能安装目录，工具必须从此目录调用。

# 当前 Editor 验证与结果汇总

两个合并入口默认复用原目录及已打开的 Unity MCP。实际执行使用个人安装目录中的 `scripts/handoff.py`；[handoff.py 维护源码](../scripts/handoff.py) 仅供维护和打包，Python 3.11+ 标准库。脚本不执行场景迁移、Git 合并/提交/推送，不自动备份或恢复用户数据，不控制 Unity 生命周期。

## 路由与能力

固定的测试调度顺序、恢复清单及双根交付清单见 [执行辅助工具与续跑](execution-tools.md)。begin/finish 的输入与会话校验保留；无需为减少轮次改用不完整测试结果或跳过快照。

1. 核对当前 MCP 的项目路径、实例 ID、进程会话身份以及实际分支/输入。停止播放并保存后检查编译、导入、未保存场景；写入和重载按 [合并流程](merge-workflow.md)。不关闭、重启或另开 Unity。
2. 按实际变化及共享依赖确定检查项、理由、完整用例清单和能力需求。只修改第四章专用内容时，前三章仍做非目标场景保护，但不默认重跑全部玩法；修改存档、玩家、背包等共享系统时，补足受影响章节的必要回归。场景未变不能替代共享代码影响分析。先从测试发现接口/版本化清单取得预期完整用例名，不从本轮执行结果反推 expected_tests。参数化测试包括每个具体用例。不以数量下限代替覆盖检查。
3. 需要 foreground_window、cursor_lock 或 camera_render 的检查，在准备会话/短预检时实测对应能力，不能仅凭配置声明 true。cursor_lock 指已证明该环境在正确播放阶段可取得光标锁，不要求 Edit Mode 常驻锁定光标。测试仍须验证实际业务输入门禁、保护帧及清理。
4. 使用 editor-begin 固定输入和票据，再通过同一 MCP 运行检查，保存调度响应及 get_test_job 完整结果，editor-finish 接入并复用 summarize。工具不调用 MCP；Agent 负责真实采集和调度，不手写通过结果。标准接入负责校验结构与关联，不能证明人为伪造的 JSON 来源真实性。
5. 条件不满足时先诊断，不用相同错误环境重试。MCP 不可用或原始结果格式不支持时明确未验证及原因，不降级为关闭 Editor/批处理。编译和人工检查可另列证据，不冒充 MCP 测试通过。

旧 workspace/preflight/run 仅支持历史独立批处理，不是当前工程前置步骤；run 默认拒绝启动。需要维护旧工具时才读 [历史批处理参考](legacy-batch.md)。两个合并操作禁止使用其 --allow-editor-launch 路线。

## 最小验证计划

保留已有计划的 source_commit、target_base_commit（完整 SHA）、source_snapshot、scope_authorization、target_platform、task_id、protection_record。新增 purpose=final/diagnostic；原批处理计划未声明时按历史格式处理。每项当前 Editor 检查如下：

```json
{
  "id": "chapter04_scene",
  "mode": "PlayMode",
  "backend": "editor_mcp",
  "reason": "填写实际改动和受影响功能，不能固定复制第四章示例",
  "test_filter": "填写实际测试类选择器",
  "expected_tests": ["填写运行前发现的完整用例名"],
  "requirements": {"cursor_lock": true, "camera_render": true, "foreground_window": true},
  "min_tests": 1
}
```

来源 snapshot 在切分支/应用合并前生成；目标 snapshot 由 editor-begin 在导入编译和恢复准备完成后生成。同目录不代表同版本。输入覆盖 Assets、Packages、ProjectSettings 及工具身份，保留现有字节变化检测，不排除整个 ProjectSettings 来掩盖副作用。快照的 dirty_files 仅扫描这些项目输入（dirty_scope=project_inputs），避免反复哈希交付报告；保存/提交前仍检查完整 Git 状态，报告和其他交付文件由独立 manifest 校验。

以下命令属于合并前的输入固定阶段，成功后核对快照身份，再通过[写入前检查点](merge-workflow.md#1-保存提交并固定输入)。续跑复用同一份有效来源快照，不在测试开始时重新覆盖它。

```powershell
python -B -X utf8 $tool snapshot --project $project --scope $scope --output "$evidence/source-snapshot.json"
```

测试前实际备份/隔离用户存档和章节偏好，再提供 protection_record：task_id、status=prepared、method=backup/isolated、details。该 JSON 不是自动备份。测试副本的存档限制和章节偏好写入须实际检查。

## 会话观察与接入命令

通过 MCP 的项目/编辑器资源及必要的只读 execute_code 实测，按下列字段规范化会话观察。session_id 应含 Editor 进程 ID 与进程启动时间等稳定身份，不能只填项目名；instance_id 为 MCP 当前实例。保留原始观察响应和字段映射依据在本机 Git 管理目录，规范化文件同样放在那里，避免提交机器绝对路径。便携票据记录观察哈希；跨机器原始证据归档须脱敏。

```json
{
  "project_path": "本次实际 Unity 项目绝对路径",
  "session_id": "实测进程及启动时间身份",
  "instance_id": "实测 MCP 实例身份",
  "observed_at": "实测时间，ISO 8601，带时区",
  "playing": false,
  "compiling": false,
  "updating": false,
  "dirty_scenes": false,
  "capabilities": {"cursor_lock": true, "camera_render": true, "foreground_window": true}
}
```

规范化时未知值保留未知，不能填 false/true 绕过预检。观察须在最近 120 秒内；begin 后实际调度前再次确认仍就绪，不在同一工程并发编辑、执行合并或跑第二组测试。MCP 重新连接到不同实例或 Editor 会话变化，旧票据失效。

```powershell
# 以下为合并后验证阶段；source-snapshot.json 已在合并前固定。
python -B -X utf8 $tool editor-begin --project $project --evidence $evidence --plan "$evidence/validation-plan.json" --check $checkId --session $sessionBefore
# 若返回 reused，不再次调度；否则通过当前 MCP run_tests 调度同一计划选择器。
# 保存原始调度响应 data（含 job_id）与 get_test_job 完整 data（含 results，不截断或分页漏项）。
# 测试完成并退出播放后重新实测 sessionAfter；不要关闭 Editor。
python -B -X utf8 $tool editor-finish --project $project --evidence $evidence --run-id $runId --session $sessionAfter --dispatch $dispatchJson --result $jobJson
```

适配器支持现有 Coplay 作业结构：job_id、status、mode、started_unix_ms、finished_unix_ms、result.summary 及 result.results（fullName/state/durationSeconds）。要求作业开始晚于 begin、与调度 ID 相同、结果模式匹配、实际用例集合与预期完全一致、总数和明细一致；零项、失败、跳过、缺失和旧结果不能报通过。`Failed:Error` 等带标签的 Failed 状态计入失败数，原始标签保留，不再因这一已知格式取消正常失败记录；计数不一致仍拒绝。前后快照或 HEAD/分支变化会使结果失效。保留同会话、作业及原始结果哈希，不用同名测试结果冒充。

中断或不兼容原始结果先保留原始响应和错误，再使用 editor-cancel --project ... --evidence ... --run-id ... --reason ... 记录 incomplete。cancel 不停止测试或 Editor；重开检查前须通过 MCP 确认旧作业已结束且恢复就绪。未收口票据阻止本证据目录的新检查。同一工程所有任务串行运行；工具短时 OS 锁不是跨 MCP 调用的长期 Editor 租约。

## 诊断、复用与汇总

final 计划固定本轮必要覆盖。失败先保留原始结果，使用独立 purpose=diagnostic 计划记录具体失败、新证据和定向检查，先看完整门禁再修改测试。diagnostic 不能作为最终 summarize 输入。相同检查/计划/输入已有失败时 begin 拒绝无变化重试。若仅修复了环境，可通过 --recovery-evidence 指向含 task_id、failed_run_id、details、evidence 的实际修复记录；同一修复仍失败后不能重复使用。相同计划/实际输入/目标提交已有有效通过结果时 begin 返回 reused；后来的失败不能被早先通过掩盖。结果复用不代表场景迁移完整性或人工通过。

当前工具仍保守核验整组输入；不把“只改一个文件”直接视为其他测试结果仍有效。原始测试完成但输入出现变化时保留 inputs_changed；只有能够证明副作用归属并精确恢复受测输入才可采用现有恢复协议，不自动恢复用户文件。分支或 HEAD 已变化不能通过空 restored_files 绕过。未解释的变化须重新验证。

### 失败后的定向诊断

首次运行仍按影响选择必要覆盖，不为每次合并固定增加一轮预检。已有明确受影响的测试假设或历史失败时，才先做对应短检查。最终覆盖不能因为耗时、失败或定向检查通过而缩减。

1. 一次收齐本轮所有失败的完整用例名、断言、堆栈及相关日志，按可能的共同原因归组。先检查相关代码、场景参数、输入门禁和测试准备/清理，避免只修第一个报错就重跑全套。
2. 用 diagnostic 计划运行能区分原因的最小检查。若单例通过而整组失败，检查顺序依赖、静态状态、物理同步和帧时序，定向运行必要的前置用例与失败组；单例通过不是原因已解决的证据。不要反复跑全套碰运气，也不默认增加重试次数或任意等待秒数。
3. 修复必须对应观察到的原因。资源尺寸或配置确已按需求改变时，先独立验证新配置，再更新派生的行程/速度等期望；不能直接把实际输出当期望。测试移动 Collider 后立即查询物理世界且自动同步关闭时，核对物理世界与 Transform 是否一致，必要时在测试准备阶段显式同步；不能把所有失败统一归为物理问题。保留业务门禁、边界、否定断言和清理检查，不以跳过用例、放宽断言或修改正常游戏逻辑掩盖测试问题。
4. 所有失败组都有原因与修复证据、对应定向检查通过后，再运行 final 计划的必要覆盖。将“失败组 → 原因 → 实际改动或环境恢复 → 定向运行 ID”简记在已有诊断记录中，不另建重复报告体系。若最终检查再次失败，保留结果并回到新的证据分析；需要整组才能复现时说明理由，不能用更名计划或虚构恢复证据绕过无变化重试限制。

定向通过只帮助决定何时运行最终检查；最终结果仍遵守完整预期用例集合、同会话、同输入及恢复协议，不拼接不同输入下的通过结果。

### 测试设置恢复与汇总顺序

测试前随会话观察记录工具可能调整的 Editor 设置内存值，至少包含 `EditorSettings.enterPlayModeOptionsEnabled` 和 `enterPlayModeOptions`；磁盘原值由已生成的输入快照和必要原文件字节固定，不增加一次全项目扫描。原值不得写死为 false 或其他默认值。

测试结束、退出播放后，先保留原始结果并按现有 editor-finish 流程收口；若记录为 inputs_changed，保留该状态及前后快照，再核对具体差异。对确认由本轮工具造成的设置变化，恢复记录的内存值，并读取对应磁盘字段和文件身份确认实际落盘；API 返回成功不代表磁盘已恢复。需要精确恢复磁盘时，仅在当前差异仍与已归因的测试副作用一致、没有用户新编辑的前提下恢复相关字段或原字节，不能整文件覆盖用户并行修改，也不为落盘调用无差别 SaveAssets。

只有内存与磁盘均核验完成、用户数据检查完成，才能写 cleanup.json 的 complete 并调用 summarize。复用 editor-finish 的前后快照填写 restored_files 的 run_id、before_identity、after_test_identity 和 attribution；最终 summarize 仍须确认受测输入确已恢复，不跳过或伪造哈希核验。遇到未知差异或未落盘设置时先处理，不提前生成失败汇总再反复重跑；已有有效测试不因已证明且精确恢复的工具副作用重跑。这里调整收尾顺序，不扩大日常测试用例范围。

恢复本轮副作用后提供 cleanup.json（task_id、status=complete、user_data_verified=true、details），以及 delivery-files.json（项目相对 files/deleted 列表）。同一份结果生成报告和哈希清单，不再临时编写本轮校验脚本。集中收尾的顺序与文件冻结边界见 [最终收尾](execution-tools.md#最终收尾)。

```powershell
python -B -X utf8 $tool summarize --require-complete --project $project --evidence $evidence --plan "$evidence/validation-plan.json" --cleanup-record "$evidence/cleanup.json" --files "$evidence/delivery-files.json" --output "$evidence/summary"
python -B -X utf8 $tool verify --project $project --manifest "$evidence/summary/result-file-hashes.json"
```

raw MCP 结果直接存入 validation/<run_id>，多个报告引用同份证据。原始响应含敏感信息时保留本机原件并另外脱敏归档，不能修改已哈希原件。运行报告自动区分 passed/failed/inputs_changed/interrupted，完成报告另外说明编译、静态完整性与人工待验。辅助脚本本身不提交或推送；执行合并的 Agent 在验证完成后按合并流程创建本地结果提交并自动推送目标分支。

## 全过程计时

使用个人安装目录中的 [handoff_timing.py](../scripts/handoff_timing.py)，记录在通过 git rev-parse --absolute-git-dir 取得的本项目 Git 管理目录下 handoff-timings/<task_id>/timing/（旧任务沿用原目录），不写受测输入。实际发生后记录 started、prepared、merged、validation_complete、cleanup_complete、committed、push_verified、finished；没有推送省略 push_verified，原目录不记录旧隔离区 released。续跑沿用任务，不猜测回填时间。

命令形式：`python -B -X utf8 $timer --directory $timingDir --task-id $taskId --event started`；完成时改为 finished，省略 --event 获取汇总。begin/finish 记录验证墙钟耗时、MCP 作业起止及用例 duration。阶段间隔含导入、调度、等待、分析或报告时明确口径，不能当成纯用例时间。需要细分的导入/编译时间取真实日志，不虚构精度。没有 finished 不声称端到端已完成。

## 工具验证

维护源码时运行：`python -B -X utf8 -m unittest discover -s "$skillRoot/scripts/tests" -v`

测试只使用临时仓库和模拟进程/会话，不操作用户 Unity，也不代表真实工程迁移或性能已经验收。实际提速需在相同来源、目标及必要覆盖下计时，不承诺固定分钟数。

已知真实场景夹具与模拟单例夹具互相污染时，在计划阶段按独立 PlayMode 生命周期分组；保存分组前后完整用例集合等价证据，不减少覆盖，不把未知失败预先归因于污染。无已知隔离需要时不增加测试组和快照轮数。
