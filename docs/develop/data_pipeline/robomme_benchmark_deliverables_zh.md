# Dev Log：RoboMME 作为 benchmark 的最终"产物"是什么

> 日期：2026-07-17
> 目的：换一个视角看 RoboMME —— 不看它的生成系统怎么搭（那部分见 `stable_il_generation_system_devlog_zh.md`），而是看它作为一个成品 benchmark **最终交付了哪些东西**。思考方式：如果我们只抓一个任务，把它做到"稳定且符合 RoboMME 的 benchmark 标准"，需要交付什么产物、工程上要支持哪些功能。
> 信息来源：robomme.github.io、`RoboMME/robomme_benchmark` 与 `RoboMME/robomme_policy_learning` 仓库的 README 和 `doc/`（`env_format.md`、`h5_data_format.md`）、HF 数据集卡片，抓取时间 2026-07-17。个别未公开写明的细节（如 demo 采集方式）会显式标注为推断。
> 行动计划：本文件是**现状分析**；据此制定的**可执行路线图**见 `robomme_pipeline_roadmap_zh.md`。

---

## 一句话总结

一个任务要进 RoboMME，不是"有个能跑通的 demo"，而是要同时交付**六层产物**：任务定义、环境接口合约、带 oracle 标注的数据集、固定协议的评测、可复现的基线、可分发的工程包。其中任何一层缺失，它都只是一个 demo，不是 benchmark 任务。

---

## 0. RoboMME 是什么（背景一段话）

RoboMME（ICML 2026 oral）是评测 VLA 模型在**长时程、依赖历史**的操作场景下的 benchmark。16 个任务分四个 suite（Counting / Permanence / Reference / Imitation，对应时间/空间/物体/程序性记忆），基于 ManiSkill（SAPIEN），Panda 机械臂 + 标准桌面。配套 14 个基于 π0.5 的记忆增强 VLA 变体、HF 数据集、leaderboard、CVPR 2026 challenge，以及 4 个镜像到真实机器人的任务。

对我们最相关的参照任务是 Imitation suite 里的 **RouteStick**（我们的 cable_routing 的"刚体化近亲"）。

---

## 1. 六层产物清单（单任务视角）

下面每一层都按"如果只做一个任务，这一层要交付什么"来写。

### 1.1 任务定义层：一个任务 = 一个可复现的 episode 空间

单任务交付物：

- 一个任务类（如 `src/robomme/robomme_env/RouteStick.py`）：场景搭建、资产、按 seed 的随机化、成功判定，全部内聚在一个文件里。
- **固定的 episode 划分**：train 100 / val 50 / test 50，每个 episode 由固定 seed 完全确定。"第 37 号测试 episode"在任何人的机器上都是同一个场景布局。
- 每个 episode 的 `setup` 元数据：`seed`、`difficulty`、`task_goal`（一组可用的语言指令，不止一句）、相机内参。

关键点：**episode 不是"随机 reset 一次"，而是一个有编号、可指名调用的对象**（`make_env_for_episode(episode_idx)`）。这是复现、评测、debug 的共同地基。

### 1.2 环境接口层：一份公开的 env contract

RoboMME 专门写了 `doc/env_format.md`，把接口当成对外承诺来维护：

- **Gym 风格 API**：`obs, info = env.reset()`；`obs, reward, terminated, truncated, info = env.step(action)`。
- **观测字典**（所有值是 list，`obs[key][-1]` 取当前帧，为的是支持视频条件化和 waypoint 动作的中间帧）：
  - 视觉：`front_rgb` / `wrist_rgb`（uint8, 256×256×3），可选 depth（int16, 毫米）；
  - 本体：`joint_state`(7)、`eef_state`(xyz+rpy)、`gripper_state`、`is_gripper_close`；
  - 相机内外参：可选 flag 开启。
- **四种动作空间**，同一个环境同时支持：`joint_angle` / `ee_pose` / `waypoint` / `multi_choice`。全部绝对量，gripper 约定 -1 关 1 开。`waypoint` 是"给末端关键帧、环境内部执行"，即把 motion planner 内置到环境里作为一种合法接口。
- **info 字典**：`task_goal`、oracle 子目标（`simple_subgoal_online` / `grounded_subgoal_online`）、`status ∈ {success, fail, timeout, ongoing, error}`。
- **公开的坐标系文档**：右手系、+x 朝物体、桌面 z=0、Panda 基座固定 (-0.615, 0, 0)、RPY 做时间连续 unwrap。

关键点：**成功/失败/超时/物理异常是接口的一部分（status 枚举），而不是 log 里的一行字**。`error` 是显式状态——物理崩了也算一种可上报的结果，不是 segfault。

### 1.3 数据产物层：带 oracle 标注的标准化数据集

单任务交付物：100 条 demonstrations，HDF5，schema 公开在 `doc/h5_data_format.md`：

```text
episode_<N>/
├── setup/          seed、difficulty、task_goal 列表、相机内参、multi-choice 选项
└── timestep_<K>/
    ├── obs/        front/wrist rgb+depth、joint/eef/gripper state、相机外参
    ├── action/     joint_action(8) + eef_action(7) + waypoint_action(7) + choice_action
    └── info/       simple_subgoal、grounded_subgoal（各带 online 版）、
                    is_video_demo、is_subgoal_boundary、is_completed
```

值得抄的三个设计：

1. **每个 timestep 同时存四种动作表示**。数据采一次，joint-space / ee-space / waypoint-space 的 policy 都能训，不用重采。
2. **oracle 子目标是数据的一等公民**。每帧带自然语言子目标（simple = 目标描述，grounded = 带空间指代），外加 `is_subgoal_boundary` 标记子任务边界。这直接支撑了他们的 symbolic memory 基线。demo 采集方式论文页没写明，但仓库里有 `subgoal_planner_func.py`，加上每帧 oracle 标注的存在，**基本可以断定是脚本化 planner 生成而非人工遥操**（推断）。
3. **配套校验工具**：`scripts/dataset_replay.py` 可以把下载的 H5 在环境里回放验证。数据不是"发出去就完了"，而是带自证工具。

分发形态：HF 上 `.h5.tar.xz`，56.4 GB，Apache 2.0，另提供 Pickle / LeRobot / TF 三种转换格式。

### 1.4 评测产物层：固定协议 + 可断点续跑的基础设施

- **协议**：test split 50 个固定 seed 的 episode，`scripts/evaluation.py` 统一入口，按 `status` 计成功率。
- **policy 与环境解耦**：评测时 policy 作为独立 server，通过 **WebSocket** 与模拟器通信。好处：policy 的 Python/CUDA 环境和模拟器环境互不污染，也天然支持 challenge 的黑盒提交（`challenge_interface/`）。
- **可恢复**：`progress.json` 记录进度，评测中断可续跑；结果按 `runs/evaluation/<policy>/ckpt*/seed*/` 目录规范落盘。
- **对照上限**：leaderboard 提供逐任务成绩，且有**人类操作者成绩（90.5%）**作为上界参照。

关键点：评测不是"跑个脚本看打印"，而是一套**别人能复跑、能提交、能对表**的流程。

### 1.5 基线与复现层：证明这个 benchmark 可学

单任务不能只有环境和数据，还要证明"照着我给的东西能训出东西"：

- policy_learning 仓库提供 π0.5 baseline + 14 个记忆变体，hydra 配置、`norm_stats.json` 归一化统计、预计算的 SigLIP 特征全部随包发布。
- 所有 checkpoint 挂在 HF，git-lfs 可拉。
- `eval.sh` 一键起 policy server + 模拟器（tmux 管理），从训练到 leaderboard 数字闭环。

关键点：**基线成绩是任务定义的一部分**。"这个任务 π0.5 只能做到 X%，人类 90%"本身就是任务难度的规格说明。

### 1.6 分发与工程层：让外人两小时内跑起来

- Docker（CUDA + Vulkan 配好）+ uv 两条安装路径；headless 渲染有 fallback 环境变量。
- `scripts/run_example.py` 一条命令出一个 rollout 视频——最小可验证入口。
- 文档三件套：`env_format.md`（接口）、`h5_data_format.md`（数据）、`docker_installation.md`（部署）。
- 网站 + 交互式 HF Space demo + 论文附录任务规格。

---

## 2. 反过来读：一个"符合 benchmark 标准"的任务的验收单

把上面六层压缩成一张验收单。一个任务要称得上 benchmark-ready，需要全部打勾：


| #   | 验收项                 | RoboMME 的实现                                         |
| --- | ------------------- | --------------------------------------------------- |
| 1   | episode 可指名复现       | `make_env_for_episode(idx)`，train/val/test 固定 seed  |
| 2   | 接口有书面合约             | `env_format.md`：obs/action/info/坐标系全部成文             |
| 3   | 结果是枚举不是日志           | `status ∈ {success, fail, timeout, ongoing, error}` |
| 4   | 多动作空间               | joint / ee_pose / waypoint / multi_choice 同环境支持     |
| 5   | 数据集 schema 公开且可回放校验 | `h5_data_format.md` + `dataset_replay.py`           |
| 6   | 数据带 oracle 结构标注     | 每帧 subgoal + 边界 flag + 完成 flag                      |
| 7   | 评测协议固定且可续跑          | 50 episodes、WebSocket policy server、progress.json   |
| 8   | 有基线成绩和上界参照          | π0.5 系列 + 人类 90.5%                                  |
| 9   | 外人可低成本复跑            | Docker、一键示例、headless fallback                       |
| 10  | 语言指令是环境输出           | `task_goal` 由 info 给出，且一个任务多句指令                     |


---

## 3. 对 TopoGym 单任务意味着什么

以 cable_routing（对标 RouteStick）为例，逐层对照现状（现状参考 `stable_il_generation_system_devlog_zh.md` 的规划）：

### 已经在路上的

- **第 1 层（episode 空间）**：`EpisodeSpec = task_id + preset_id + seed + variant` 的设计和 RoboMME 的 episode 编号思想一致。缺的是把它固化成 train/val/test 三个 seed 列表并写死进 repo。
- **第 6 项（oracle 标注）**：这是我们的**天然优势**。`EpisodePlan` 的 subgoal 序列（`grasp_handle` → `wrap_P1_outer` → …）就是 RoboMME 花力气造出来的 `grounded_subgoal` + `is_subgoal_boundary`。我们的 planner 输出只要在录制时逐帧落盘，就直接得到同等级标注。
- **第 3 项（结果枚举）**：`EpisodeResult` 的 success/failure_reason 已是雏形；PBD soft abort 对应的正是 RoboMME 的 `error` 状态——**把 Genesis 崩溃收编为一种合法评测结果**，而不是流程事故。

### 差距最大的

1. **第 2 层：没有 env contract**。我们有 runner，但没有一份"obs 字典里有什么、动作是什么格式、坐标系怎么定义"的对外文档 + Gym 风格接口。`genesis_world_coordinates_zh.md` 覆盖了坐标系一角，但 obs/action 合约完全没有。
2. **第 5 层：没有数据 schema**。当前录制产物是视频 + result JSON，不是逐帧 obs/action 的结构化数据。RoboMME 的启示是 schema 要先于数据定：即使暂时只采 10 条，也应该按"setup + timestep/{obs,action,info}"的结构落盘。
3. **第 4 项：动作空间单一**。我们只有隐式的 dense ee 轨迹。RoboMME 的 `waypoint` 动作类型和我们 planner 的输出天然同构——`ee_pose_dense` + `waypoint_sparse` 双导出（前一篇 dev-log 的 G 层建议）应升级为正式动作空间定义。
4. **第 7/8 层：完全没有**。这是合理的——评测协议和基线属于"任务稳定之后"的产物。但要意识到：**没有这两层之前，我们做的是环境，不是 benchmark**。

### 一个务实的排序

对单个任务（cable_routing）而言，通往 benchmark-ready 的最短路径是：

```text
① 固化 seed 列表（train/val/test），episode 可指名复现     ← 几乎零成本
② 写 env contract 文档（obs/action/status/坐标系）          ← 写作成本为主
③ 录制时按 RoboMME 式 H5 schema 落盘（含 planner subgoal） ← 中等工程量
④ dataset_replay 式的回放自校验                             ← 依赖 ③
⑤ 评测脚本 + 成功率统计（先不做 policy server 解耦）        ← 依赖 ①②
⑥ 基线训练（IL on 我们自己的数据）                          ← 最后，且依赖全部
```

①②③ 不依赖 cable_routing 的物理问题被彻底解决——schema 和合约可以先在 swap/maze 这类已稳定的刚体任务上立起来，cable_routing 后接入。

---

## 3.5 代码现状逐层核对（基于实际代码，2026-07-18）

第 3 节的对照是**基于规划文档**写的。这一节把同一张验收单压到**当前 repo 里真实存在的类和文件**上，逐项给出证据和判定（✅ 已具备 / 🟡 有雏形但形态不对 / ❌ 缺失），个别地方会修正第 3 节偏乐观或偏悲观的说法。

| # | 验收项 | 现状 | 证据（实际代码） | 判定 |
| --- | --- | --- | --- | --- |
| 1 | episode 可指名复现 | `EpisodeKey(task_id, preset_id, seed, variant_id)` + `stable_id()` 已是稳定身份 | `topogym/generation/episode_spec.py` | 🟡 身份对象已就位，但 **seed 尚未真正随机化**（`swap_generator.py` 注释明说"seed reserved for future randomization"），且 repo 里**没有固化的 train/val/test seed 列表**，也没有 `make_env_for_episode(idx)` 入口 |
| 2 | 接口有书面合约 | 无 `env_format.md` 类文档 | `docs/develop/` 下只有交互/任务合约（如 `collision_based_il_contract_zh.md`），没有 obs/action/status/坐标系的统一对外合约 | ❌ |
| 3 | 结果是枚举不是日志 | `EpisodeResult.success: bool + failure_reason: str`；MDP 用 `terminated/truncated` | `episode_spec.py`（EpisodeResult）、`envs/swap_mdp.py` | 🟡 有结构化结果，但**不是 `status ∈ {success, fail, timeout, ongoing, error}` 枚举**；物理崩溃（PBD soft abort）尚未收编为显式 `error` 状态 |
| 4 | 多动作空间 | MDP 动作空间只有 `[dx, dy, dz, gripper]` 相对增量 | `envs/swap_mdp.py`（`action_space = Box(-1,1,(4,))`，`ee_target = hand + delta`） | 🟡 waypoint 的原料已在 `planning/waypoint.py`（`WaypointPlan/WaypointTarget`）里，但**没有作为 RL/评测动作空间暴露**；RoboMME 的 joint/ee_pose/waypoint/multi_choice 四选一、且全为**绝对量**，我们目前是单一相对增量 |
| 5 | 数据集 schema 公开且可回放校验 | 只有视频录制，无逐帧结构化数据 | `utils/recording.py` 只产 mp4；repo 无 `h5py`/HDF5 落盘、无 schema 文档、无 `dataset_replay` | ❌ |
| 6 | 数据带 oracle 结构标注 | `PlannedSubgoal`（subgoal_id/kind/target/label）+ `EpisodePlan.subgoals` 已存在 | `planning/subgoal.py`、`planning/waypoint.py` | 🟡 结构是**天然优势**且已在内存里生成，但因为第 5 层缺失，**没有逐帧落盘进数据集**，`is_subgoal_boundary` / `is_completed` 这类帧级 flag 也还没有 |
| 7 | 评测协议固定且可续跑 | 无 | 无 `evaluation.py` / `progress.json` / policy server | ❌ |
| 8 | 有基线成绩和上界参照 | 无 | — | ❌ |
| 9 | 外人可低成本复跑 | 有 `configs/` + `bash_scripts/` + prototype 入口，但无 Docker、无"一条命令出 rollout"的最小入口文档 | `configs/`、`bash_scripts/`、`demos/` | 🟡 |
| 10 | 语言指令是环境输出 | `task_goal` 存在于 spec 侧参数，但不由 `env.step()` 的 `info` 稳定输出 | `swap_generator.py`（variant.parameters 里有 goal/oracle），`swap_mdp._build_info` 的 info 里**没有 task_goal** | 🟡 |

### 相对第 3 节需要修正的两点

1. **我们其实已经有 Gym 风格接口，不是"只有 runner"**。`topogym/envs/{swap,onestroke,maze_wall_removal,untangle}_mdp.py` 都是完整的 `gymnasium.Env`（`reset`/`step`/`Box` 空间），还带了 `RslRlSwapAdapter` 这类 RL 适配器。所以第 2 层真正缺的**不是"没有接口"，而是"接口形态不对且没写成合约"**：
   - obs 是**扁平 Box 向量**（hand/gripper/block 位置拼接），不是 RoboMME 的 `{front_rgb, wrist_rgb, joint_state, eef_state, gripper_state, ...}` 字典；
   - action 是**相对 ee 增量**，不是绝对量的四种动作空间；
   - 只覆盖 4/7 个任务（`stacked_plate`/`cable_routing`/`peeling` 无 `*_mdp.py`）。
2. **第 3、4 项比第 3 节说的更接近"雏形"而非"在路上"**：结果对象和 waypoint 原料都在，但都停在"数据结构存在"这一步，还没接到对外的 status 枚举 / 动作空间定义上。真正的工作量是**把已有内存对象接到合约化的输出上**，而不是从零造。

### 结论（代码视角）

按第 3 节 ①→⑥ 的排序，当前代码把 ① 的一半（身份对象）和 ⑥ 的一半（subgoal 结构）做出来了，其余基本是空白。**离 benchmark 最近的两块低成本收益**是：把 seed 固化成 split 列表并让 generator 真正按 seed 随机化（补齐 ①），以及把 `PlannedSubgoal` + obs/action 按一个先定死的 H5 schema 逐帧落盘（同时启动 ③ 和 ⑥）——后者不依赖 RL/评测，可以先在 swap/maze 上立起来。

---

## 4. 两条容易被忽略的教训

1. **RoboMME 明说了"并行环境目前只服务 IL，RL 并行是 planned"**。一个 ICML oral 级别的 benchmark 也是先把单环境 + IL 数据这条线做扎实才谈 RL 并行。我们不必为"以后要 RL"提前给环境生成系统加复杂度。
2. **产物的一半是文档和工具，不是代码**。RoboMME 的 `doc/` 三件套、dataset_replay、run_example、progress.json，单看每个都不"高级"，但它们共同构成"外人可用"这个 benchmark 的本质属性。我们内部 dev-log 已经很多，缺的是**面向使用者的合约文档**——这类文档一旦写下，反过来会约束代码不乱变。

---

## 5. 结论

RoboMME 的最终产物不是 16 个任务，而是一个**六层交付模板**：可指名的 episode 空间、成文的接口合约、带 oracle 标注且可自校验的数据集、固定且可续跑的评测协议、基线 + 人类上界、两小时可复跑的工程包。

对 TopoGym："把一个任务做稳定"只覆盖了第 1 层和第 3 项的一半。下一阶段如果目标是 benchmark 而非 demo 集，应该按第 3 节的 ①→⑥ 顺序，先在已稳定的刚体任务上把 schema/合约/评测立起来，让 cable_routing 这类难任务做完时有现成的"模具"可以灌入。