> 本页随独立安装版发布；`<PROJECT>` 是定位后的 Unity 项目，`<REPO>` 是仓库根。`$skillRoot` 是本技能安装目录，工具必须从此目录调用。

# 仅生成清单／只读验收流程

本参考文件的“不自动修复、提交或创建分支”只适用于这两个只读入口；执行合并按 merge-workflow.md 的授权范围办理。

用中文执行，先读 [项目指南](ProjectGuide.md)。团队主程将开发场景的机关整体复制或替换到基础测试场景；按机关／功能组织交付和验收，既给人简短操作清单，也给 AI 完整、可复现的核验依据。无需历史会话。不要在创建本技能时执行真实交付或验收。

## 入口和范围

- “准备交给主程合并，整理当前分支的场景交付清单”：生成交付记录。
- “检查这次场景交付在 develop_base 中有没有遗漏”：用既有交付记录验收远程主分支。
- 同义表达也适用。生成清单不意味着提交、推送、通知主程、修复主分支或创建下一开发分支的授权。用户随后要求提交清单时，只暂存并提交本次文档，检查暂存区避免夹带已有改动；未要求推送时不推送。
- 开发分支通常为 develop_base_zhangtaoXX。读取真实分支和作者后缀，不固定编号；作者标识优先取分支后缀，Git user.name 另存，不假设各电脑 Git 身份完全一致。
- 按 [场景配对规则](scene-sync.md) 递归检查 Assets/GMScenes/Test 及章节子目录中实际存在的全部编号，自动配对 TestScene_all_NNN_<实际作者>.unity 与 TestScene_all_NNN.unity（含 004 及后续编号）。逐章记录有改动、无交付差异、缺少开发场景等覆盖状态；检查直接修改基础场景的情况。不能因缺少个人场景就断言该章无改动。
- 不把第二章机关要求复制到三个章节；跨章公共改动才扩展到相关章节。不以只复制了开发场景为新增整个功能的证据。

## 路径和版本

定位含 Assets 和 ProjectSettings 的 Unity 项目目录，并用 git rev-parse 定位仓库根；两者可能不同。所有持久路径使用相对路径、正斜线，并注明相对于项目还是仓库。依据中保存 project_path（项目相对于仓库根的路径）。不要写入机器盘符、用户名目录、远程 URL 中的凭据或依赖特定系统的命令。

交付目录位于项目 `Docs/SceneHandoffs/YYYY-MM-DD_HHmmss_<作者>_<分支名>/`。时间采用本机本地时间，元数据记录 ISO 8601 时区偏移。目录段替换 Windows/macOS 不合法字符并处理冲突；文件内保留完整原始分支名。每次重新交付创建新目录，不覆盖旧记录。

生成 合并清单.md 和 核验依据.json；验收时新增 合并后验收.md 及 验收依据.json。重复验收保留既有结果，给新验收文件加时间后缀。

需要批处理运行验证时，复用 [验证工具](automation-tools.md) 的来源/目标快照、运行记录与结果汇总，并在本轮核验依据中用相对路径和哈希引用；同一组结果不在多份文档手工重算。仅生成清单不因此启动 Unity，既有 schema_version: 1 和原始证据保持不变。工具汇总不替代下文逐功能静态验收和人工确认。

## 生成交付记录

1. 检查 Git 状态、真实分支、远程和提交历史。固定完整交付功能提交号 source_commit、基准提交号 baseline_commit 和基础场景比较版本 comparison_commit，说明各自的选取理由。优先以分支起点和历史证据识别本次开发范围；merge-base 只是线索，主分支已合入此分支或开发期间反复同步时不能盲目用当前 merge-base 当开发起点。无法确定的范围标记待确认。
2. 检查未提交的场景、代码、资源与 Unity 未保存状态。相关未提交内容可以形成草稿，但必须记录 draft 状态、脏文件和无法绑定提交的部分，不冒充固定提交的正式交付。Unity 未连接时明确无法确认编辑器未保存改动。提交文档前复查功能版本，发现新增相关改动先更新依据或标明草稿；不擅自提交业务文件。文档记录已有功能提交号，文档自身提交号无需自引用。
3. 将同版本开发场景与基础场景配对比较，再结合基准以来的代码、Prefab、资源和场景变动，识别本次交付、历史差异及临时测试内容。记录排除项及理由；仅对影响交付范围的歧义集中询问用户，继续其他可确定项。
4. 按功能建立稳定条目 ID。新增／整体替换机关在简单版只写根路径；根外引用、目标门、初始化器、出生点、删除对象、共享配置等需要额外操作的内容单列并关联功能。公共变更列出所有已知受影响功能。不猜功能名称或因果，读代码和资源给出依据。
5. 详细版保存整个交付子树的组件、关键及其他序列化配置、内部／外部引用、相关资源与 .meta GUID、Prefab 来源和 override、SaveId 等可复查证据。可将大量结构化快照放在同目录证据文件中，用相对路径和哈希引用，避免 JSON 过大。固定提交中的相关源文件必须可找回；缺失提交、LFS 实体或解析失败明确记录，不宣称完整。
6. 验证 JSON 可解析、条目 ID 能互相对应、证据路径存在、提交可解析、全部发现编号的覆盖状态齐全，检查 Git diff 仅含本任务文档。汇报目录、功能范围和待确认项，不自动提交。

简单版每项包括：ID、章节、机关／功能、变动类型（新增／修改／删除）、准确对象路径、具体合并操作、遗漏影响。新增机关内部细节不逐组件罗列。整体复制会覆盖其他同事改动时提示具体冲突范围。

## 合并后验收

1. 从当前会话指向、作者／分支、交付记录状态和提交关系选择本次交付。不能仅按文件夹时间选全仓库最新记录。多个合理候选无法区分时让用户选择，不猜；草稿只能作局部核验，不能出正式全部通过结论。
2. 检查工作区后 fetch 配置的主分支远程，固定远程 develop_base 完整提交号 target_commit。fetch 失败时明确无法验收最新远程版本；不拿旧本地分支冒充。无需用户切换分支或 pull。
3. 通过 git show/ls-tree 等只读读取固定目标版本，保留当前分支、未提交内容及已打开 Unity 场景，不创建 worktree 或项目副本。当前工程未处于目标输入时仅做静态验收，运行验证记为未执行；不得将当前开发工程的 Console 当作目标版本结果，也不为只读验收擅自切分支。
4. 对照条目检查存在性、删除落实、组件与配置、输入输出引用、Prefab override、依赖资源／代码和重复 SaveId／旧触发器。检查跨根引用和其他对象指向被替换对象的入向引用。不只检查对象名字。
5. 对象身份综合层级、组件类型、脚本 GUID、稳定业务标识和结构匹配；重复名称要定位到唯一对象。跨场景复制的 fileID 可改变，内部引用须映射到实际目标再比较，不能直接以 YAML 文本、fileID 或哈希不等断言功能遗漏。重命名、重挂层级及主程的等效实现需要语义核实；冲突或证据不足列待确认，不能强制回滚主程改动。
6. 输出每项结果：已静态对齐、确定遗漏／不一致、存在冲突需确认、证据不足；运行验证另设状态，静态通过不等于功能正常。每个问题必须给出功能、场景、准确层级、组件／字段、交付期望值、主分支实际值、证据位置、影响和具体补齐建议。区分已运行复现的故障与根据代码配置推断的风险，解释因果，不只写“部分合入”。
7. 按改动选择必要 Unity 验证，遵循项目要求：机关完成、特效结束、输入与镜头释放、存档恢复等。Unity MCP 可用时使用对应技能并确认连接的是验收项目；工具不可用则写未验证项。运行前保护本地存档，避免验收污染用户进度。没有执行就不能声称通过。
8. 将结果写回原交付目录，固定 source_commit、target_commit、交付记录哈希和验收时间，汇总受影响功能。原清单和核验依据保持不变。发现遗漏不自动修复、提交或创建新分支。

## 详细记录的最小数据约定

核验依据.json 使用 schema_version: 1，至少包含：

- handoff_id、created_at、author、git_author、branch、status（draft 或 ready）、project_path、remote_name。
- source_commit、baseline_commit、comparison_commit、baseline_reason、dirty_files、editor_saved_state。
- scenes：所有发现编号的 source_scene、target_scene、coverage、reason。
- items：id、feature、related_features、chapter、change_type、source_scene、target_scene、object_path、component、operation、expected_behavior、omission_impact、impact_basis、verification_steps。
- 每项 evidence：各证据的 commit、仓库相对 file、对象定位、字段 before／expected、规范化引用目标；子树快照或源文件引用覆盖完整交付单元，明确未覆盖内容。dependencies、external_references、incoming_references、save_ids 可放条目下或引用证据文件。
- exclusions、uncertainties、evidence_files（相对路径、SHA-256）、coverage_limits。未知值使用 null 并说明原因，不填臆造值。

验收依据.json 包含 schema_version、handoff_id、handoff_evidence_hash、source_commit、target_commit、checked_at、results。每个 result 关联原条目 id，保存 status、expected、actual、location、evidence、affected_features、impact、impact_certainty、suggested_fix、runtime_verification 和 limitations。简单报告与详细结果一致，不把运行未验证隐藏在“全部通过”总结中。
