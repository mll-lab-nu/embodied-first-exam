# 无调用脚本清理、唯一实验室与资产工具归并

> 后续复核已纠正部分删除判断；textures/fem 已恢复并补回 Blanket 纹理调用。当前恢复范围和后续任务运行目标见[基础运行计划](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_base_task_runtime_plan_zh.md)。本页清单记录当时的删除动作。

日期：2026-09-23。本轮根据用户要求整理当前 simulator；**未运行测试、测试收集、项目导入验证、仿真、渲染或数据转换**。下列变更已写入代码，不能据此声明物理运行通过。

## 1. 结果与范围

- 删除 26 个未接入当前调用链的源码脚本；动态注册的 13 个 Task、实际使用的具名变体和公共接口保留。
- 背景只保留 `compact_lab`；布局与 Genesis 实体构建合为 `world/lab.py`。
- Buzz Wire 与 Lock Picking 的专属外观函数合入各自 `assets/geometry/<task>.py`；共享表面工具移到 `assets/surfaces.py`，撤销 `assets/appearance/`。
- Hedgehog in Cage、Fiber Bundling 的默认机器人改为 `panda_robotiq`，通过共享配置和控制器加载。
- Rope Threading 的参考参数转换移为手动离线工具 `scripts/import_rope_threading_reference.py`；已打包的参考 JSON 和来源记录保留。
- 更新[全项目脚本清单](../../../legacy/cleanup_20260929/docs/develop/dev-logs/script_inventory_zh.md)及[逐测试脚本说明](simulator_test_scripts_zh.md)。历史 `runs/legacy/reports`、根目录资产来源副本与延期 agent 没有在本次删除。

这里的“无调用方”依据当前 Python 导入、符号/路径搜索、注册表动态入口和测试引用判断；不把“没有静态 import”直接当成删除条件。CLI 和公共库入口由用户或外部程序调用，不能按普通内部函数处理；本次明确保留的 Rope 转换工具也属此类。

## 2. 删除清单：26 个脚本

以下路径均相对 `topogym/`，已删除，不作为当前文件链接。

- 未接入的只读评价与旧签名：
  - `evaluation/geometry_metrics.py`：绳、四面体、扫掠和穿越链测量。
  - `evaluation/lock_picking.py`：旧 Lock 记录的回退周期统计。
  - `evaluation/particle_metrics.py`：通用粒子测量。
  - `evaluation/stability.py`：独立阈值稳定性包装。
  - `evaluation/surface_collision.py`：未接入的 ipctk 表面查询。
  - `world/signatures.py`：旧模型/场景签名；当前状态身份不依赖它。
- 未接入的规划及专用求解：
  - `planning/subgoal.py`：旧子目标结构。
  - `planning/waypoint.py`：旧路径点生成。
  - `planning/grasp_sites.py`：布面抓取候选选择。
  - `planning/motions/horseshoe_ring.py`：旧链条折叠参考变换。
  - `planning/motions/lock_picking.py`：旧盘钥参考动作。
  - `solvers/geometry/lock_picking.py`：未接入的角区间计算。
- 未使用的模型、几何与旁路工具：
  - `assets/geometry/braid.py`：编织中心线生成。
  - `assets/textures.py`：独立程序化纹理生成。
  - `utils/geometry/closed_band.py`：闭合带几何工具。
  - `utils/geometry/rope_crossings.py`：独立绳交叉分析。
  - `robot/collision_geometry.py`：未接入的机器人碰撞网格提取。
  - `sensors/camera_rigs.py`：未使用的程序化相机组；实际相机仍由共享 YAML 和 `sensors/cameras.py` 创建。
  - `recording/media.py`：旧抽帧/拼图/编码旁路；保留公共 session、encoding、timeline。
  - `data/importers/rope_threading.py`：未接入的完整参考轨迹导出工具，区别于下文保留的初态参数提取工具。
- 未接通的物理辅助包装：
  - `world/physics/fem.py`：孤立的 FEM 材料包装与顶点读取。
  - `world/physics/constraints.py`：旧焊接查询/释放，未接入统一抓持和回溯。
- 没有当前具名变体、也没有其他调用方的派生脚本：
  - `tasks/task_variations/buzz_wire_3d.py`。
  - `tasks/task_variations/cast_keyhole.py`。
  - `tasks/task_variations/horseshoe_ring.py`。
  - `tasks/task_variations/lock_picking.py`。

最后四份文件不提供当前 `VARIATIONS`；移除后仍可选择 base，不能使用的旧变体名仍被拒绝。保留实际具名参数所在的 Blanket、Knot 模块，以及被 Coil 几何派生调用的 Coil 模块。

`evaluation/` 现在保留 `cloth_metrics.py` 与 `motion_certificate.py`；`planning/` 保留被使用的 Coil 参考运动。这里是按脚本清理，不宣称已逐函数删除全部历史辅助逻辑。

## 3. 唯一背景与资产归并

```text
topogym/
├── world/
│   ├── lab.py                       compact_lab 布局 + Genesis 实体构建
│   └── visuals/presentation.py      共享外观与相机接线；拒绝其他背景
├── config/profiles/
│   └── presentation_configs/compact_lab.yaml
└── assets/
    ├── surfaces.py                  共用木纹工具、角色粗糙度
    └── geometry/
        ├── buzz_wire_3d.py          几何、支撑和专属外观
        └── lock_picking.py          几何、配色和孔口描边
scripts/
└── import_rope_threading_reference.py
```

- 删除旧 `world/lab_layout.py` 与 `world/nyx_lab.py` 的拆分和中转；封闭实验室布局保留，撤销 `lab`、`checker` 分支。
- 共享 preset 从 `nyx_lab.yaml` 更名为 `compact_lab.yaml`；两套机器人 profile 指向同一背景。
- `prepare_presentation` 对其他背景报错，检查发生在添加布景实体之前。
- Nyx/rasterizer 仍是同一个 Genesis 场景的渲染选择，不是两套背景或两种物理模拟途径。
- 两份任务外观脚本合入对应几何文件，撤掉反向导入；不复制共享木纹实现到每项任务。
- `world/visuals/` 仍负责把参数接到 Genesis 表面和相机，职责不同于离线资产几何生成。

## 4. Rope 的“导入来源数据”到底是什么

它是**把外部示例已导出的几何和首帧状态，转换成我们建模时读取的参考参数 JSON**。适用场景是重新提取该示例的初始绳形、圆环布置，或在上游数据更新后重建参考文件；不在每次创建环境、reset 或 step 时执行。

脚本：[import_rope_threading_reference.py](../../../scripts/import_rope_threading_reference.py)。来源 URL 是随代码和资源保存的出处记录；脚本不联网下载，不运行来源项目。

| 调用者提供的本地文件 | 内容与用途 |
|---|---|
| `geometry.json` | 几何名称、形状/尺寸、局部变换、所属刚体，以及桌面与夹具几何 |
| `manifest.json` | 二进制数组的位置、dtype、shape 和 SHA-256；指导读取和完整性校验 |
| `phase-000.bin` | 已导出的状态数组；提取首帧刚体位姿，以及初始关节值、时间和交叉信息 |

具体转换过程：

1. 校验二进制文件和数组哈希，按 manifest 描述读取数组。
2. 按首帧位姿转换 80 段命名绳胶囊的端点，检查连续性，得到按材料方向排序的 81 个绳节点。
3. 从每环 64 段胶囊中提取三个环的中心、法向、局部基与半径，保留支架/底座参数。
4. 写出参考 JSON，含绳节点和半径、环/支架、桌面基准、来源哈希，以及目标穿环顺序 `R1- → R2+ → R3+`。

当前运行数据链：

```text
外部 geometry.json + manifest.json + phase-000.bin
    ↓ 手动运行 scripts/import_rope_threading_reference.py
参考参数 JSON
    ↓ 已收录版本：assets/resources/templates/rope_threading_reference.json
assets/geometry/rope_threading.py
    ↓ 当前任务尺度/坐标变换下的绳、环和支架网格
tasks/rope_threading.py 的实体声明 → Genesis World（FEM/IPC 运行仍受阻）
```

输出不是完整运动轨迹、Genesis checkpoint 或可执行 Python，也没有转换或重现来源引擎的动力学。代码中的 `original MuJoCo world` 只说明原始坐标来源；工具不 import/调用 MuJoCo。它按该示例的对象名称和数量实现，不是通用资产导入器。

若以后不需要重新提取，可以再删除此 CLI；当前 simulator 只依赖已打包的[参考 JSON](../../../topogym/assets/resources/templates/rope_threading_reference.json)和[catalog](../../../topogym/assets/resources/catalog.json)。本轮保留工具供检查，没有执行转换、下载或替换参考资源。将来更新包内 JSON 时，需要同步更新 catalog 的 SHA-256。

## 5. 能力边界和检查状态

- 13 项 Task 定义保留。8 项刚体/关节链与 Blanket PBD 共 9 项有待验证的生命周期代码路径；4 项 FEM/IPC 仍在 reset 前明确报告缺口。七项未完成判据仍不允许声明 solved。
- 删除孤立 FEM/约束包装没有补齐软体参考构形、IPC 任意状态恢复或 assist grasp；[registry](../../../topogym/config/registry.py) 将后续缺口位置指向实际保留的 `world/genesis_world.py`、`world/physics/ipc.py` 及各 Task。
- 补写 `test_configuration.py`：检查 Hedgehog/Fiber 经自动配置实际选出 Panda＋Robotiq 关节描述、两种机器人共用 compact_lab、其他背景在修改场景前被拒绝。
- 更新架构测试的退役 import 名单。没有增加测试脚本；仍为 19 个测试脚本及 1 个公共夹具。
- 静态语法、活动 import 与未定义名称核对未发现问题；共享配置引用和当前文档链接存在，12 项打包资源与 catalog 哈希一致且内容未变。转换算法及 compact_lab 布局的 AST 与整理前一致。
- 全仓清单识别 17,188 个代码路径：当前 116、延期 agent 59、历史 17,013；当前源码直接 MuJoCo import 为 0。计数包括包标记、测试与工程工具，不代表运行通过。
- 本轮检查限于源码 AST、引用/路径、资源哈希与文档清单；**测试尚未执行，无通过率或物理正确性结论**。

此前接入范围与 reset 设计见[任务接入记录](simulator_task_integration_20260923_zh.md)；其中整理前的文件名和机器人默认值以本页、当前 registry 和[最新脚本清单](../../../legacy/cleanup_20260929/docs/develop/dev-logs/script_inventory_zh.md)为准。
