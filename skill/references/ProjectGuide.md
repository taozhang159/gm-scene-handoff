> 本页随独立安装版发布；`<PROJECT>` 是定位后的 Unity 项目，`<REPO>` 是仓库根。`$skillRoot` 是本技能安装目录，工具必须从此目录调用。

# GMGame 项目指南

本文件维护 Codex、Claude Code 等 Agent 共用的业务约束、项目基线和当前资源布局。文件更新流程、目录选择及验收要求统一维护在 [项目文件更新标准](ProjectUpdates.md)，由 `gm-project-update` skill 加载。全仓库统一使用根目录的 AGENTS.md（目标项目内 `<REPO>/AGENTS.md`） 和 CLAUDE.md（目标项目内 `<REPO>/CLAUDE.md`），两者只保留入口；具体字段、参数、资源引用以当前代码和序列化资源为准。

## 文件更新与文档入口

- 新增、修改、移动、重命名、替换、删除文件及检查目录归属时，使用 gm-project-update skill（目标项目内 `<PROJECT>/.agents/skills/gm-project-update/SKILL.md`）。标准中的类型目录、章节归属、引用同步和验证要求适用于 Unity 项目及仓库 Sources/（目标项目内 `<REPO>/Sources`）。
- 场景前缀及其文件、专属资源的 Chapter 编号映射统一遵守 [章节归属规则](ProjectUpdates.md#2-章节归属)；场景文件的两层目录约定见[固定位置与既有边界](ProjectUpdates.md#固定位置与既有边界)。下文既有资源清单记录当前路径，实际新增与归类迁移按标准中的文件类型规则执行。
- 文档正文、参考图和交付证据集中在 Docs，分类与入口见 文档总目录（目标项目内 `<PROJECT>/Docs/README.md`）。更新流程只在标准正文维护，避免多个入口重复保存相同规则。
- 当前 Resources 归属和加载地址见 Resources 目录说明（目标项目内 `<PROJECT>/Docs/Project/ResourcesLayout.md`）；GMPrefabs、GMMaterials、GMShaders 的当前布局和历史迁移映射见下文。

- 第四章照骨室模型或动画制作：先读续作摘要（目标项目内 `<PROJECT>/Docs/Puzzles/BoneMirrorRoom/Resume.md`）与制作流程（目标项目内 `<PROJECT>/Docs/Puzzles/BoneMirrorRoom/ProductionWorkflow.md`），复用已确认的参考图、Tripo、Blender MCP、Unity MCP 流程及资产，不要求用户在新会话重复说明。

## 工作原则与项目基线

- 修改前阅读相关代码、场景和 Prefab；只处理任务相关内容，不清理、重置或覆盖用户已有改动及 Unity 生成文件，不无条件覆盖 Inspector 配置。
- 文件使用 UTF-8；代码注释使用中文并沿用所在文件风格。
- 支持第一／第三人称的解谜游戏，新设置默认第一人称，C 键或设置菜单切换并记住选择，第一章“幽冢启门”。Unity 2022.3.62f2c1，Built-in Render Pipeline，Post-Processing 3.5.4；未安装 URP/HDRP，材质默认使用 Standard。
- 新建及维护 `Assets/` 下的 C# 文件必须遵守 [CSharp 文件头与命名空间规范](ProjectUpdates.md#csharp-文件头与命名空间)：使用 `GM` 文件名前缀、统一文件头和 `NetherTomb` 命名空间。完整模板、日期填写、程序集配置及引用同步要求统一在该规范维护。
- 业务代码在 `Assets/GMScripts/`，正式场景在 `Assets/GMScenes/`。没有命令行 Build 配置，编译、运行、构建通过 Unity Editor 完成；已安装 `com.coplaydev.unity-mcp`。

## 编辑器工具与自动化测试

- 编辑器工具位于 `Assets/Editor/`，自动化测试位于 `Assets/Tests/EditMode/` 和 `Assets/Tests/PlayMode/`。新增测试按文件更新标准归类，先确认已有测试程序集边界。
- 原 `Assets/GMEditor/` 中的两个测试脚本已归入第三章，原目录已删除：

| 当前文件 | 测试用途 |
| --- | --- |
| Chapter_03/GoldenBell/GMGoldenBellMusicPuzzleTests.cs（目标项目内 `<PROJECT>/Assets/Tests/EditMode/Chapter_03/GoldenBell/GMGoldenBellMusicPuzzleTests.cs`） | 五铃音频数据、Prefab、路由与旧存档兼容。 |
| Chapter_03/Save/GMPuzzleSaveHardeningTests.cs（目标项目内 `<PROJECT>/Assets/Tests/EditMode/Chapter_03/Save/GMPuzzleSaveHardeningTests.cs`） | 白虎星盘完成态、朱雀羽免疫与使用冷却、机关读档后的状态裁决。 |

- 上述两个测试脚本由 GMGame.Chapter03.EditModeTests.asmdef（目标项目内 `<PROJECT>/Assets/Tests/EditMode/Chapter_03/GMGame.Chapter03.EditModeTests.asmdef`） 管理，程序集名称为 `GMGame.Chapter03.EditModeTests`。限定 `Editor` 平台并保留 `TestAssemblies` 配置；不并入上层的星移机关测试程序集。其他第三章模块的测试仍遵守其已有专用程序集边界。
- 测试类命名空间统一为 `NetherTomb`，`.meta` GUID 保持不变。按程序集运行时使用 `GMGame.Chapter03.EditModeTests`；按类运行使用 `NetherTomb.GMGoldenBellMusicPuzzleTests` 或 `NetherTomb.GMPuzzleSaveHardeningTests`。测试通过反射访问 `Assembly-CSharp` 中的运行时代码，保留该边界。

## 场景与全局对象

- `ProjectSettings/EditorBuildSettings.asset`、`GMGlobalSceneManager.cs` 中的 `NetherTomb.SceneEnum` 和加载 switch 必须同步。索引为：0 登录，1–3 章节 001–003，4 过场 001，5–9 游戏 001–005；Test 场景不进入构建。
- 业务跳转使用 `GMGlobalSceneManager.GotoSceneWithEnum`；GMSaveManager 内部跨场景读档例外。跳转顺序：`QuickSave → GMPlayerTransientStateCleanup.Reset → GMInventoryManager.ClearAllItems → 淡出加载`。
- 登录和游戏 001–005 的 `GMGlobalManager.globalPrefabs` 内容及顺序一致：Player、InventoryManager、GameTip、HintPanel、CrosshairCanvas、GlobalFadeCanvas、GameAudioManager。新增全局 Prefab 放入 `Assets/GMPrefabs/Common/Global/` 并同步正式场景。
- GMGlobalManager 保留首个实例并跨场景存活；GMSaveManager、GMSettingsMenu 在 BeforeSceneLoad 自动创建，避免重复创建。执行顺序：GMGlobalManager -20、GMSettingsMenu -15、GMPlayerController -10。
- 各 `GMGameSceneXXXInitializer` 管理出生点和开场流程，读档时跳过新游戏出生点、教程启动及开场提示；完成初始化后调用 `NotifyCurrentChapter` 和 `NotifySceneReady`。新游戏教程由场景显式调用 `StartTutorial`，不在 GMGameTip.Start 自动启动；第一章教程通过 `chapter_01_tutorial` 组件记录进度，在 `OnLoadComplete` 后续接未完成步骤，详见 第一章新手操作引导（目标项目内 `<PROJECT>/Docs/Systems/ChapterOneTutorial.md`）。

## 交互、镜头与公共能力

- 新功能使用 `CombinationItems` 系统：GMPlayerController、GMGrabbable、GMItemPlacementController、GMIItemSlot/GMItemSlot。不要混用旧 GMPlayerInteract、GMItemPickup 等系统；新 `GMItemData` 是普通 class，旧 `Game/Items/GMLegacyItemData.cs` 的 `GMLegacyItemData` 是 ScriptableObject；二者均位于 `NetherTomb`，按实际类型区分。
- 常规拾取、放置、交换走 GMItemPlacementController；槽位通过 Fill/Unfill 和 OnItemPlaced/OnItemRemoved 推进状态。`acceptedItemName` 匹配 `itemName`（空值接受任意，逗号分隔多个）；`itemId` 是存档、校验和本地化的稳定标识，不为翻译直接修改 itemName。
- 世界交互检查 `GMSettingsMenu.BlocksWorldInput`；`GMInventoryManager.IsPreviewMode` 包含背包预览和世界检视，期间阻断移动、视角与世界交互。
- 镜头接管可用 `disableMouseLook`，归还前必须 `SyncPitchFromCamera`；传送和读档恢复使用 `GMPlayerController.RestoreTransform`，同步 CharacterController 和相机姿态。
- 全局 Player 的主相机挂载 `GMPlayerPerspective`，C 键以约 0.5 秒柔和过渡切换第一人称与右肩头肩近景；人物头肩偏左，镜头偏右，腰腿裁出画面。基准后距 0.55 米（再按垂直投影比例补偿构图）、右偏 0.25 米，观察支点相对逻辑眼位降低 0.30 米并沿视角上方偏移 0.05 米；蹲伏前倾时支点向人物前方移动 0.28 米，近距隐藏阈值 0.35 米，并按当前骨骼姿态和近裁剪面保护侧面躯干／肩部／头部；沿墙旧机位被身体包住时优先采用身体外的安全机位，空间不足时仅在渲染期间隐藏人物；基准水平 FOV 55 度并随环境 FOV 调整。操作设置的 60–90 度统一表示水平视野，第一／第三人称渲染时按实际画面比例换算垂直角度，避免宽窗口放大四角；已保存的角度数值保留，配置字段与格式不变。环境设置 → 操作设置提供第一／第三人称并排选项，与 C 键共用所选模式，修改自动保存，重新启用或重启游戏后恢复；暂停菜单内选择仍可平滑过渡，演出接管期间只保存选择并在归还控制后生效。同区提供镜头俯仰幅度与人物可见比例滑块，修改自动保存：两种视角共用上下各 20–60 度的俯仰限幅，默认 40 度；人物比例为 20%–100%，默认 20% 头肩近景，调大以 0.18 秒阻尼逐渐拉远到全身，仅影响第三人称。读档、设置朝向和机关镜头归还控制时使用当前俯仰限幅。位置、FOV 和近裁剪面共用同一条切换曲线，连续切换保留速度并柔和反向，切回第一人称时不残留后距。切换进度先于玩家移动及射线查询推进，每帧只求解一次镜头姿态；机位直接跟随玩家水平位置，第三人称转向在玩家控制器中以 0.065 秒短时缓冲并同步人物与逻辑眼位，第一人称保持直接响应；传送、读档、镜头归还及输入阻断清理待处理转向。第一／第三人称共用独立的地形高度缓冲，取消为固定人物构图而设置的 3 厘米地形滞后限幅，允许人物暂时起伏；取景、避墙和瞄准点都基于稳定眼位，高度／遮挡恢复／目标逆深度分别以 0.16／0.18／0.28 秒阻尼。第一人称蹲起沿用控制器原有插值，鼠标保持直接响应，普通不可交互地面不牵引取景，地上交互物、槽位和线索保留汇聚。Built-in 渲染只应用缓存姿态，结束归还眼位、旋转、FOV 与近裁剪面；交互射线统一通过 `GMPlayerPerspective.GetInteractionRay`／`RaycastNonAlloc`／`Raycast` 读取当帧缓存画面的准星方向，命中点在远近切换、蹲起和地面检测期间持续对齐屏幕中心；射线起点投影到眼位深度，检测长度按眼位半径换算。镜头平滑沿用现有参数；存档和机关镜头仍基于玩家眼位。镜头使用球形扫掠与沿墙滑动；侧墙遮挡实际交互目标时仅阻断交互，不拉扯镜头或锁住移动。传送和临时状态重置同步清除跟随历史；菜单／检视／演出不接受 C 键切换，演出接管后自动让权，结束恢复所选模式。当前人物使用用户提供的 `Character_Locomotion.fbx`，运行模型、3 个 Standard 材质、3 张贴图及外观 Prefab 位于 `GMPrefabs/Common/Props/CharacterLocomotion/`，首次接入的可编辑工程与输入包保留在仓库 `Sources/Common/Player/CharacterLocomotion/`；本轮最新可编辑工程保留在用户原工作目录，未覆盖仓库同名源文件。23 根导出骨骼、24,504 个三角面；Generic Avatar 当前保留站立、行走、快跑五个片段：三个原地片段及行走、快跑两个前进片段。全局 Player 的外观 wrapper 保留原 GUID 与组件身份，当前名为 `PlayerAvatar.prefab`。`GMAnimations/Common/Player/CharacterLocomotion.controller` 按实际位移混合原地 Walk／FastRun，前进 Root Motion 关闭；后退使用反向播放，横移与斜移沿移动方向缓冲转身。模型等比放大 1.858105 倍至 1.82 米，步频按源行走／快跑参考速度 0.4872／2.25 米每秒乘缩放匹配。Run 与 Sprint 动作已删除，两个前进动作保留在 FBX，未新增输入档位。胸部、头颈不再逐级抵消水平转角，骨盆带动整个人物同步转向；衣物接触补面已匹配周围黑色布料，FBX 源材质到三种 Standard 材质的映射已补齐。待机、停止收步和蹲伏沿用关节接地求解；蹲伏骨盆下沉 0.59 米，不缩小人物。当前 Generic 手掌按 Hand.L／Hand.R 识别，最终姿态统一执行整段袖子避让，覆盖蹲下、起身及走跑换向。新走跑不叠加旧格蕾丝／里昂修姿；头颈观察、鞋底探地与镜头避让保留。普通／加速／蹲行／蹲行加速速度仍为 1.45／3.2／0.75／1.1 米每秒，碰撞体、输入、存档和镜头设置保持。旧 OutdoorSurvivor 运行模型包、旧 Humanoid Avatar、Starter Assets 运行动画及旧 PlayerLocomotion 控制器已删除，可恢复原件及清单见源工程 History；旧制作文档与源工程标为历史。接入验证及楼梯动作限制见本次人物替换（目标项目内 `<PROJECT>/Docs/Art/PlayerPerspective/CharacterLocomotion/README.md`）。

- 全屏演出使用 `AcquireExternalInputLock(owner)` / `ReleaseExternalInputLock(owner)` 具名锁，保证结束、异常、禁用和中断时释放；不要用单个 bool 覆盖其他持有者。切场景和读档前调用 `GMPlayerTransientStateCleanup.Reset`。
- 燃烧复用 GMBurningEffectController + `Assets/Resources/Common/BurningProfiles/` 下的 GMBurningProfile。
- 界面语言由 GMGameLanguage、GMLanguageManager 统一管理。`Assets/Resources/Common/Config/Localization/` 集中存放本地化配置：`LocalizationTable_EN.asset` / `LocalizationTable_ZH.asset` 供 `GMLocalizationManager.tables` 在 Inspector 中配置；线索、提示、道具说明使用对应 Localization.json。GMHintClue 只存 clueId；缺失翻译回退中文或首条文本。
- 公共音效统一调用 `NetherTomb.GMGameAudioManager` 的具名方法，AudioClip、音量及分组集中配置于全局 GameAudioManager.prefab。连续交互使用 SfxGroup 双音源抢占；除天然多声部效果外不叠加 PlayOneShot，专属放置音效与 PlayItemPlace 互斥。
- 长动作音效绑定动作时长或持有 AudioSource；循环通过 StopLoop 清理，结束、禁用、异常均需停止。初始化和恢复不播放玩家操作音效。
- 高频射线保留 RaycastNonAlloc、静态缓冲区和无分配排序，避免 Update 分配。GMPlayerController 线索凝视的引用身份比较保留 ReferenceEquals，不能改成 Unity `==`。
- 运行时 AddComponent ParticleSystem 后先 `Stop(true, StopEmittingAndClear)`，再配置 duration/lifetime，最后 Play。

- 水纹机关使用 `NetherTomb.GMWaterFlowController`（`CombinationItems/WaterPuzzle/`）；样条水流效果使用 `NetherTomb.GMSplineWaterFlowController`（`CombinationItems/WaterFlow/`），二者各自保留原有 GUID 和序列化数据。

## 存档与谜题恢复

核心实现位于 `Assets/GMScripts/Save/`：GMSaveManager、GMSaveableObject、GMISaveable、GMSaveDataModel、GMChapterPrefs。修改前先读对应实现，保留当前存档的恢复时序。

- 共 10 槽：0 自动且禁止手动覆盖，1–9 手动。当前只读写 v3（含 totalPlaySeconds），必须包含 player、inventory；存档在 `Application.persistentDataPath/GMGame/Saves/`，不迁移或回退读取旧 GMGame 根目录，不接受其他根格式版本。
- 写盘采用同目录 .tmp 回读校验后替换，旧版保留 .bak，主档损坏回退备份。任一 CaptureState 异常或核心状态缺失必须取消整次保存，不能覆盖旧档。
- 只允许正式游戏场景（索引 5–9）及 `TestScene_all_*` 保存；登录、章节、过场、普通测试场景不得覆盖存档。读档、Loading、预览及不稳定镜头接管期间拒绝普通手动保存。
- 谜题在动画和校验结束的稳定终态 QuickSave，连续操作防抖，恢复或演出期间不落盘。确需近景终态保存时使用 `QuickSave(allowTransientCamera: true)` 捕获演出前稳定姿态；退出应用也仅在允许保存的游戏场景使用此方式。
- 新谜题优先继承 GMSaveableObject，配置全局唯一 SaveId；保留历史 SaveId。CaptureState 仅返回本组件权威 JSON，不直接写盘；RestoreState 必须处理空 JSON（旧档或缺少记录）。新道具通常用 GMGrabbable，白名单自动 SaveId 由 GMCustomGrabbableSetup 管理。
- 谜题主控拥有权威状态；恢复前停止旧协程、临时音源、镜头接管，清理旧槽内副本及运行时生成物，再静默重建门、奖励、灯光和槽位。临时槽内副本通常不设 SaveId，由谜题主控恢复。
- 恢复不得重播演出、音效、提示或操作动画；已完成档回退未完成档必须解除锁定并恢复交互。多组件控制同一扇门时，在 OnLoadComplete 后由权威完成态裁决。
- 恢复需等待组件初始化注册、补恢复迟注册对象、等待协程及帧尾 Destroy 收口，再整理背包、清除 IsRestoringFromSave 并触发 OnLoadComplete；单组件异常不阻断其他组件。不要省略这些等待阶段。

## 菜单与章节

- GMSettingsMenu 主菜单顺序：继续游戏、存档管理、章节选择、环境设置、制作人员、退出游戏。Loading 使用独立且高于菜单的 Canvas，关闭菜单后仍可显示；读档失败立即关闭 Loading 并提示，空槽禁止读档。
- 环境设置由 GMCommonSettingsPanel 构建；语言切换需确认并经 GMLanguageManager 刷新。制作人员使用 GMCreditsCatalog。设置只读写 `GMGame/Settings/settings.json`，缺失或无效时创建默认值，不迁移旧路径文件或旧 PlayerPrefs 语言；设置当前写入 v8 格式；已有 v6 偏好读取时保留原选项并补齐镜头俯仰幅度 40°、人物可见比例 20% 的默认值，v7 及更早版本补齐第一人称默认视角，之后菜单或 C 键选择均持久保存。章节偏好只读取当前 v2 分层格式，由 `GMGame/Preferences/chapter_prefs.json` 管理，区分全局和章节私有偏好，不迁移旧路径或扁平数据。
- 章节选择使用 `GMChapterTriangleSelector` / `BuildChapterTriangle`，不扩展遗留分页方案。固定三卡，扩章前重构映射和排序；暂停时动画使用 unscaledDeltaTime。
- 当前章节优先采用初始化器通知，缺失时回退 GMChapterPrefs.LastChapterScene；游戏场景到卡片索引映射：001→0、002→1、003/004/005→2。这是当前运行时 UI 的卡片映射；文件与资源的章节归属由上述场景前缀规则确定，实际目录遵守对应文件类型的规则。

## 特殊玩法风险

- 轮回门：修改前读 GMLunHuiMenTrigger、GMComaWakeEffect、GMDoorRiseTrigger。闭眼全黑后传送，保留 Camera 渲染，禁止关闭整个 Player；移动前禁用 CharacterController，完成后恢复，坐标写入后触发 OnPlayerTeleported，再醒来。GMDoorRiseTrigger 依赖此事件复位而非 OnTriggerExit，SaveId 保留 `lunHuiDoorRise`；中断时恢复组件 enabled 状态、相机层级效果和输入锁。
- 白虎视线：实现位于 `CombinationItems/Puzzle/GMTigerVision*.cs`。优先骨骼扫描，判定和视觉共用扇形与遮挡距离；遮挡考虑 mask 内非 Trigger 实体并保留地面过滤，体积采样不得超过遮挡距离。无敌不失败，恢复走 RestoreTransform，复活点由 GMTigerVisionRespawnRouter 管理。
- 白虎视觉优先调整 `Assets/Resources/Chapter_03/TigerVisionVisualProfile.asset`，保留蓝/青蓝连续体积光雾和弱地面扫痕；不添加大面积离散斑点或不受遮挡的 Cone 粒子、Billboard 雾片、旧 LineRenderer 光线，不批量覆盖场景实例字段。

## Debug 与模型资源

- 构建配置在 Unity `Tools → Build Config`，DEBUG_BUILD / RELEASE_BUILD 互斥，未显式选 Debug 按 Release。快捷键和答案日志必须受 `#if DEBUG_BUILD` 控制，不能用 UNITY_EDITOR 替代。
- Debug 模式下，Player 的 `GMPlayerController → Debug 交互射线 → Show Interaction Ray` 默认开启；Scene／Game 视图开启 Gizmos 后显示与拾取、放置及 E 键共用的准星射线，长度按逻辑眼位的实际检测半径限制。绿线与十字表示首个碰撞点（不代表一定可交互），青线表示剩余范围或未命中，第三人称遮挡阻断交互时为红色；菜单、检视及输入阻断期间隐藏，Release 不编译此显示。
- 业务控制器只暴露 ForceSolve 等无输入语义接口；通用按键集中于 `Assets/GMScripts/Debug/GMPuzzleDebugShortcuts.cs`，专用调试组件整体受 DEBUG_BUILD 控制。答案日志读取运行时权威状态，不重新生成答案。
- Blender PBR 导出沿用 Baihu、Poshidiao 方案；如需减面先处理再导出。项目模型与动画技能随仓库同步，仅在用户明确调用时使用，常规任务遵循项目通用规范；已有 FBX 直接进入加工与接入；跨平台细节见 FBX 道具处理工作流（目标项目内 `<PROJECT>/Docs/Workflows/ModelProcessing/Workflow.md`）。动态加载资源沿用 `Assets/Resources/Chapter_XX/<ModelName>/`（跨章节资源用 `Common/`）；场景或 Prefab 直接引用的模型包按下表放入 `GMPrefabs`。保留 FBX、材质及必要贴图，不留下 manifest、重复 .fbm、临时 Prefab 或抽取的 Materials 目录；既有包中被引用的文件不得按目录名直接删除。
- Standard：BaseColor 开 sRGB；Metallic/Roughness/Normal 关 sRGB，Normal 设 Normal Map。Metallic RGB 存金属度、Alpha 存 `1 - roughness`；正确绑定 _MainTex、_BumpMap、_MetallicGlossMap 并启用对应关键词，_Metallic 和 _GlossMapScale 为 1，_SmoothnessTextureChannel 为 0。
- FBX importer 沿用模型包当前配置，包括既有的 ImportViaMaterialDescription、InPrefab、BasedOnTextureName、RecursiveUp 设置，只有导入任务确需调整时才更改。Material remap 仅对应模型实际导入的源材质标识，不为不存在的模型名或小写别名创建映射；同时核对 Texture2D 映射并保留有效 GUID 绑定。刷新后验证 FBX 和场景实例 sharedMaterials 的对象身份、Shader 和效果；紫色模型先查引用、Shader、remap。

### GMPrefabs 目录

归属遵守场景前缀规则，再结合专属或共享的实际场景依赖判断；跨章节使用的模型、材质及贴图只保留一份。目录移动保留 GUID，场景中的全局 Prefab 列表及 Inspector 参数不因归类而重设。

| 目录 | 内容 |
| --- | --- |
| Chapter_01/（目标项目内 `<PROJECT>/Assets/GMPrefabs/Chapter_01`） | 第一章道具、星图机关、石雕和场景物件；`Environment/` 放水洼 Prefab，`Environment/Scenes/Chapter_01.fbx` 为第一章场景模型。 |
| Chapter_02/（目标项目内 `<PROJECT>/Assets/GMPrefabs/Chapter_02`） | 第二章五行室、暗室、武器室、水坑室、轮回路、陈列室和环境资源；场景模型为 `环境/Scenes/墓室内场景_018.fbx`，宝箱 Prefab 为 `Props/TreasureChest/TreasureChest.prefab`。 |
| Chapter_03/（目标项目内 `<PROJECT>/Assets/GMPrefabs/Chapter_03`） | 第三章白虎室、五铃机关、四神兽石碑和特效；五铃 Prefab 为 `Props/GoldenBell/GoldenBellPuzzle.prefab`，`Environment/Scenes/` 包含 `Chapter_03.fbx` 和 `墓室内场景_Chapter3_01.fbx`。 |
| Common/（目标项目内 `<PROJECT>/Assets/GMPrefabs/Common`） | `Global/` 中的七个全局 Prefab；`Props/` 中共用的宝箱模型、钥匙、磷光石、石槽及贴图；`Environment/灯_四神兽/` 为第二、三章共用灯模型包。 |

旧路径的当前对应关系：顶层 `Global/` → `Common/Global/`，`Environment/` → `Chapter_01/Environment/`，`Scenes/` 中的模型按上表分章；顶层 `GoldenBell/GoldenBellPuzzle.prefab` 和 `Props/TreasureChest.prefab` 分别对应上表第三、二章 Prefab。

原第一章 `StoneCarvingModels/` 中的 `shicao.fbx`、`shicao_Materials/`、`shicao_Textures/` 及 `mima_Textures/` 已迁至 `Common/Props/StoneCarvingModels/`，其余第一章专用模型留在原章节。原第一章 `磷光石/` 对应 `Common/Props/磷光石/`；原第二章 `环境/灯/灯_四神兽/` 对应 `Common/Environment/灯_四神兽/`。

`mima_Textures/` 的底色和法线贴图被多章旧 FBX 共用。相关 ModelImporter 的 `.meta` 通过 `externalObjects` 中的 Texture2D GUID 显式绑定原贴图；保留这些映射，避免目录调整或重新导入后按同名文件误选其他贴图。映射不改变模型、材质子资源的 fileID。

原 `Assets/GMModels/Props/<ModelName>/` 中的包按下表迁入，包名及内部相对路径保持不变；`Assets/GMModels/VFX/XuanwuSpirit/` 对应第三章 `VFX/XuanwuSpirit/`。原目录已移除，历史交付证据中的旧路径仍表示当时的版本，可按此表查找当前文件。

| 当前目录 | 模型包 |
| --- | --- |
| GMPrefabs/Chapter_01/Props/（目标项目内 `<PROJECT>/Assets/GMPrefabs/Chapter_01/Props`） | AncientPaper、BronzeKey、BronzeKeyBox、DryMoss、JadeBowl、JadeDisc、JadePaper、StarPuzzle、StoneGate3、StoneLampBowl、StoneLamppost、Tinderbox、TripleItemSlotOptimized、TripleItemSlotTrigger。 |
| GMPrefabs/Chapter_02/Props/（目标项目内 `<PROJECT>/Assets/GMPrefabs/Chapter_02/Props`） | EarthSpirit、FireSpirit、FiveElementsBallV2、FiveElementsPillarEarth3、FiveElementsPillarEarth3Bottom、MetalSpirit、OrnateCoffinBox、OrnateCoffinLid、RustySword、Sulfur、WaterBowl、WaterGateWrench、WaterGateWrenchBase、WaterSpirit、WoodSpirit。 |
| GMPrefabs/Chapter_03/Props/（目标项目内 `<PROJECT>/Assets/GMPrefabs/Chapter_03/Props`） | BellStriker、DragonBellRack、FourPillarTray、GoldenBell、NewSoulBindingRing、QinglongStoneTablet、SoulBindingChainLink、TigerJadeMirrorButton、TigerNail、TigerStarNumberPlatform、TigerStarPlatform、TigerStarPlatformClean、VermilionBirdStoneTablet、WardJadeTalisman、WhiteTigerStoneTablet、XuanwuStoneTablet。 |
| GMPrefabs/Chapter_03/VFX/（目标项目内 `<PROJECT>/Assets/GMPrefabs/Chapter_03/VFX`） | XuanwuSpirit，供第三章 RewardActivation 下的玄武灵体 Prefab 使用。 |
| GMPrefabs/Common/Props/（目标项目内 `<PROJECT>/Assets/GMPrefabs/Common/Props`） | 原 GMModels 中的 ChestKey、TreasureChest 模型包，由第二、三章共用；第二章专用的 TreasureChest.prefab 按上表存放。 |

- 无场景前缀的专属资源按所属场景确定章节。BellStriker 用于第三章五铃机关；全局 Player 的道具预览引用不改变其章节归属。
- 移动模型包保留 `.meta` 的 GUID、FBX 子资源 fileID 及材质 remap，场景和 Inspector 序列化引用由 Unity 按 GUID 解析到新位置。Editor 路径使用 `Assets/GMPrefabs/...` 形式的项目相对路径。

### GMMaterials 目录

材质按实际场景和 Prefab 用途归类。保留材质、配套 Shader 和网格资源的 GUID、fileID、参数及逻辑名称；同名材质不代表同一资源，不按文件名合并。

| 目录 | 内容 |
| --- | --- |
| Chapter_01/（目标项目内 `<PROJECT>/Assets/GMMaterials/Chapter_01`） | 第一章墙面、纯色、玉纸、星图和石碗材质；`Environment/` 放水洼与水滴材质。 |
| Chapter_02/（目标项目内 `<PROJECT>/Assets/GMMaterials/Chapter_02`） | 第二章各房间、天花板、地面、五行和水流材质；`TextTilePuzzle/` 放轮回路文字机关的激活高亮材质。 |
| Chapter_03/（目标项目内 `<PROJECT>/Assets/GMMaterials/Chapter_03`） | 白虎室及其机关材质；`GoldenBell/` 放五铃槽材质，`TigerStarButton/` 放星移机关材质与配套 Shader，`DigitalDisplayText/` 和 `WhiteTigerAstrolabeText/` 放第三章文字材质。 |
| Common/（目标项目内 `<PROJECT>/Assets/GMMaterials/Common`） | `CombinationItems/SlotDefault.mat` 为全局 Player 使用的槽位材质；`Stone/`、`Ceiling/`、`Hall/`、`Wall/` 为第一、二章共享材质；`Color/M_Color_Black_001.mat` 由第二、三章共用。 |

2026-09-16 整理后共 211 个资源：194 个材质、13 个 Shader、4 个网格资源；第一章 13 个、第二章 70 个、第三章 122 个、公共 6 个。此次移动 28 个资源，资源内容保持不变；移除 5 个无引用的空子目录。

下表路径均相对 `Assets/GMMaterials/`；目录迁移保留内部文件名。历史交付快照中的旧路径和哈希保持原意，当前资源按本表定位。

| 原路径 | 当前路径 |
| --- | --- |
| `Environment/` | `Chapter_01/Environment/` |
| `DigitalDisplayText/` | `Chapter_03/DigitalDisplayText/` |
| `TigerStarButton/` | `Chapter_03/TigerStarButton/` |
| `WhiteTigerAstrolabeText/` | `Chapter_03/WhiteTigerAstrolabeText/` |
| `Chapter_01/CombinationItems/GoldenBellTrayGroove.mat` | `Chapter_03/GoldenBell/GoldenBellTrayGroove.mat` |
| `Chapter_01/CombinationItems/SlotDefault.mat` | `Common/CombinationItems/SlotDefault.mat` |
| `Chapter_01/Stone/` | `Common/Stone/` |
| `Chapter_01/Others/` | `Chapter_01/StoneBowl/` |
| `Chapter_02/Ceiling/M_QBZX_001.mat` | `Common/Ceiling/M_QBZX_001.mat` |
| `Chapter_02/Color/M_Color_Black_001.mat` | `Common/Color/M_Color_Black_001.mat` |
| `Chapter_02/Hall/M_Hall_Down_003.mat` | `Common/Hall/M_Hall_Down_003.mat` |
| `Chapter_02/Wall/` | `Common/Wall/` |
| `Chapter_03/白虎室/猜数字机关/M_TextTile_ActivatedOverlay_Transparent.mat` | `Chapter_02/TextTilePuzzle/M_TextTile_ActivatedOverlay_Transparent.mat` |

场景、Prefab、材质和项目设置按原 GUID 解析新位置。当前业务代码与 Editor 工具没有使用这些旧文件路径；`Shader.Find` 仍使用 Shader 声明中的名称，例如 `GM/TigerStarButton/StarNode`，无需随目录变更。第一章 `Chapter_01/Wall/M_Wall_001.mat` 的位置、贴图、光泽及 Shader 参数保留；目录整理不调整画质配置。

### GMShaders 目录

本目录共 33 个 Shader：第一章 2 个、第三章 31 个；第二章使用 `.gitkeep` 预留目录。当前没有跨章节共享的 Shader；今后如有跨章节用途，归入 `Common/`。章节内多个机关复用同一 Shader 时仍归该章节。

以下旧路径和当前目录均相对 `Assets/GMShaders/`，文件名保持不变；历史交付快照中的原路径按本表查找当前文件。

| 原路径或文件 | 当前目录 | 数量与用途 |
| --- | --- | --- |
| `Environment/` | Chapter_01/Environment/（目标项目内 `<PROJECT>/Assets/GMShaders/Chapter_01/Environment`） | 2 个，水洼与水滴。 |
| `GhostTiger*.shader` | Chapter_03/GhostTiger/（目标项目内 `<PROJECT>/Assets/GMShaders/Chapter_03/GhostTiger`） | 6 个，幽灵白虎本体、光晕、雾、粒子与足迹。 |
| `RewardActivationSoul*.shader` | Chapter_03/RewardActivation/SoulBinding/（目标项目内 `<PROJECT>/Assets/GMShaders/Chapter_03/RewardActivation/SoulBinding`） | 3 个，锁魂链与魂雾。 |
| `RewardActivationTalisman*.shader` | Chapter_03/RewardActivation/Talisman/（目标项目内 `<PROJECT>/Assets/GMShaders/Chapter_03/RewardActivation/Talisman`） | 3 个，符文、瘴气与仪式；仪式 Shader 也供本章其他奖励演出复用。 |
| `RewardActivationXuanwu*.shader` | Chapter_03/RewardActivation/Xuanwu/（目标项目内 `<PROJECT>/Assets/GMShaders/Chapter_03/RewardActivation/Xuanwu`） | 6 个，玄武能量、领域、仪式与灵体。 |
| `StoneTablet*.shader` | Chapter_03/RewardActivation/StoneTablet/（目标项目内 `<PROJECT>/Assets/GMShaders/Chapter_03/RewardActivation/StoneTablet`） | 5 个，四神兽石碑环境与封印效果。 |
| `TigerNail*.shader` | Chapter_03/RewardActivation/TigerNail/（目标项目内 `<PROJECT>/Assets/GMShaders/Chapter_03/RewardActivation/TigerNail`） | 3 个，虎钉闪电、符文投影与八卦。 |
| `WhiteTiger*.shader` | Chapter_03/WhiteTiger/（目标项目内 `<PROJECT>/Assets/GMShaders/Chapter_03/WhiteTiger`） | 5 个，白虎星盘发光、文字叠加、能量束、光柱与垂帘。 |

- 材质、Prefab、Profile 和 `GraphicsSettings.asset` 继续按原 GUID 引用；图形设置中已有的 20 个本目录 Shader 引用随 GUID 解析到新路径。
- `GMGhostTigerEffectController`、`GMRewardActivationVisualController`、`GMStoneTabletAmbientVFX` 及白虎星盘表现代码使用 `GM/...` 逻辑名称查找 Shader。文件迁移保留这些名称，Editor 工程文件由 Unity 重新生成。
- 本次迁移的 include 均引用 Unity 内置文件，Fallback 使用 Shader 名称，文件内容保持不变。`GMMaterials` 与 `Resources` 中随专题资源存放的 Shader 继续按各自目录约定管理。

## 完成验证

按 [项目文件更新标准](ProjectUpdates.md) 的“按影响选择验证”和“完成与维护”执行，并将本指南中受影响的业务约束作为验收依据。
