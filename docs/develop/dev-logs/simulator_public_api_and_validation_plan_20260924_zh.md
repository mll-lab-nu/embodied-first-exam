# Simulator 公共接口、特权回溯与验证实施计划

日期：2026-09-24。**本文件保留开发计划，并已按最新权限、目录和录像要求修订；实施与实测结果见 [本轮报告](simulator_public_api_implementation_20260924_zh.md)。**

依据：[核心就绪度审计](../../../legacy/cleanup_20260929/docs/develop/dev-logs/simulator_core_readiness_audit_20260924_zh.md)和用户本轮五项要求。以下新合同取代旧计划中的 `reset(state_id=...)`、回溯后保留可访问旧分支等约定；历史测试结果仍按其当时的合同理解。

## 1. 先明确现状和这次要改变的行为

| 项目 | 当前实现 | 本阶段目标 |
|---|---|---|
| 物理历史 | 每个成功提交的外部物理 tick 保存完整 EpisodeState | 保持，不降为每个 action 或每个视频帧才保存 |
| 普通 reset | `reset(seed=..., state_id=...)` 混合新建和回溯 | `reset(*, seed=None)` 只开启新 episode；管理方可选择 seed；同 seed 重建相同初始条件 |
| 历史回溯 | 当前 episode 内恢复；旧未来及分支仍可选择 | 独立特权 `rewind_to(state_ref)`；回溯点之后的旧未来永久失效 |
| 跨 reset 回溯 | 不支持；旧 World 和历史会释放 | 明确禁止：只维护当前 episode，见 §3.4 |
| 入口 | `Env(SimulatorConfig(...))` | 增加薄封装 `topogym.env_list()`、`topogym.make()`，继续使用同一个 Env |
| 控制 | 机器人关节位置命令 | `JOINT_ABS`、`JOINT_DELTA`、`EE_ABS`、`EE_DELTA`，按机器人描述确定维度 |
| observation | 混合完整 world 状态、机器人、任务和 RGB | 明确 `EE` / `JOINT` 观察合同；详细 World 状态通过特权入口读取 |
| 视觉 | Nyx + compact_lab 已接通，默认关闭 RGB；打开后实际多出相机 | 默认视觉配置开启 RGB，双臂严格 4 路、单臂严格 3 路，落实近景；显式无图像配置保留 |
| solved | 公共 TaskResult 已有，7 项任务完整判据尚缺 | 统一结果接口和结束语义；逐任务补判据并独立验收，不把“能 step”视为“能判 solved” |
| 稳定性 | 13 项基础任务有短程证据 | G2 必做，并补连续运行、reset/close、异常边界和资源证据 |

### 1.1 对“默认每 tick 保存一次”的准确回答

**是的，但保存者是 Env 的 EpisodeHistory，`StateInfo` 只是索引元数据，不是完整恢复数据。**

- `Env.reset(seed=...)` 完成场景、机器人、Task 初态准备后保存 tick 0。
- `Env.step(action)` 每次成功执行 `World.advance()`、Task 更新后调用 `_save_state()`。保存的是 World、Robot 控制目标、Task 判据及 RNG 等完整状态。
- 默认 `physics_dt_s=0.0025`，一个外部 tick 为 2.5 ms；默认一个 action 推进 10 tick，即 25 ms。因此 action 中途也有恢复点。
- `solver_substeps=4` 是一个 tick 内的数值细分，不产生四个额外公开恢复点。
- 没有独立的现实时间计时线程；时间来自 `physics_step × physics_dt_s`。读取 observation、render 和录制不推进物理。
- 每 tick 保存物理状态不等于每 tick 渲染 RGB。发生异常而未成功保存的半成品状态也不属于可恢复历史。
- 有实现不等于已经对所有接触阶段、长时间和随机状态完成验证；这部分由 G2/G3/G5 补证。

依据：[Env](../../../topogym/simulator/env.py)、[EpisodeHistory](../../../topogym/simulator/history.py)、[WorldState](../../../topogym/world/state.py)。

## 2. 公共 API 的拟定合同

以下接口由 `simulator/` 统一组织。管理方拥有 make/reset/close；外部操作方只接收不带 reset 的交互句柄。这里是本地 simulator 接口，不是 agent 或网络服务。

拟定默认值为 `observation_mode="JOINT"`、`control_mode="JOINT_ABS"`、`enable_rgb=True`，沿用现有关节控制基础并开启标准视觉；Env 配置与 make 默认保持一致。下面示例显式选择 EE 模式。

```python
import topogym

task_ids = topogym.env_list()
catalog = topogym.env_list(details=True)
env = topogym.make(
    "cast_coil",
    observation_mode="EE",          # 或 JOINT，与 control_mode 独立
    control_mode="EE_ABS",          # 或 EE_DELTA / JOINT_ABS / JOINT_DELTA
    enable_rgb=True,                # 标准默认；Nyx + compact_lab
    enable_privileged=True,         # 由本地宿主明确开启，普通使用默认 False
)

obs, info = env.reset(seed=17)
initial_ref = info["state_ref"]
obs, reward, terminated, truncated, info = env.step(action)
images = env.render()              # 与当前 observation 共用 SensorFrame

obs, info = env.privileged.rewind_to(initial_ref)
history = env.privileged.get("history")
world_details = env.privileged.get("world")

# 操作方只持有 actor；任何模式均无 reset / seed 修改入口。
actor = env.interaction(privileged=True)
actor.step(action)
actor.rewind_to(info["state_ref"])

# 只有管理方可以 reset；新的 episode 使旧 actor / StateRef 失效。
obs, info = env.reset(seed=17)       # 相同 seed，新的 episode、相同初始环境
obs, info = env.reset(seed=18)       # 管理方可以主动切换 seed
env.close()
```

| 接口 | 要实现的边界 |
|---|---|
| `env_list()` | 稳定排序的任务 ID；`details=True` 返回机器人、物理类型、基础变体、操作级能力及缺口；查询不初始化 Genesis/CUDA、不创建资产 |
| `make(task_id, ...)` | 校验注册名和配置，返回唯一 Env；构建物理场景仍在 reset；未知配置在改变引擎前拒绝 |
| `action_spec` / `observation_spec` | 查询组名、数组形状、dtype、单位、坐标系、关节顺序、控制模式及相机 schema；不冒称已有 Gymnasium Space 全兼容 |
| `reset(*, seed=None)` | 仅管理方；唯一语义为新 episode；显式整数 seed 是复现入口；省略 seed 则生成并返回本次实际 seed，没有 last_seed 属性 |
| `step(action)` | 返回 `(obs, reward, terminated, truncated, info)`；先验证整个 action 再施加；记录实际推进 tick 数；终止后继续 step 明确失败 |
| `observe()` | 返回当前模式的只读 observation；重复调用不得改变物理、判据持续时间或 RNG |
| `render()` | RGB 字典，使用与 observation 相同状态身份及图像缓存；显式无图像环境调用时清楚报告未启用，不临时换 renderer |
| solved | `info["task_success"]` 表示成功；`goal_evaluation_complete` 表示该任务判据是否完整；两者不能混用 |
| `close()` | 幂等；释放 World、Nyx、历史存储和输出资源；关闭后原 Env 不可重启，需重新 make |
| `env.interaction(privileged=...)` | 管理方授予操作句柄，两种模式均无 reset；只有显式授权后才可使用 rewind/get。`env.privileged` 是管理方内部诊断入口；提供受限 `get()` 和 `rewind_to()`，不开放通用 `getattr`、原生 Scene 或可写张量 |

### 2.1 观察与动作的具体约定

- **模式独立**：`EE` 观察可以搭配关节控制；`JOINT` 观察也可以搭配 EE 控制。不要因切换观察模式改变物理运行路径。
- `JOINT` 观察：每个 arm group 的关节位置、速度及夹爪实测状态；`EE` 观察：每组 TCP 的世界坐标位置、`wxyz` 姿态及夹爪实测状态。共同提供 episode/state/tick/time 标识、RGB 和相机标定。
- **TCP 显式定义**：不能把现有 `hand_link` 位姿直接命名为工具中心位姿。共享 RobotDescription 记录 `hand_link → TCP` 固定变换，两种机器人分别提供值；观测、控制和 IK 使用同一变换。
- `EE_ABS`：世界坐标位置（m）与归一化 `wxyz` 四元数；`EE_DELTA`：相对 action 提交前的**实测 TCP**，世界坐标平移增量（m）和世界轴旋转向量（rad）。姿态采用 `R_target = Exp(delta_rot) × R_measured`，明确乘法顺序。
- `JOINT_ABS`：绝对关节角；`JOINT_DELTA`：相对提交前实测关节角的增量。夹爪在四种模式中均为显式绝对目标，不随模式变成增量。
- 夹爪先沿用模型已定义的原生坐标，并在 spec 标单位和限位；Robotiq 的旋转驱动角不能冒称开口米数。若以后提供统一开口宽度接口，需单独标定转换。
- 省略的组/字段保持其已有控制目标；`{}` 保持目标。显式零增量的含义是以当前实测姿态为目标，和 `{}` 不一定等价。
- ALOHA 与 Panda 的关节数量、组名从描述读取；不能硬编码“两臂各 7 关节”。
- EE 命令经公共 IK 求解为关节目标；检查可达残差、限位及有限数值后再提交。双臂中任何一臂非法或求解失败，整个命令无副作用地拒绝；不得先执行一臂再失败。求解失败也不得消耗未回滚的随机流。
- 详细物体位姿、FEM 顶点、内部任务指标等默认不混入普通 observation。公共 `info` 保留生命周期和成功信息；研究/诊断数据走特权 `get()`。

这层是 simulator 的控制模式转换，不是 planner；不在其中规划成功轨迹、抓取策略或偷偷调用 `scene.step()`。

### 2.2 solved、失败、超时与故障

- 成功：`task_success=True`、`terminated=True`；失败终态：`task_success=False`、`terminated=True`，给明确原因。
- 达到时间上限而未终止：`truncated=True`；不把时间耗尽当成 solved。
- 同一 tick 同时到达成功和时限：先提交 Task 结果，成功终止优先，避免同时设置互相冲突的结束原因。
- 非有限物理量、求解器错误、快照写入失败是运行故障，抛出带阶段信息的异常，不能伪装成正常任务失败或返回成功 transition。
- 判据仅在物理 tick 更新；重复 observe/render/特权 get 不增加“稳定满足目标”的时间。
- 七项 `goal_complete=False` 的任务可以继续用于环境运行验收，但在判据补齐前不能声称“13 项 solved 监测全部完成”。

## 3. 历史、回溯与新 episode

### 3.1 用完整身份定位，不能只传一个整数

在 `simulator/history.py` 定义不可变 `StateRef(episode_id, state_id)`。普通 info 返回当前引用；特权 `get("history")` 返回仍有效状态的 StateInfo。

- `state_id` 是身份，不是 `physics_step` 或时间；回溯后分配的新状态 ID 不得复用已作废 ID。
- 时间只用于查询已保存 tick 的元数据。第一版不引入任意浮点时间插值恢复接口。
- 一个 episode 的当前可恢复历史是一条有效路径；不再提供旧分支选择。
- 现有 `branch_id` 可保留为**续跑段身份**用于录像/日志隔离，不再表示旧未来仍可选择；不再平行引入一套功能相同的 branch/revision 命名。

### 3.2 rewind 是“恢复并截断”，不是“恢复并保留所有分支”

```text
回溯前：A0 → A1 → A2 → A3 → A4 → A5
                       ↑ 回到 A2

回溯后：A0 → A1 → A2 → A6 → A7 ...
                         新 action 产生的新状态

A3、A4、A5：永久作废；不能再 get / rewind_to，也不在有效 history 中。
```

1. 校验特权、episode 身份、目标仍在有效路径且 checkpoint 完整；非法请求不能修改当前状态或删历史。
2. 恢复 World、Robot 控制状态、Task、RNG、约束和时钟；恢复成功后再提交历史截断及续跑段切换。
3. 清理失效观察缓存、旧控制模式缓存和废弃快照资源；记录被作废 ID 与原因。存储共享缓冲区应按引用处理，不能误释放仍有效快照。
4. 返回恢复点 observation/info；回溯本身不产生物理 tick，不增加已保存物理状态数。下一次成功 tick 才创建新 state_id。
5. 从 action 内部 tick 回溯后，下次 `step()` 是新 action，正常推进新的 decimation；不自动执行旧 action 剩余部分。
6. 支持回到 tick 0。恢复一个已结束状态后仍是结束状态，不能继续 step；需回到更早未结束状态或普通 reset。
7. 恢复过程出错时不得宣称已完成截断。若底层已经部分修改且无法保证原子回滚，Env 必须进入 faulted 状态，仅允许已验证的恢复路径或 close，不能继续使用半恢复状态。

已写出的报告/MP4 可以作为**审计证据**保留，不是可恢复历史。有效轨迹索引必须标废弃段无效，防止数据读取端把它当成当前轨迹。公共 API 不能重新取得这些旧未来的可用状态句柄；已经被外部复制的日志不承诺物理擦除。

### 3.3 reset 与随机性

管理方以相同 `seed` 调用 `reset(seed=...)` 的目标是：**在配置、资产和软件/设备运行条件相同的情况下，新 episode 的初始几何、材料、纹理、机器人状态、任务内部状态和随机流一致。** episode UUID、输出目录和创建时间应不同，不应进入物理内容指纹。

需要逐项控制，而不是仅调用一次 `numpy.random.seed()`：

| 随机来源 | 要做的工作 |
|---|---|
| 任务参数、变体、几何和纹理 | 统一从 episode seed 派生命名子流；沿用 `utils/variant_rng.py`，避免依赖模块调用顺序或 Python `hash()` |
| Task/Env 局部 Generator | 统一初始化、记录版本和恢复 RNG 状态；不能有无 seed 的隐式 generator |
| Python / NumPy / Torch CPU 与 CUDA | 在实际库初始化顺序下设种子；当前 `seed_process()` 只处理已加载 Torch，需核对首次 reset 与后续 reset 的一致性 |
| Genesis / IK | 记录引擎 seed 和求解器设置；核对随机采样、重试和缓存；不能让渲染消耗物理随机流 |
| Nyx | 核对路径采样、抗锯齿、去噪及历史缓存是否具有随机/时序状态；验证 reset 后首帧及回溯后首帧是否可复现；若需派生采样 seed，使用 episode seed、camera ID 和物理 tick 等稳定键，不用新 UUID、分支 ID 或 render 调用次数 |
| 资产缓存 | 内容哈希由规范化参数、seed 和生成器版本决定；不能受 run 路径、UUID、调用先后影响 |

本地 `gs_nyx_plugin/nyx_camera_options.py` 没有显式 seed 字段，在所查 Python 实现和 SDK 类型声明中也未找到可直接使用的随机种子入口。**这不证明 Nyx 一定不可复现，但目前不能声称 episode seed 已控制其全部采样。** 要先做原始帧复现检查；若存在隐藏随机源，补明确可控接口或固定的采样初始化，并把所需依赖补丁/版本纳入仓库依赖记录。不能虚构 `NyxCameraOptions(seed=...)` 参数，也不能用放宽图像误差来掩盖尚未控制的随机源。

验证时分开报告：初始声明/资产的精确内容一致、初始物理数组一致、后续浮点轨迹容差、原始 RGB 是否逐像素一致。浮点并行积分的确定性与“随机源都由 seed 控制”不同；所有容差及设备/版本边界必须预先声明，不承诺任意 GPU 或版本之间位级相同。视觉可复现仍未确认时，不能勾选“所有随机性控制完成”。

### 3.4 最终边界：一个当前 episode，不维护跨 episode 存档

- `reset(seed=...)` 由环境管理方调用，可以更换 seed；每次 reset 都创建新 episode，释放旧 World/历史。
- 外部操作方只获得 `env.interaction(privileged=False/True)`。两种模式均无 reset、make、close 或 seed/config 修改接口。
- 特权仅增加当前 episode 内的 `rewind_to` 和只读 `get`，不能用旧 episode 的引用跨 seed 恢复；同 seed 的旧 episode 也不可恢复。
- 管理方 reset 后旧普通/特权句柄均失效，必须重新发放当前 episode 的句柄。
- 不增加 last_seed 属性，不增加跨 World checkpoint 存档模块，不增加跨 episode 回溯测试。
- Python 对象封装是受信本地调用的接口边界；恶意同进程反射攻击的隔离属于后续进程沙箱范围。

## 4. 要添加或调整哪些实现脚本

下表是修改位置和内容，不要求把现有模块再复制成平行框架。未列删除通用 FEM/纹理等实现；这些能力继续保留。

### 4.1 入口、生命周期、历史与权限

| 脚本 | 操作 | 具体内容 |
|---|---|---|
| `topogym/simulator/api.py` | 新增 | 薄 `env_list()` / `make()`；复用 registry、SimulatorConfig 和 Env，惰性加载引擎 |
| `topogym/__init__.py` | 修改 | 导出公共入口和必要类型，不在 import 时初始化物理或 GPU |
| `topogym/simulator/config.py` | 修改 | observation/control mode、特权开关、默认视觉配置及交叉校验；无图像运行显式配置 |
| `topogym/config/registry.py` | 修改 | 同一份任务目录供 env_list 和 make 使用；能力细化到控制、观察、回溯、solved，不用 integrated 代替通过证据 |
| `topogym/simulator/env.py` | 修改 | reset 与 rewind 分离；新增 observation_spec 和不含 reset 的交互句柄；统一错误状态机；控制编译、每 tick 提交、只读结果及输出事件 |
| `topogym/simulator/history.py` | 修改 | StateRef、有效路径截断、永不复用 ID、失效引用拒绝；Transition 记录提交动作和实际关节目标、时间及段身份 |
| `topogym/simulator/privileged.py` | 新增 | 特权 facade：rewind_to 和白名单 get；拒绝未启用访问；只返回复制/不可变数据 |
| `topogym/world/genesis_world.py` | 修改 | 完整恢复/失败处理和诊断入口；World 保持唯一物理推进所有者 |
| `topogym/world/state.py` | 修改 | 补核对恢复覆盖、随机状态、无损存储引用释放及完整性校验；不得删除用于接触续跑的内部状态 |
| `topogym/world/physics/ipc.py` | 修改 | 截断/close 时 native checkpoint 资源释放；失败恢复边界、约束缓存及原生恢复验证 |

特权 `get()` 初版白名单：`state_info`、有效 `history`、当前 `world`、`robot`、`task`、`diagnostics`。不先承诺对任意旧 checkpoint 直接解码全部传感观测；访问历史物理状态通过合法 rewind。IPC 接触数据当前覆盖不足的项目必须附 availability，不能用空数组假装“无接触”。这里的特权是本地调用权限边界，不是同进程恶意 Python 代码的安全沙箱。

### 4.2 控制、观察、相机与随机性

| 脚本/配置 | 操作 | 具体内容 |
|---|---|---|
| `topogym/robot/control.py` | 新增 | 四种模式的动作校验和关节目标编译；双臂原子提交；记录可恢复控制器状态 |
| `topogym/robot/joint_position.py` | 修改 | 保留统一底层关节执行；供模式转换层调用；观察拆分、目标恢复、夹爪单位保持明确 |
| `topogym/robot/description.py` | 修改 | 共享 TCP 变换、关节组、控制规格合同 |
| `topogym/robot/aloha/description.py`、`robot/panda_robotiq/description.py` | 修改 | 分别补双臂/单臂 TCP 与观察/动作规格；Panda 路径同样位于 `topogym/` 下 |
| `topogym/robot/panda_robotiq/gripper.py` | 按需修改 | 仅在夹爪语义/校验需要补充时完善原生角度映射，不制造未经标定的 aperture 接口 |
| `topogym/solvers/genesis_kinematics.py` | 修改 | FK 检查 IK 残差、可达性/限位与查询副作用；返回明确失败信息，不隐式步进 |
| `topogym/sensors/observation.py` | 修改 | 按 EE/JOINT 组织公共数据；详细 World 状态从默认 observation 移出；保持不可变 SensorFrame 共用 |
| `topogym/sensors/camera_info.py`、`sensors/cameras.py` | 修改 | 统一标准 camera ID、标定和动态腕部安装验证；后者同样位于 `topogym/` 下 |
| `topogym/config/scene.py` | 修改 | 在创建相机前落实 observation_cameras，只创建选中的默认 4/3 路，避免只在输出端过滤 |
| `topogym/config/profiles/camera_configs/aloha_observation.yaml` | 修改 | `cam_high/cam_low/cam_left_wrist/cam_right_wrist`，两固定视角和左右腕部；调近工作区取景 |
| `topogym/config/profiles/camera_configs/panda_robotiq_observation.yaml` | 新增 | `agentview/front_oblique/wrist`，两固定视角和一个腕部 |
| `topogym/config/profiles/tabletop_aloha.yaml`、`tabletop_panda_robotiq.yaml` 及 `env_configs/world_tabletop{,_aloha}_v1.yaml` | 修改 | 两个 profile 接入相机合同，清除默认合并导致的多余机位，统一 compact_lab；调试相机显式开启 |
| `topogym/world/tabletop.py`、`world/visuals/presentation.py` | 按需修改 | 消费已解析配置，不另造 Task 相机；验证背景和材质实际生效；均位于 `topogym/` 下 |
| `topogym/sensors/renderers/nyx.py` | 修改 | 随 reset/rewind 失效采样缓存；验证渲染可复现入口，完整记录 spp/denoise 等配置，无静默 Rasterizer fallback |
| `topogym/utils/variant_rng.py` | 修改 | 命名随机流合同及版本、初始化次序、seed 合法性；纠正当前注释中过强的任意机器位级复现承诺 |
| `topogym/assets/textures.py` 及各 Task 的几何/变体生成调用 | 审核后按需修改 | 消除未受 episode seed 控制的随机入口，确保纹理与资产内容复现；不为凑整齐新增空文件 |

视觉和录像统一采用用户指定的 **848×480、30 fps**，固定 spp/去噪参数并保留原始 PNG；最终距离、FOV、目标像素覆盖阈值在实测前写入配置与报告。用所有任务的 home 与操作区代表姿态检查孔槽、细绳、夹爪是否可辨，不能只验证图像尺寸或改视频编码掩盖远景。配置生效与实际画面验收分别记录。

### 4.3 Task、录制、数据和安装

| 脚本 | 操作 | 内容 |
|---|---|---|
| `topogym/tasks/base.py` | 修改 | 公共 solved/失败/稳定时长合同、只读查询和回溯恢复；明确首次满足判据的计时边界并测试 |
| `topogym/tasks/buzz_wire_3d.py` | 后续判据阶段修改 | 连续穿越、终点支撑和能量/历史资格 |
| `topogym/tasks/lock_picking.py` | 后续判据阶段修改 | 止挡、同轴间隙、过载与退出/释放资格 |
| `topogym/tasks/fiber_bundling.py` | 后续判据阶段修改 | 所有细杆按要求通过孔口及完整物理资格 |
| `topogym/tasks/rope_threading.py` | 后续判据阶段修改 | 按材料点顺序判定完整穿线 |
| `topogym/tasks/knot_untying.py` | 后续判据阶段修改 | 实测拓扑解开、释放与停稳 |
| `topogym/tasks/orbits.py` | 后续判据阶段修改 | 完整解缠判据，不能只看绕数 |
| `topogym/tasks/slotted_post_ring.py` | 后续判据阶段修改 | 环完整退出及拓扑/接触资格 |
| 其余六个 Task 脚本 | 审核，必要时修改 | `cast_coil.py`、`cast_keyhole.py`、`horseshoe_ring.py`、`hedgehog_in_cage.py`、`interlocked_claws.py`、`blanket_flatten.py`：现有判据正反例、seed 初态和公共合同；均在 `topogym/tasks/` |
| `topogym/recording/session.py`、`recording/timeline.py` | 修改 | 消费 reset/rewind 生命周期事件；恢复点开始新段；记录旧段失效而保留审计视频；均在 `topogym/` |
| `topogym/data/episode_dataset_writer.py`、`data/h5_schema.py` | 修改 | 模式/动作单位、请求动作与执行目标、失效轨迹索引和 schema 版本；普通 reset 切换 episode，不能拼成一个样本 |
| `pyproject.toml` | 修改 | 打包新增模块/相机配置、必要依赖与 test markers；不把 agent/deferred 拉进公开安装 |
| `scripts/test_base_tasks.py` | 修改 | 扩展现有进程隔离驱动，选择验收组/seed/模式/时长并统一证据，不再另写一套执行器 |
| `tests/runtime_evidence.py` | 修改 | 使用特权只读诊断，记录每 tick 身份、动作转换、随机源配置、回溯作废和真实相机参数 |

判据阶段不要求先做 planner 或全流程成功 demo；可以用经独立确认的实测状态、数值夹具和局部物理过程验证。但不能只用 mock 的 `success=True` 证明真实 Task 已能识别 solved。

## 5. 测试逐脚本计划

现有基线是 162 个参数化用例，136 个找到历史通过记录、26 个缺保存的通过记录；这些数字来自上一轮审计，不是本轮执行结果。接口和历史语义改变后会增删用例，不能直接承诺“再跑 26 个就全部完成”。

下表覆盖本阶段新增或受影响脚本；其它资产、碰撞、材料、任务变体等现有单元测试继续作为回归，不无理由重写。

### 5.1 无 GPU 的接口和数据合同

| 测试脚本 | 操作 | 验证功能与关键反例 |
|---|---|---|
| `tests/contracts/test_public_api.py` | 新增 | env_list/make/spec，13 个注册项、惰性 import、错误任务/模式、EE/JOINT 观察与控制独立组合；此处使用替身，不冒充物理通过 |
| `tests/contracts/test_env_lifecycle.py` | 扩展 | G2 状态机：make 后、reset 中、ready、done、faulted、closed；只读无副作用；中途终止/截断；非法 action 原子性；close 失败和重复关闭 |
| `tests/contracts/test_episode_rewind.py` | **重写冲突断言** | 每 tick 存储、tick 0/中途 tick、恢复后截断、旧未来引用永久拒绝、ID 不复用、普通 reset 新身份、非法恢复无变化；不再断言旧未来可恢复 |
| `tests/contracts/test_privileged_access.py` | 新增 | 默认无特权、白名单、跨 episode/废弃引用、返回值隔离、不能获取可写 World/Scene；管理方 reset 后旧句柄失效 |
| `tests/unit/test_control_modes.py` | 新增 | 世界坐标旋转/平移约定、TCP 变换、delta 基准、四元数/有限值/维度/限位、缺省字段、双臂失败原子性；不代替真实 IK 验证 |
| `tests/unit/test_seed_streams.py` | 新增 | 同 seed 命名子流、调用次序独立、纹理/几何随机源清单、合法 seed 边界；禁止隐式未设种子的随机来源 |
| `tests/unit/test_configuration.py`、`test_robot_descriptions.py` | 扩展 | 新配置默认/组合、两种机器人 TCP/组维度、默认 4/3 相机配置；两个脚本均在 `tests/unit/` |
| `tests/unit/test_task_state.py`、`test_task_support.py`、`test_task_definitions.py` | 扩展 | solved/失败/超时/未完成判据的区别，稳定时长、恢复后计数、能力声明与实现一致；均在 `tests/unit/` |
| `tests/recording_data/test_recording_branches.py` | 调整并拟改名 `test_recording_rewind.py` | 新段/旧段失效、旧视频仍能用于审计、有效轨迹不可重入废弃段；移除“保留所有可选分支”语义 |
| `tests/recording_data/test_dataset_transitions.py` | 扩展 | 动作/执行目标/观测/tick 对齐，跨 reset 分文件/身份，回溯后有效样本索引；HDF5 仍为可选功能 |
| `tests/recording_data/test_snapshot_isolation.py` | 扩展 | 普通和特权返回值不可反向修改历史；截断释放不会损坏共享存储的有效状态 |
| `tests/architecture/test_module_boundaries.py` | 扩展 | 一个 Env/World 时钟，公共入口不依赖 agent/deferred，Task 不复制控制/录制循环 |
| `tests/conftest.py` | 修改支持 | 更新替身世界、权限和控制 fixture；保留 mock/真实引擎边界，不能靠替身新增功能假装真实后端支持 |

### 5.2 真实 Genesis / Nyx 验证

以下真实运行在执行前全部接入报告与场景录像。非建场景的非法输入用例可以没有录像，但报告必须注明没有构建场景；不伪造视频。

| 测试脚本 | 操作 | 验证功能与证据 |
|---|---|---|
| `tests/integration/test_base_task_runtime.py` | 扩展 | 13 项基础 Task 经 make/reset/step/observe/render/close；严格 4/3 相机；有效 action、有实际时长的连续段、tick 0/中途回溯和旧未来拒绝 |
| `tests/integration/test_genesis_robot.py` | 扩展 | 两种机器人四种控制模式；实际位移、左右臂隔离、夹爪单位、FK/IK 残差、不可达命令不改变状态；不以“返回有限值”替代可达测试 |
| `tests/integration/test_genesis_seed_reset.py` | 扩展 | 从两机器人 A→B→A 扩到 13 项基础 Task；同配置同 seed 的内容指纹、初态数组、任务/RNG、纹理及原始 RGB；另测新进程重建 |
| `tests/integration/test_genesis_world_history.py` | 扩展 | 重力/接触及接触前中后 checkpoint 续跑、随机流、空间哈希、错 World 拒绝；底层 checkpoint 恢复机制与 Env 的有效历史权限分开验证 |
| `tests/integration/test_genesis_fem_ipc.py` | 扩展 | FEM/IPC 材料/接触/永久连接的完整恢复和续积分；覆盖截断后原生文件寿命，不用位置速度读回代替 checkpoint |
| `tests/integration/test_task_lifecycle.py` | 整合独立断言 | 将与全任务验收重合的生命周期断言映射到统一入口；保留 PBD、被动关节链等独有物理断言，不为抹掉缺证据数而删除测试 |
| `tests/integration/test_task_switch_runtime.py` | 扩展 | 同进程 ALOHA→Panda→ALOHA 的 close/make/reset、资源释放、engine 全局配置限制及新旧身份隔离 |
| `tests/integration/test_lifecycle_stability.py` | 新增 | G2+G5：反复 seed reset、提前终止/时限、运行阶段故障、输出失败、close 失败、重建；连续运行和 CPU/GPU/文件句柄/历史存储趋势 |
| `tests/integration/test_observation_rig.py` | 新增 | G6：4/3 路 camera ID、Nyx 实例、标定像素投影、腕部运动跟随、近景清晰度、home/操作区覆盖；每标准视角 PNG+连续视频 |
| `tests/integration/test_output_invariance.py` | 新增 | G7：同 seed/actions 下 RGB 开关、额外 observe/render 次数、录制/数据消费者开关，不改变物理轨迹/判据/RNG；比较原始帧和状态身份 |
| `tests/integration/test_task_goals.py` | 新增，判据阶段 | 13 Task 正例、近似但未成功的反例、失败及稳定时长；七项新判据需独立物理/拓扑证据，不能继承其他任务的成功标签 |
| `tests/packaging/test_installed_simulator.py` | 新增 | G8：非 editable wheel、仓库外 import/env_list/make/reset/step/render/close；基础资源和显式外部资源路径、缺失依赖错误；干净环境不依赖源码 PYTHONPATH |

### 5.3 G2 必须具体验证的边界

1. **时间**：正常 decimation、action 中途成功/失败、恰好时限、非整 action 时限；返回真实 tick 数和持续时间，不能始终填默认值。
2. **只读**：重复 observe/render/spec/特权 get，不改变时钟、物体、控制目标、Task 计数或随机流。
3. **输入错误**：NaN/Inf、形状/单位错误、越限和不可达；原子拒绝且原 Env 仍可用。
4. **故障提交边界**：在控制提交、World.advance、Task.update、snapshot、RGB 和输出 sink 分别注入错误；区分最后已保存 tick、未提交 tick 和已经推进但未输出的 action。
5. **故障恢复**：输出失败之后已提交物理状态不丢失；无权 rewind 的用户仍能新 reset 或 close；无法可靠恢复的原生引擎故障标 fatal，并要求新进程重建，不谎称所有故障都能 reset。
6. **reset/close**：非法 seed 在释放当前场景前拒绝；reset 构建失败不会释放活动 Env 限制后偷偷遗留场景；close 幂等；释放失败保留 faulted 身份和诊断。
7. **结束状态**：done 后 step 拒绝；普通 reset 开新 episode；恢复到 done 仍 done；恢复到其前面可以续跑且旧结束状态已失效。
8. **资源**：多次 reset 后只保留合同允许的历史。只维护当前 episode，内存不能因旧 episode 泄漏而持续增长。

mock 用于穷举异常点；真实引擎用于确认恢复与资源行为。两类证据都需要，不能相互替代。

## 6. 实施顺序、覆盖规模与通过门槛

| 阶段 | 开发工作 | 先验收什么 | 对应审计组 |
|---|---|---|---|
| P0 合同与证据 | 固定本文件接口、失效规则、模式坐标系；先改 RuntimeEvidence 和驱动 | 每项结果有 source/config/asset 身份、阶段错误和真实视频出口 | 所有组的前置条件 |
| P1 普通 API 与当前 episode 回溯 | make/env_list/reset 分离、StateRef、特权、历史截断、只读 observation | 无 GPU 合同；再做小型真实刚体/PBD/FEM checkpoint 与 G2 边界 | G1/G2/G3 |
| P2 控制与视觉 | EE/JOINT 模式、TCP/IK、严格 4/3 相机和近景 Nyx | 两机器人模式测试、标定/视角验收、输出不改变物理 | G1/G4/G6/G7 |
| P3 全 seed 与连续稳定性 | 所有随机入口审查、13 Task A→B→A、资源释放 | 13 Task 连续段、长时代表场景、G2 完整真实报告 | G2/G3/G5/G7 |
| P4 权限边界 | 管理方 reset、操作方无 reset、旧句柄失效 | 两种模式都拒绝 reset，跨 seed/跨 episode 引用均拒绝 | G1/G3 |
| P5 任务 solved 判据 | 完善七项判据并验证其他六项；不做 planner | 每项独立正反例、稳定时长及回溯一致性 | Task 语义完成门槛 |
| P6 独立安装与交付 | wheel、资源闭包、受影响测试最终回归、能力清单和全脚本清单 | 同一最终代码版本的可追溯证据；发布准确缺口 | G8 + 最终核对 |

**G2 不是可选项，不放到 planner 或 demo 之后。** P1 就开始；P3 补足真实运行与资源压力。

首轮可操作的运行规模（项目验收目标，不是普适行业认证数字）：

- **13 基础 Task**：每项先至少 5 秒连续物理时间；默认 dt 下 2,000 tick，默认 decimation 下 200 action。不是 200 帧拼接，也不是 5 秒墙钟时间。若真实任务提前终止，按真实结果结束，另用机制夹具完成长程稳定性检查。
- **seed**：13 Task 先以固定 A→B→A 组合重建，并在新进程重建 A；验证内容一致，不能强迫没有随机初态的任务在 A/B 之间人为不同。
- **控制矩阵**：两种机器人 × 四控制模式 × 两观察模式共 16 个代表组合；13 Task 都经默认支持组合运行，任务与公共控制耦合有风险时增加相应组合，不先盲目做全笛卡尔积。
- **长时代表**：刚体、被动关节链、PBD、自由 FEM 绳、带永久连接 FEM 各至少一项，候选 60 秒物理时间；先量化每 tick 存储增长与成本。若受资源约束不能完成，报告未完成，不能降低保存频率来通过。
- **反复生命周期**：每种物理机制先 10 次 reset/close 循环；预热后测 CPU/GPU/文件句柄与本地 native 存储，区分编译缓存、有效历史和泄漏。
- **恢复深度**：小型确定性机制用例遍历每个有效 tick；大场景至少包含初态、action 中间、接触前/接触中/接触后、较晚 tick 与终止边界。因 rewind 会删未来，遍历不同目标应重新构造相同前缀，不能依赖已作废点。
- **连续性容差**：按变量单位、后端、精度和机制预先记录。先验证恢复瞬间的完整状态，再比较相同后续动作的轨迹；不得只比较一个物体位置或发现失败后不断放宽阈值。

## 7. 每次真实 test run 要留下什么

沿用 `runs/test_results/`，新增本轮独立分区，例如：

```text
runs/test_results/simulator_contract_<run_id>/
├── README.md                 总结果、范围、未运行/失败项和逐视角链接
├── summary.json              每个 test node 的状态与覆盖矩阵
├── source_hashes.json        包括工作树未提交修改
├── source_snapshot.tar.gz
├── environment.json          GPU/驱动/Genesis/Nyx/IPC/精度/依赖版本
└── <case_id>/
    ├── report.json           各阶段输入、指标、断言和失败详情
    ├── junit.xml / run.log
    ├── resolved_config.json  robot/TCP/模式/seed 子流/4或3路相机参数
    ├── history_events.jsonl  保存/回溯/作废/reset/故障的身份和时钟
    ├── trajectories.npz      受测实际状态与动作；按大小分块
    ├── frames/<camera>.png   原始对照帧，不只看 MP4
    └── videos/<segment>/<camera>.mp4
```

- 单列 **physics time / wall time / frame count / encoded duration**；视频覆盖哪个 tick 范围一目了然，不把“一帧、播放器显示 0 秒”写成完整稳定性证据。
- 视频从实际测试 observe/render 取得；标准视角共用相同 tick/state/frame；编码时间映射清楚，不靠重复帧补足物理时长。
- 回溯点可能不是旧视频采样点：恢复后再渲染并开启新段。所有段注明 episode、起点、是否已被回溯撤销，不能拼成一条连续执行。
- 故障中断也保存最后可确认 tick、stage、stderr、退出码/信号及已完成视频。无 GPU、超时、skip、crash 均不能计入 pass。
- 数值/接触/材料诊断按物理机制提供，缺数据明示；细节读取不得偷偷触发 step。
- 执行前先检查测试是否具备上述证据能力。GPU 不可访问时，交付**实现后的、可直接执行的 CLI**及依赖/输出说明供用户运行；本计划不把尚未添加的 CLI 参数伪装成现有命令。

## 8. 最终交付与不能混淆的完成标准

1. 公共 API、默认视觉、tick 历史、特权截断和 G2 生命周期均有实现与实际证据；只跑通 reset/step 不够。
2. 同 seed 新 episode 的可复现性按随机源清单验收；Nyx 若尚有未控制采样，明确保留缺口。
3. 13 项基础环境可运行与 13 项任务 solved 判据完整分别报告；后者需要 P5 通过，不要求 planner 已能解题。
4. 禁止跨 episode 回溯；管理方 reset 后旧操作句柄及旧 StateRef 必须失效。
5. 每个公开特权数据项有精确含义和可用性；不把刚体 contacts 描述为完整 IPC/FEM 接触接口。
6. 保持 Genesis 唯一物理途径、Nyx + compact_lab 唯一标准视觉途径、一个活动 World 的现有范围；agent/网络 API、并行环境、跨版本 checkpoint、深度/分割和自动 assist 不默认为本轮已实现。
7. 实施后更新 `tests/README.md`、逐测试脚本文档、公共 simulator 用法和能力清单；运行 `scripts/inventory_sources.py` 更新全部模块脚本列表。历史审计/视频保留其原有事实和版本，不改写成新合同验收结果。

本文件是计划及合同；具体实现、通过项和未完成项以本轮实施报告为准。
