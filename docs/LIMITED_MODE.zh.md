> **历史设计文档**：已由 [PROTOCOL.md](PROTOCOL.md)（v1.0）和 [LIMITED_MODE_PROTOCOL.md](LIMITED_MODE_PROTOCOL.md)（`eai-standard/2.1`）取代，仅作留档。limited 模式现称 standard 模式。

# Limited 模式（"机器人即服务"）是怎么做的

英文设计与协议：`LIMITED_MODE.md`、`LIMITED_MODE_PROTOCOL.md`（协议版本 `rcb-limited/2.0`，v2 设计见 `LIMITED_MODE_V2_DESIGN.zh.md`）。
第一个实例：`tasks/robotwin_2_0_stack_blocks_two-standard/`，与 unlimited 版共用同一个冻结实例（seed 60417）。

## 1. 两种模式的区别
| | unlimited（现有任务） | limited |
|---|---|---|
| 仿真器在哪 | 和 agent 同一容器，agent 是 root，什么都能改 | 独立的 `sim` sidecar 容器，agent 打不开 |
| reset | 无限 | **没有**：一次 trial = 一个 episode，像真机一样 |
| 能看到什么 | 物体位姿、`check_success`、场景文件、规划原语 | 只有相机 RGB（头部/正面/左右腕）+ 本体（关节、夹爪、末端位姿） |
| 动作 | 直接调 RoboTwin 原语 / 低层 step | `qpos`(14) 或 `ee`(16)，即 RoboTwin 策略评测的原生 `take_action` |
| 步数 | 无限制 | 无限制，只受 agent 墙钟预算限制；步数作为成本上报 |
| 交付物 | agent 自己保存 `trajectory.npz` | **同样是 `(T,34)` 轨迹**，但由服务端录制，agent 碰不到 |
| verifier | 在 agent 容器里回放 | 在**独立沙箱**里读 sidecar 的产物 |

## 2. Harbor 提供的四块积木（已验证，Harbor 0.23）
1. **sidecar 服务**：`environment/docker-compose.yaml` 里除 `main` 之外的服务都是 sidecar，文件系统/进程与 agent 隔离，只能走网络。
   GPU 预留写在 `sim` 服务上。
2. **网络策略**：`[agent] network_mode = "no-network" | "allowlist"`。开启出口控制时 Harbor 把 main 和 sidecar 放进同一个网络
   命名空间，服务地址变成 `localhost:8000`；`public` 时是 `http://sim:8000`。客户端两个都试。
3. **sidecar 产物 + collect 钩子**：`artifacts = [{ source = "/data/final.json", service = "sim" }, ...]` 在 main 停掉之后从
   sidecar 拷出；`[[verifier.collect]]` 先在 sidecar 里执行一条命令做快照。
4. **独立 verifier**：`[verifier] environment_mode = "separate"` + `tests/Dockerfile`（镜像里自带 `/tests/test.sh`），
   产物按原路径上传进去（`/data/...`）。

PoC（`docs/limited_mode/gym-sidecar-poc/`）在 `public` 与 `no-network` 下 oracle 都得 1，并实测：agent 容器里看不到 sidecar 的
`/data`、`/srv` 和进程；未公开端点返回 501/404；第 3 次 reset 被服务端 429 拒绝并记入日志。

## 3. 服务端（`environment/sim/server.py`）
- 基于现有 `rcb_traj.Session` 建场景（seed、instance.json 只在 sidecar 里），启动即 `record_start()`，整个 episode 全程录制。
- 接口只有四个：`GET /spec`（动作类型、维度、关节限位、相机名单、预算）、`POST /observe`（`seconds=0` 取当前帧免费；`seconds>0` 保持上一指令并观看一段时间，返回视频）、`POST /submit`（一批低层动作：`joint_position` 按 `dt` 以 250 Hz 线性插值流式执行，或 `ee_pose` 逐行 CuRobo 规划；返回执行视频/帧/本体感知）、`GET /status`。返回体是二进制 RCB1 帧（mp4 / 原始数组），不用 base64，也不会自动进入模型上下文；agent 用 `rcb_client.py` 的 `submit()/get_obs()` 拿到 `Result` 对象后自行决定存哪里、看哪几帧。
  **严格 gym 契约：模型对世界的一切认识只来自 obs。** 相机标定（RoboTwin `get_obs()` 自带的每相机 `intrinsic_cv / extrinsic_cv / cam2world_gl`）
  放在 obs 的 `cameras` 字段里而不是 spec 里；任务可用 `RCB_OBS_CALIBRATION=0` 关掉，得到纯像素版本。
  其它一律 404（包括 `/reset`）。
- （v1 的 `/step` 已退役，以下为 v1 实现细节，v2 中 `joint_position` 直接写驱动目标、`ee_pose` 走 CuRobo）`/step` 直接调用 RoboTwin 的 `take_action(action, action_type)`：
  - `qpos`：14 维 = 左臂 6 关节 + 左夹爪 + 右臂 6 关节 + 右夹爪（弧度；夹爪 0 闭 1 开），服务端做时间最优插值再走物理；
  - `ee`：16 维 = 左 xyz + wxyz 四元数 + 夹爪 + 右同样，世界系；CuRobo 只对桌面避障（不知道物体），某臂规划失败则原地不动并在
    `plan` 字段里报告。`ee` 目标与观测里的 `endpose` 同一约定（ALOHA 上偏移为 0），观测到的位姿可以直接当目标。
- 校验：维度、NaN、关节限位（URDF 的 ±10 rad 占位限位按 RoboTwin 规则报 ±π）、夹爪 [0,1]、四元数单位模 → 否则 400，不执行物理。
- 每步之后调用任务自己的 `check_success()`；第一次成功即结束（`done=true, reason="success"`），否则等 collect 钩子发 SIGUSR1 结束
  （`reason="timeout"`）。
- **finalize**（成功或收到信号后，后台线程持锁执行）：`record_stop()` 得到 `(T,34)` 轨迹 → 存 `/data/trajectory.npz` →
  从冻结实例**重新回放**得到 `replay_success` 与终态哈希比对 `deterministic` → 六视角 `replay.mp4`（帧数上限约 600）→
  写 `/data/final.json`（`finalized: true`）。所有事件追加到 `/data/episode.jsonl`。
- 启动完成后写 `/data/server.pid`，collect 钩子据此发信号。

## 4. 任务目录怎么组织
```
tasks/robotwin_2_0_<task>-limited/
  environment/Dockerfile           # agent 镜像：python:3.12-slim + requests/numpy/pillow + rcb_client.py，无仿真器、无 RoboTwin 代码
  environment/docker-compose.yaml  # sim: rcb-robotwin 镜像，挂载 ./sim:/srv:ro，command python /srv/server.py，GPU 预留；不要写 expose/ports
  environment/sim/{server.py, rcb_traj.py, instance.json}
  environment/rcb_client.py        # 同 docs/limited_mode/client_v1.py
  tests/{Dockerfile, test.sh, grade.py}  # 独立 verifier：success = live ∧ replay_success ∧ deterministic；拷贝视频/轨迹到 /logs/verifier
  solution/{solve.sh, oracle_replay.py, oracle_qpos.npy}  # oracle：unlimited 专家轨迹每 25 步取一行当 qpos 动作重放
  task.toml                        # artifacts 来自 service="sim"；[[verifier.collect]] 发信号并等 finalized；[verifier] separate + no-network
```
reward.json 字段与 unlimited 版一致（`success / n_actions / sim_steps / video_rendered` …），两种模式可直接对比。

## 5. 踩过的坑
- collect 钩子里 `pkill -f server.py` 会匹配到钩子自己的 shell，先把自己杀了（退出码 138 = SIGUSR1）。改成服务端写 pid 文件，
  钩子先等 pid 文件出现再 `kill -USR1 $(cat /data/server.pid)`，然后轮询 `final.json` 的 `finalized`。
- 成功触发的 finalize 与信号触发的 finalize 可能同时启动，第二个会用空录制覆盖轨迹 → 加 `finalizing` 标志。
- sidecar 上写 `expose:` 会与出口控制的共享网络命名空间冲突（`conflicting options: port exposing and the container type network mode`）。
- 这个版本的 Harbor 用 `environment_mode="separate"` 时要求 `tests/Dockerfile`。
- `harbor run -o` 用绝对路径，否则 compose cp 会先在错误的相对目录失败再回退（能用但日志很吵）。
- oracle 的 qpos 重放比原始逐步 drive 目标多耗物理步（17k vs 4.3k），因为每个 chunk 都做一次 TOPP；finalize 里的回放 + 渲染约 4-5 分钟，
  collect 钩子超时设 600 s。

## 6. 结果（stack_blocks_two，seed 60417，Codex + GPT-6 Astra）
oracle 1（161 个 qpos 动作）、nop 0；GPT-6：成功，17 个 `ee` 动作、3820 物理步、agent 261 s、724k/5k tokens。
它用头部相机 RGB 加上 obs 里自带的相机内参/外参，把方块像素坐标反投影到桌面（桌面高度已知）得到世界坐标，自顶向下抓取；左臂规划失败一次后改用右臂把红块搬到中央，再用左臂堆叠。
对比 unlimited 版（145 s、20 步、359k/2k）：约翻倍的时间和 token，但仍然成功。

## 7. 把别的任务改成 limited
服务端是通用的：compose 里改 `RCB_TASK`、换 `instance.json`、改 task.toml 的名字/描述、准备 oracle 的 `oracle_qpos.npy`
（从该任务的 unlimited oracle 轨迹抽样）即可。待做：4 个难任务的 limited 版。
