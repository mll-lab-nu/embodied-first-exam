# 功能目录重排记录：只移动文件

日期：2026-09-23。范围：仓库内的 `topogym/` Python 包；按当前工作树操作，保留已有未提交修改。

## 1. 已完成什么

- **本轮是文件归位，不是可运行接口重构。** 所有既有文件的内容和权限均未改变；没有改 import、函数、类、配置值或依赖项，也没有新增 Python 兼容层或包初始化代码。
- 原 `tasks/` 的 376 个非缓存文件已分流；现在其中只有 **13 个任务文件及原 `__init__.py`**。
- 全包 502 个非缓存文件中，**465 个移动、37 个原位保留**；另将 596 个字节码缓存原样移入 `redundants/bytecode/`。没有删除任何原有文件，没有以 Git HEAD 覆盖本地内容，也没有恢复本轮开始前已删除的文件。
- 移动前后按逐文件 SHA-256 和文件权限核对：**1,098 / 1,098 一致，遗漏 0、内容变化 0、权限变化 0**。496 个 Python 文件均可通过语法解析；这不代表 import 或运行测试通过。
- 新增内容只有目录说明、此记录、清单和校验记录。源码树之外的 `tests/`、`scripts/`、根目录 `configs/`、根目录 `assets/`、`runs/`、demo 与依赖环境未迁移；开发记录的导航及源码链接同步更新。

## 2. 当前目录

```text
topogym/
├── config/                   配置、注册、episode 规格
├── envs/                     环境协议、初态和执行
│   ├── adapters/             公共与各任务 agent/environment adapter
│   ├── execution/<任务>/     原各任务物理执行循环
│   ├── initialization/       受控初态构造与恢复
│   └── task_support/         暂不能按函数拆开的任务支持
├── world/                    Genesis 世界和物理设置
│   ├── physics/<任务>/       接触、内存、数值等引擎扩展
│   └── rope_backends/        Genesis 的 PBD / FEM+IPC 能力
├── robot/                    本体、动作解释和抓持
├── solvers/
│   ├── kinematics/<任务>/    FK / IK 求解
│   ├── collision/<任务>/     碰撞和间隙查询
│   ├── geometry/<任务>/      几何可解性与路线证书
│   └── validation/<任务>/    可达性预检
├── sensors/                  相机、标定和渲染支持
├── tasks/                    13 个 <任务名>.py + 原 __init__.py
├── assets/
│   ├── generators/<任务>/    建模、网格、外观及资产准备
│   ├── variants/<任务>/      变体采样与逆向设计
│   ├── loaders/<任务>/       参考资产和已生成实例加载
│   └── manifests/            原来源清单
├── policies/                 控制策略及动作原语
├── agents/                   bridge / rollout 外层会话和传输
├── recording/                公共录制、13 个任务 adapter 和任务归档
├── data/                     数据写入、格式和导出
├── evaluation/               成功判据、诊断和评测
├── utils/                    公共数学、几何、随机流、I/O
└── redundants/               原样隔离的剩余实现和缓存
```

`<任务>` 子目录目前只用于区分实现来源、防止同名覆盖，并方便并排比较；不表示这些重复实现必须长期保留。包内 `topogym/assets/` 放资产生成/加载代码，仓库根目录 `assets/` 里的模型素材仍在原位；两者不是同一个目录。

| 功能目录 | 既有非缓存文件数 | 归属 |
|---|---:|---|
| [config/](../../../topogym/config) | 18 | 配置、任务注册、episode 合同和公开规格 |
| [envs/](../../../topogym/envs) | 28 | 环境协议、任务 adapter、初态与执行循环 |
| [world/](../../../topogym/world) | 23 | Genesis 世界、场景支持、物理扩展与状态 |
| [robot/](../../../topogym/robot) | 14 | 机器人动作端口、控制器与抓持机制 |
| [solvers/](../../../topogym/solvers) | 28 | FK / IK、碰撞、几何证书与可达性检查 |
| [sensors/](../../../topogym/sensors) | 8 | 相机、标定、观测及 RGB 渲染支持 |
| [tasks/](../../../topogym/tasks) | 14 | 每个任务一个现有场景入口文件 |
| [assets/](../../../topogym/assets) | 63 | 机器人模型、任务几何、变体生成与资产加载 |
| [policies/](../../../topogym/policies) | 50 | 动作原语、专家策略与任务路线编排 |
| [agents/](../../../topogym/agents) | 21 | 外层 agent 传输、会话、预算与 rollout 编排 |
| [recording/](../../../topogym/recording) | 59 | 公共录制与集中后的任务录制、归档支线 |
| [data/](../../../topogym/data) | 5 | 数据格式、episode 写入与轨迹导出 |
| [evaluation/](../../../topogym/evaluation) | 56 | 任务判据、验收、诊断和跨试验评测 |
| [utils/](../../../topogym/utils) | 5 | 公共 I/O、随机流和几何数学工具 |
| [redundants/](../../../topogym/redundants) | 109 | 后端隔离、兼容层、实验、展示和旧目录标记 |

另有原根目录 `topogym/__init__.py` 1 个。上表不计本轮新增的 README，也不计缓存。

## 3. 每任务一个文件的具体含义

选取所有任务都已有的 `scene.py` 原样移动为 `tasks/<任务名>.py`。这只是当前最一致的任务场景入口，**还不是 RoboWits 示例那样继承统一 Env、集成实体、初态、目标、奖励与成功判据的完整任务类**。

- 旧 `agent_spec.py` 在 `config/task_specs/`，旧 `agent_adapter.py` 在 `envs/adapters/`；后者原本包含的目标判定仍在其内部，未提取函数。
- 独立 `evaluator/verification/anchored_verifier/topology` 归入 `evaluation/tasks/`；后续应让真正的任务成功语义回到 Task 定义，公共验证算法留在 evaluation/solvers。
- `cast_coil/assembly_task.py` 同时含装配初态、阶段、路线和目标，暂放 `envs/task_support/cast_coil/`；不把移动伪装成已经拆分职责。
- `scene.py` 中原有的公共建场景、数学辅助、相机等混合代码依然存在；本轮不会通过改写内容强行凑成统一基类。
- 原各任务 `__init__.py` 移入 `redundants/package_markers/tasks/`；根任务包的 `__init__.py` 原样保留，其中旧目录说明尚未改写。

任务入口对应：

- [topogym/tasks/blanket_flatten.py](../../../topogym/tasks/blanket_flatten.py) ← `topogym/tasks/blanket_flatten/scene.py`。
- [topogym/tasks/buzz_wire_3d.py](../../../topogym/tasks/buzz_wire_3d.py) ← `topogym/tasks/buzz_wire_3d/scene.py`。
- [topogym/tasks/cast_coil.py](../../../topogym/tasks/cast_coil.py) ← `topogym/tasks/cast_coil/scene.py`。
- [topogym/tasks/cast_keyhole.py](../../../topogym/tasks/cast_keyhole.py) ← `topogym/tasks/cast_keyhole/scene.py`。
- [topogym/tasks/fiber_bundling.py](../../../topogym/tasks/fiber_bundling.py) ← `topogym/tasks/fiber_bundling/scene.py`。
- [topogym/tasks/hedgehog_in_cage.py](../../../topogym/tasks/hedgehog_in_cage.py) ← `topogym/tasks/hedgehog_in_cage/scene.py`。
- [topogym/tasks/horseshoe_ring.py](../../../topogym/tasks/horseshoe_ring.py) ← `topogym/tasks/horseshoe_ring/scene.py`。
- [topogym/tasks/interlocked_claws.py](../../../topogym/tasks/interlocked_claws.py) ← `topogym/tasks/interlocked_claws/scene.py`。
- [topogym/tasks/knot_untying.py](../../../topogym/tasks/knot_untying.py) ← `topogym/tasks/knot_untying/scene.py`。
- [topogym/tasks/lock_picking.py](../../../topogym/tasks/lock_picking.py) ← `topogym/tasks/lock_picking/scene.py`。
- [topogym/tasks/orbits.py](../../../topogym/tasks/orbits.py) ← `topogym/tasks/orbits/scene.py`。
- [topogym/tasks/rope_threading.py](../../../topogym/tasks/rope_threading.py) ← `topogym/tasks/rope_threading/scene.py`。
- [topogym/tasks/slotted_post_ring.py](../../../topogym/tasks/slotted_post_ring.py) ← `topogym/tasks/slotted_post_ring/scene.py`。

## 4. redundants 中保留了什么

`redundants` 在这一步表示“隔离待筛选”，不是已证明可以删除；功能区仍可能在代码里依赖它们，本轮未修复或解除这些依赖。

- [mujoco/](../../../topogym/redundants/mujoco)：17 个文件；17 个明确的第二物理后端/模型/驱动/渲染文件；不包含所有 MuJoCo import 文件。
- [compatibility/](../../../topogym/redundants/compatibility)：4 个文件；旧录制目录、旧 recorder 和旧公共名称转发。
- [experiments/](../../../topogym/redundants/experiments)：54 个文件；专用 probe、探索、对照实验及旧 demo 入口。
- [presentation/](../../../topogym/redundants/presentation)：12 个文件；静态 HTML、绘图或汇报入口。
- [checks/](../../../topogym/redundants/checks)：1 个文件；独立研究规则检查。
- [benchmarks/](../../../topogym/redundants/benchmarks)：1 个文件；构建和物理单步基准。
- [package_markers/](../../../topogym/redundants/package_markers)：19 个文件；已经分流的旧包初始化文件。
- [documentation/](../../../topogym/redundants/documentation)：1 个文件；原 tasks/README.md，内容原样保留。
- `bytecode/`：596 个旧缓存文件，保留旧路径层级；不执行、不重新编译。Git 原有缓存忽略规则仍然适用。

**MuJoCo 尚未被撤销。** 全包的 60 个直接导入文件全部保留：20 个现在位于 redundants，40 个分布于 solvers、recording、evaluation、assets、envs、policies、robot 等目录。后者包括 FK/IK 和混合文件；旧依赖及 Genesis 内部库依赖也未修改。目录归位不构成 Genesis-only 运行验收。

## 5. 集中后可以并排检查的重复职责

以下是功能重合的候选组，不是已证明行为完全相同或可以直接互换的代码。

- **环境适配：** `envs/adapters/` 集中公共 rigid/FEM adapter 和 8 个任务 adapter；检查初始化、动作校验、step、观测和判据如何重复。
- **执行循环：** `envs/execution/` 集中任务 runner/runtime，`envs/episode_runner.py` 保留公共协议；之后才能统一谁拥有物理时钟。
- **机器人求解：** `solvers/kinematics/` 集中 Coil/Keyhole/Buzz Wire/Horseshoe/Knot/Blanket/Rope 等 FK/IK，`solvers/collision/` 集中各任务 clearance/guard；MuJoCo 替换应在这一层对照实现。
- **抓持与 assist：** `robot/grasping/` 集中附件和任务抓持；`envs/adapters/fem_robot.py`、任务执行器内仍有混合抓持代码，不能仅凭移动就宣称唯一 Robot 接口。
- **建模与生成：** `assets/generators/` 集中 13 个任务原 geometry 及建模工具；`assets/variants/` 集中各任务 seed/参数化生成；公共网格与交叉数学已移到 `utils/geometry/`。
- **录制：** `recording/task_adapters/` 集中 13 个任务 adapter，`recording/tasks/` 集中各家族 archive/render；便于与公共 session/replay/archive 比较重复流程。
- **验收与数据：** `evaluation/tasks/` 集中物理与几何判据，`data/exporters/` 集中轨迹和指标导出；后续分别理清 Task 的成功语义与通用导出。
- **公共数值支持：** `world/physics/knot_untying/runtime_memory.py` 与 `world/physics/rope_threading/runtime_memory.py` 等按职责相邻；不为合并名称而直接假设参数和副作用相同。

本次对完整文件 SHA-256 分组，排除包初始化文件后，未发现两份非缓存文件完全相同；主要问题是部分函数与流程的职责重合，需要下一轮逐函数比较。

## 6. 当前可运行性与后续边界

**当前工作树不能按原入口直接运行。** 按“只移动、不修改代码”要求，以下引用有意保持原字节，尚待下一轮统一修复：

- `from topogym.tasks.<任务>...` 等绝对 import，和原场景中的 `from .geometry ...` 等相对 import。
- registry 的延迟模块字符串、包 `__init__.py` 转发、`python -m` CLI，以及源码外 tests/scripts 的 import。
- `Path(__file__).parents[...]`、相对模型路径、Hydra 配置搜索路径及打包发现规则。
- 混合文件内的 scene.step、robot assist、录制、成功判定与其他跨层调用。

没有安装别名、软链接或 import hook 把旧目录隐藏恢复；未新增空 `__init__.py`。新目录的接口及依赖并未因此自动建立。未执行物理测试或导入整包，只做完整性和 AST 语法检查。

## 7. 逐文件清单与回溯

- [全部 502 个非缓存文件的迁移清单](structure_move_files_20260923_zh.md)：旧路径、新路径、简介、归属理由，保留原位项也列出。
- [完整机器可读迁移记录](structure_move_manifest_20260923.json)：包含全部 1,098 个原文件的双向路径、原 SHA-256、字节数和权限；可按 old/new 查询，缓存也没有遗漏。
- [移动后核对结果](structure_move_verification_20260923.json)：记录文件、语法、任务入口和源码未变的核对结果。

迁移清单提供逆向移动依据；若之后编辑了新路径文件，回退前应先确认 SHA-256 和旧路径是否被重新占用，不能覆盖后续工作。
