# VLA 接入：设计与实现记录

| 项 | 值 |
|---|---|
| 状态 | 已实现。5 个 checkpoint 在 GPU 上跑通。第二批零样本评测（每模型 3 seed × 60 s）在 X-VLA 跑完 2 个 seed 时停止，已完成的都是 0/3；正式评测等 TopoGym 按 `index.html` 第 3 节改完后再跑 |
| 目标 | 只评测（零样本）：用各模型官方 checkpoint 和官方推理代码，不微调 |
| 范围 | 只改仓库根 `vla/`；分支 `dev/pingyue` |
| 相关文档 | [`../README.md`](../README.md)：安装、运行、配置、输出；[`index.html`](index.html)：交接报告（各模型能否发挥真实水平、差异与适配、TopoGym 可改进项、VLA 选择、结果） |
| 更新 | 2026-09-30 |

本文记录设计、接口约定、核对结论和变更历史。代码是接口的准确定义，本文只写代码里看不出的约定和原因。

## 1. 原则

1. **只改 `vla/`**。仓库其他目录一律不改；TopoGym 侧能解决的差别只记录（`index.html` 第 3 节）。
2. **复用 TopoGym**：环境循环、动作校验、观测、录像都用已有接口（第 6 节），不重写。
3. **简单**：协议只有 3 个数据类；Gym 侧一个通用适配器；每个模型一个子类；事实写在配置里，逻辑写在代码里；没有注册表和用不到的配置项。
4. **依赖隔离**：评测用 conda 环境 `topogym`，不装新包，传输只用标准库；每个模型一个 conda 环境 `vla-<model>`（`bash vla/setup.sh <target>`），都设 `PYTHONNOUSERSITE=1`。
5. **证据**：真实运行的产物放 `runs/test_results/<YYYYMMDD>_vla_<名称>/`（不进 git）；单测不能作为"模型能跑"的证据。

## 2. 架构与目录

```text
评测进程 · conda env topogym                              模型进程 · conda env vla-<model>
run_eval ─ Env ─ VLAAgent ─ Adapter ─ RemoteClient ⇄ TCP ⇄ serve ─ BaseVLA 子类 ─ 官方推理代码
```

```text
vla/
├── README.md · setup.sh · .gitignore（third_party/）
├── protocol.py            PolicySpec / Observation / ActionChunk，编解码（标准库 + numpy）
├── config.py              load_yaml：_base_ 继承 + ${} 引用（OmegaConf）
├── gym/                   评测进程；可 import topogym
│   ├── adapter.py         TopoGym 观测 / 动作 ⇄ 标准向量
│   ├── agent.py           VLAAgent：动作块队列、到位再换、逐臂跳过
│   ├── client.py          RemoteClient、LocalClient、PolicyError
│   ├── instructions.py    每个任务的英文指令与 VERSION
│   ├── report.py          输出目录 → Markdown 对比表
│   └── run_eval.py        入口
├── models/                模型进程；不 import topogym 和 vla.gym
│   ├── base.py            BaseVLA（camera_images：裁剪、缩放）
│   ├── serve.py           入口：加载模型配置 → TCP 服务
│   ├── dummy.py           HoldVLA：把当前状态重复成动作块
│   ├── droid.py           DROID 关节 7 约定（三个 DROID 模型共用）
│   ├── pi05/              model.py、gripper.py（openpi 的 ALOHA 夹爪连杆）
│   ├── groot/             model.py、franka.py（eef_9d 的正运动学）
│   ├── molmoact2/         model.py
│   └── xvla/              model.py、frames.py（每臂坐标换算）
├── configs/models/<robot>/  base.yaml + 一个 checkpoint 一个文件
├── configs/eval/            base.yaml + 一个任务一个文件
├── tests/                   不需要 GPU
└── docs/                    本文件、index.html（交接报告）
```

`LocalClient` 在评测进程内直接调用 `BaseVLA`，只用于测试和 `HoldVLA`。模型服务同一时间只服务一个连接。

## 3. 接口约定

**协议**（`protocol.py`，版本 3）：
- `PolicySpec` 由服务端连接后先发，内容来自模型配置的 `spec` 段：`name`、`embodiment`、`cameras`（顺序即模型图像槽的顺序）、`action_space`（`joint_abs` | `ee_abs`）、`control_hz`（训练数据频率）、`chunk_size`、`execute_steps`、`reach_tolerance_m`（只用于 `ee_abs`）。
- 发给模型的状态由动作空间决定（`STATE_KEY`）：`joint_abs` 发关节状态，`ee_abs` 发末端状态。TopoGym 的 JOINT 与 EE 观测模式二选一，评测按此设置观测模式。
- 线格式：`[4 字节大端 header 长度][JSON header][各数组原始字节]`，只用 `send_bytes` / `recv_bytes`，不用 pickle。消息：服务端 `spec`、`error`；客户端 `reset`（回 `ok`）、`infer`（回 `chunk`）。客户端等待回复不设时限，服务端退出时立即报 `PolicyError`。

**标准向量**（臂的顺序取 `action_spec["arms"]`，ALOHA 为 left、right）：

| 状态 / 动作空间 | 每臂布局 | ALOHA | Panda |
|---|---|---|---|
| `joint` / `joint_abs` | `[q₁ … qₙ, 开度]`，rad | 14 | 8 |
| `ee` / `ee_abs` | `[x, y, z, r₁ … r₆, 开度]`，TopoGym 世界系，m | 20 | 10 |

- `r₁…r₆` 为旋转矩阵前两列；转回时先 Gram–Schmidt 正交化。
- **开度** ∈ [0, 1]，1 = 全开。读数：`(原生值 − 空夹爪合上的位置) / (全开 − 空夹爪合上的位置)`，ALOHA 两指在 8.2 mm 处碰到（读 0），全开 37 mm；Panda 的 Robotiq 驱动角 0.8 rad 为 0、0 rad 为 1。命令：开度 > 0 时按同一比例换回原生值，部分张开的夹爪保持原开度；开度 0 命令到导轨末端（ALOHA 2 mm）并夹紧。
- **截断**：关节截到限位、开度截到 [0, 1]，按行计入 `clipped_actions`；末端位姿不截断。末端目标超出 TopoGym 的 IK 容差时按 RoboTwin 的做法逐臂跳过：先只让一条臂保持实测位姿，再让所有臂保持，计入 `skipped_actions`。
- **到位再换**（`reach_tolerance_m` > 0，只有 X-VLA）：同一目标重发到所有 TCP 都进入容差内，最多多发 10 个控制步。
- 相对 / 绝对、夹爪方向、坐标系等模型自己的约定都在模型子类里换算；图像先按 `model.image_aspect` 居中裁剪，再按 `model.image_hw` 缩放（`BaseVLA.camera_images`）。

## 4. 评测循环

- `topogym.make` 的参数由 spec 决定：控制模式、观测模式、`control_decimation = round(1 / (control_hz × physics_dt_s))`、`max_physics_steps = sim_seconds / physics_dt_s`；辅助抓持保持默认关闭；`env.*` 原样透传。
- 每个 seed：`env.reset(seed)`；`VLAAgent.reset` 用 Env 的 episode id；每个控制步 `agent.act` → `actor.step`；跟踪误差为"发出的臂目标 − 下一次实测"（关节 rad 或 TCP 位置 m）的各臂最大值；结束后按 `docs/vla_doc/vla_eval_demo.py` 的规则分类。
- 输出目录必须尚不存在。`results.jsonl` 每个 episode 一行；`summary.json` 含成功率、结果计数、PolicySpec、指令与版本、完整配置，以及开始运行时的 git commit 和是否有未提交改动（`git_dirty`）；`report.md` 一行汇总；开录像时每路相机一个 MP4。字段含义见 README 第 5 节。
- `outcome`：`success`、`task_failure`、`time_limit`、`unevaluated`、`unfinished`、`invalid_action`、`policy_error`、`env_error`。

## 5. 配置

规则和评测键见 README 第 4 节。要点：模型配置按机器人分目录，`_base_` 指向一个父文件；`${}` 在合并后解析；命令行 `key=value` 最后生效，键名必须已存在（`env.*` 除外）；端口在运行时指定，不写在配置里。指令在 `gym/instructions.py`，改动文本要递增 `VERSION`。

## 6. 复用的 TopoGym 接口（2026-09-30 在代码中核对）

| 接口 | 用法 |
|---|---|
| `topogym.make(task_id, **SimulatorConfig 字段)`，`with` 管理生命周期 | `variation_id`、`control_mode`、`observation_mode`、`physics_dt_s`、`control_decimation`、`max_physics_steps` |
| `env.reset(seed=)`、`env.interaction()` → `actor.step / observe / action_spec` | 评测进程是管理方，只把观测交给 agent |
| `action_spec`：`robot_id`、`arms`、`groups[arm]`（`arm_joint_names`、`joint_limits_rad`、`gripper_field`、`gripper_limits`、`fields`） | 驱动 Adapter，不另写机器人描述 |
| `obs["rgb"][相机]`（480×848×3 uint8）、`obs["robot"][arm]` | JOINT 模式有关节和手指位置；EE 模式有 TCP 位姿和手指位置 |
| `RecordingSession` + `env.add_frame_sink` + `env.sensor_frame()` | 录像，用法同 `topogym/recording/segment.py` |
| `docs/vla_doc/vla_eval_demo.py` | `GRIPPER_OPEN_CLOSED`、`classify` 等约定照搬（不 import docs 下的文件） |

## 7. 与训练机器人对应关系的核对结论

证据：`runs/test_results/20260930_vla_p4_checks`、`20260930_vla_round2_audit`、`20260930_vla_round3_gripper`、`20260930_vla_groot_eef9d`、`20260930_vla_round2_reach`。四个模型的调用方式都已逐项对照官方代码核对，一致。

1. **ALOHA 关节**：TopoGym ALOHA 取自 mujoco_menagerie `aloha.xml`，关节轴、连杆、限位与 vx300s 相同，起始姿态为 ACT 的 START_ARM_POSE，属于标准 ALOHA 约定。
2. **DROID 关节 7**：TopoGym 把 Robotiq 装在 Franka hand 坐标系上（相对法兰 −45°），DROID 装在法兰上，`q7_DROID = q7_TopoGym − π/4`（`models/droid.py`）。
3. **夹爪**：DROID 系三个模型用闭合度（1 = 闭合），π0.5 DROID 与 GR00T 在 0.5 处二值化；π0.5 ALOHA 的模型值是 Interbotix 连杆的电机角，按 openpi 的连杆模型换算（`models/pi05/gripper.py`）；X-VLA 在 g > 0.7 时闭合。
4. **GR00T eef_9d**：官方 `compute_eef_9d` 的欧拉角读法与训练数据不一致（在 TopoGym 起始姿态处相差 180°），改用法兰旋转矩阵；DROID 真实数据开环对比，执行的 8 步误差中位数低 20%（p = 0.004）。仿真中官方读法让每个 episode 37–53% 的动作行被关节限位截断，改用法兰旋转后 buzz_wire_3d seed 0 从 366 行降到 2 行（`runs/test_results/20260930_vla_groot_clipping_seed0`）。
5. **X-VLA 坐标**：输出 RoboTwin 世界系中 link6 的位姿（TCP 在其 x 方向 0.12 m），四元数按训练时的方式误读；TopoGym 两臂面对面、RoboTwin 两臂并排，所以每臂按自身底座换算，高度相对桌面（RoboTwin 底座高出桌面 4.2 cm）。proprio 用实测位姿（官方客户端从第二块起用上一步目标，到位时两者相差不超过 5 mm）。
6. **相机**：TopoGym 各相机 848×480（16:9）。DROID 训练画面 320×180，GR00T、MolmoAct2 按官方客户端缩到该尺寸，π0.5 自己加黑边缩到 224；ALOHA 训练画面为 4:3，两个 ALOHA 模型先居中裁成 640×480。相机位置和视角未调整。
7. **π0.5 ALOHA 的截断**：openpi 默认的 `pi05_aloha` + `pi05_base` 零样本输出有系统偏差。在 TopoGym 里，每个新动作块的第一个目标比实测关节多出 0.34–0.65 rad，方向固定（肩更负、肘更正、腕俯仰更负），逐块累积到关节限位；先移到 openpi 复位姿态也一样。在真实 ALOHA 数据（lerobot/aloha_static_coffee）上开环，首个目标平均偏离当前状态 0.18 rad，真人记录 0.015 rad。所以原因在模型，与 TopoGym 和适配无关（`runs/test_results/20260930_vla_pi05_aloha_clipping/README.md`）。
8. **吞吐**（独占 GPU）：每控制步墙钟 cast_coil decimation 8 为 0.35 s、24 为 1.0 s，buzz_wire_3d decimation 27 为 2.1 s；reset 17 s / 40 s；仿真显存 2.0 / 4.5 GB。模型显存 π0.5 约 12 GB、MolmoAct2 约 10 GB（bf16）、X-VLA 3.5 GB（GR00T 未单独测）。

## 8. 决定

| # | 问题 | 结论 |
|---|---|---|
| D1 | 辅助抓持 | 关闭（默认），整批统一 |
| D2 | 训练频率不能整除物理步 | `control_decimation` 取整，不做时间重采样；结果记录实际频率 |
| D3 | 指令 | 13 个任务的指令在 `gym/instructions.py`；cast_coil、blanket_flatten 两条为起草，全部待熟悉任务的人确认 |
| D4 | `execute_steps` | 用各模型官方示例值，写在模型配置里，评测配置可以覆盖 |
| D5 | 传输 | 标准库 TCP，一对一；TopoGym 环境不装新包 |
| D6 | 图像预处理 | 发渲染原图，裁剪、缩放在模型子类里按官方方式做 |
| D7 | PolicySpec 的来源 | 模型配置的 `spec` 段，子类不硬编码 |
| D8 | 起始姿态 | 用任务定义的姿态；按模型设置起始姿态列为 TopoGym 改进项 |

## 9. 验证

| 项 | 证据 |
|---|---|
| 单测（不需要 GPU） | `pytest vla/tests -q` |
| 链路冒烟：HoldVLA 本地与远程客户端结果一致，与 `vla_eval_demo.py` 一致 | `runs/test_results/20260930_vla_smoke_{hold,remote_hold,demo}_*` |
| 五个 checkpoint 的 GPU 冒烟 | `runs/test_results/20260930_vla_round2_gpu_checks/smoke_report.md` |
| 首批评测（修正前，3 seed × 30 s） | `runs/test_results/20260930_vla_batch1_*` |
| 第二批评测（全部修正后，3 seed × 60 s） | `runs/test_results/20260930_vla_p5_*`；`python -m vla.gym.report <目录>...` |

## 10. 之后

- **TopoGym 改进项**：见 `index.html` 第 3 节（起始关节角按模型设置、DROID 式外部相机等 6 项）。
- **微调**：要在 ALOHA 任务上测出真实水平需要微调。演示可由 `topogym/planning/` 的脚本化参考解在与评测相同的配置（CUDA、RGB、`control_decimation`、辅助抓持设置）下重新执行并渲染得到；现有 `solvability_proof/` 是 CPU、无 RGB、25 ms tick，不能直接用作训练数据。按 Adapter 的标准向量导出一份数据（同时写关节和 TCP），再转成各模型的训练格式。
- **多个仿真进程共用一个模型服务**：只需修改 `serve.py`。

## 11. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-29 | 计划定稿：只评测；只改 `vla/`；一个通用适配器；标准库 TCP；配置驱动的 `run_eval` |
| 2026-09-30 | 实施：协议、适配器、agent、评测循环、模型服务、四个模型的包装层与 `setup.sh`；HoldVLA 冒烟与远程冒烟通过；独立审查修复 4 项（`env_error` 记录原因、录像失败不中止后续 seed、覆盖项拼错报错、回复编码失败时回 `error`） |
| 2026-09-30 | X-VLA 改为 16.7 Hz（decimation 24）、执行整块 30 步：RoboTwin 每 15 个 1/250 s 仿真步存一帧；GR00T 只用当前帧，执行 8 步 |
| 2026-09-30 | 首批评测（3 seed × 30 s，修正前）：四个可运行模型都是 0/3 |
| 2026-09-30 | 第二轮：环境改为 conda；端口改为运行时参数；配置按机器人分目录并用 `_base_` 继承；指令移到 `gym/instructions.py`；新增 `report.md` 与 `vla.gym.report`；对照官方代码复查四个模型的调用 |
| 2026-09-30 | 第三轮：DROID 关节 7 按 45° 安装差换算；X-VLA 高度相对桌面、目标到位再换、IK 达不到时逐臂跳过；π0.5 ALOHA 夹爪按 openpi 连杆换算；ALOHA 两指碰到读作闭合；GR00T eef_9d 改用法兰旋转；删除旧的 uv 环境 |
| 2026-09-30 | 收尾：ALOHA 模型画面先居中裁成 4:3（commit 707ecd5）；最终审查修复（commit 7c00ed5）：状态由动作空间决定（协议版本 3），去掉未使用的关节 + 末端双状态路径；ALOHA 夹爪部分张开时保持原开度；截断由 agent 按行计数；`_base_` 只指向一个父文件；`serve` 固定监听 localhost；边界测试按完整模块名检查。删除实施前的设计文档 `DESIGN.md`，`index.html` 改为交接报告 |
| 2026-09-30 | 客户端先检查协议版本再读 spec 字段（旧版服务端报版本不一致，不再报字段错误）；`summary.json` 的 git commit 改为开始运行时读取，并记录 `git_dirty`。此前的 summary 在运行结束时读取 commit，运行期间有提交时会记成之后的 commit |
| 2026-09-30 | GR00T 截断查明：官方 eef_9d 读法下 37–53% 的动作行被关节限位截断；法兰旋转下 seed 0 只剩 2 行（关节 7 超出 0.036 rad，属于 45° 安装差留下的行程余量） |
| 2026-09-30 | 停止第二批评测（X-VLA 跑完 2 个 seed），正式评测等 TopoGym 改完。π0.5 ALOHA 截断查明：零样本输出有系统偏差，真实 ALOHA 数据上也一样，起始姿态不是原因 |
