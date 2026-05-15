# 模块 A — World Builder（造世界）

> 在 Genesis 之上把一个具体任务的物理场景搭起来，并在每个 episode 开头把场景重置到 B 指定的初始拓扑配置。
>
> 下游所有模块通过 A 暴露的 **Scene 句柄** + **命名实体表** 访问场景里的任何对象。

---

## 1. 输入

**构造期（启动一次）**

- **TaskSpec**：任务 ID + 难度档 + 全局 seed
- **AssetRefs**：该任务用到的 URDF / MJCF / mesh / 纹理文件路径（机器人、桌面、props、绳子模板等）
- **SimConfig**：`n_envs`、`dt`、`substeps`、`device`（cuda/cpu）、solver 选择
- **CameraSpec**（来自 D 的构造期声明）：需要哪几个相机、各自的位姿/分辨率/FOV——A 在场景里把这些相机摆好

**Episode 边界（reset 时）**

- **初始配置 dict**（来自 B）：例如 `{"rope_endpoints": [...], "tile_arrangement": [...], "robot_home": [...]}`，一批 N 份（每个 env 一份）

**每步**：无（A 不在 step 路径上被调用）

---

## 2. 输出

**构造期**

- **Scene 句柄**：一个薄封装在 `gs.Scene` 之上的对象，带 `n_envs / device / dt` 元信息
- **命名实体表（Entity Manifest）**：字符串 ID → Genesis Entity 句柄，例如
  - `"robot"` → Franka 实体
  - `"rope_0"`, `"rope_1"`, … → DLO 实体
  - `"tile_grid"` → 刚体 group
  - `"cam_topdown"`, `"cam_wrist"` → 相机实体

**Reset 后**

- 物理状态已落到初始配置（机器人 home、物体在 initial pose、绳子按 B 指定的拓扑摆好）
- 渲染就绪，D 可以立即拿初帧

**每步**：无

---

## 3. 与其他模块的连接

- **被谁调**：F 在构造期调一次（建场景），在 reset 时调一次（落初始配置）
- **谁读它**：
  - **B** 通过 Scene 句柄读物体世界坐标算 reward / topology_state
  - **C** 通过 Entity Manifest 拿 `"robot"` 句柄做控制
  - **D** 通过 Entity Manifest 拿 `"cam_*"` 句柄做渲染
- **它读谁**：B 在 episode 开头产出"初始配置 dict"喂给 A
- **配置上游**：H（config + assets registry）提供 TaskSpec / AssetRefs / SimConfig

---

## 4. 内部逻辑概述

**构造期**

1. 全局 `gs.init(backend=...)`（整个进程只调一次）
2. 创建 `gs.Scene(options=...)`
3. 按 TaskSpec 选定的 scene template，逐个 `scene.add_entity(...)`：
  - 地面 / 桌面（固定刚体）
  - 机器人（C 提供 URDF 路径，A 负责 add 进 scene）
  - 任务 props（刚体方块 / DLO 绳 / hex 棋盘 …）
  - 相机（按 D 在构造期的 CameraSpec 摆好）
4. `scene.build(n_envs=N)` —— 一次性把 N 个并行场景编译成 GPU 计算图
5. 把所有 entity 句柄整理进 Entity Manifest，暴露给其它模块

**Reset 时**

1. 收到 B 传来的 N 份初始配置 dict
2. 对每个 env，按配置 `set_qpos` / 设刚体位置 / 设 DLO 顶点位置
3. 触发一次 zero-step（有些 solver 需要它来同步 state）
4. 不返回 obs（拼 obs 是 D 的事，由 F 在 reset 路径下一步调用 D）

**关键纪律**

- A **只摆场景**，不算 reward、不算 success、不发动作——那些归 B/C/D
- 所有"怎么摆"的随机性来自 B 传过来的 config，A 自己不掷骰子（这样保证 reset 可复现）
- `build` 完成后实体集合**冻结**：不能动态加减实体，只能改 state

**外部依赖**：仅 Genesis（`gs.init / gs.Scene / add_entity / build / set_qpos / 实体属性 setter`）。