# ring_transfer —— docx 2.6「绳圈从柱 A 转移到柱 B」设计契约与落地记录

日期：2026-08-24。类别 `routing`。代码：`topogym/tasks/routing/ring_transfer.py`（场景）、
`_ring_transfer_geometry.py`（布局预算）、`topogym/planning/ring_transfer_planner.py`（oracle）、
`topogym/verification/ring_transfer_verifier.py`（判定）、`demos/routing/ring_transfer_physical_demo.py`
（demo）、`tests/check_ring_transfer_geometry.py`（离线门）、`tests/ring_transfer_spike.py`（无臂 spike）。
配置：`configs/task_configs/ring_transfer_topogym_tabletop_v1.yaml`。

## 1. 任务定义

闭合弹性环平铺在桌面、套在柱 A 上；终态环套在柱 B 上、不再围住 A。判定量是环中心线绕每根柱轴的
**绕数**（俯视投影，闭合曲线的转角和 / 2π，整数），enclosure 是绕数为 1 的柱子集：{A} → {B}。
路径证据单独记录：每根柱的挡头顶是否被越过（`top_crossed`）、环到柱面的最小间隙（穿模监视）。

变体轴从一开始就在数据结构里：`posts` 是列表，`ring.enclosure` / `goal.enclosure` 是子集，判定器输出
每柱绕数向量，oracle 吃 `layout.crossings()` 给出的跨越序列。本轮只实现单柱出生形与 A→B 一条序列。

## 2. 场景（第二版，2026-08-25）

- 两根工业走线柱（柱身 r=0.016 高 0.100、底座锥 r=0.030、**碰撞挡头** r=0.026 厚 0.008；深灰柱身、
  黑色底座与挡头），A 在 (−0.100, 0)，B 在 (+0.120, 0)。第一版（r 0.012、高 0.085、柱距 0.14、
  周长 0.53）是 transfer 路线的几何，用户看 demo 后要求环更小、柱距更远、柱子更拟真。
- 闭合环：`world/closed_band.py` 周期管，周长 0.40、半宽 0.045、管半径 0.004，出生为围住 A 的跑道形、
  长轴指向 −x。FEM+IPC，`rest_shape=spawn`（闭合环上 straight 不可用）。
- 默认 oracle 是 `carry`（§3b）；`transfer`（§3）在这组几何下拉伸比 1.96，不可用，离线门只报告。
- 挡头是碰撞体，与 cable_routing 的装饰顶盖不同：无挡头时远端帽抬高后拉线与桌面成约 40°，A 处缠绕在
  tan(角) > μ=0.3 时沿柱身上滑并越过柱顶（实测平移段第 60 步脱离）。gateway 因此是挡头顶。

## 3. 单夹爪为什么必须分两段、以及为什么要钩

1. **单点捏住的环套不进任何柱子。** 环被拉紧后在 A 处收拢成 2(r_post + r_tube)=0.032 宽的双股，
   闭合曲线只在 A 处有绕数；离线门第一版量得绳股离 B 轴 12.5 mm < 16 mm。
2. **悬空的环也套不进柱子。** 单手提起的环竖直悬挂，俯视投影是一条 70 mm 线段、面积为零，而围住 B
   要求投影包住 B。实测：环脱离 A 后搬到 B 上方放下，B 绕数 0。
3. 因此 on-phase 用**两指伸进远端帽张开 0.070 钩住**（两条 follow band），A 柱当第二只手把环撑成
   梯形（A 处 0.032 → 远端 0.070），B 处绳股间距 0.062 ≥ 0.044。路径：绕 A 平转（z=0.03，经 +y 到
   55°）→ 抬到 0.155 → 平移到 B 远侧 x=0.116 上方 → 下放 → 释放。平移段全程绷紧（拉伸比 1.05~1.15）。
4. off-phase 捏住贴着 A 的帽，抬到挡头顶 +0.024，向 B 平移 0.060 滑过挡头，释放。

离线门检查的全部不等式与路径采样见 `tests/check_ring_transfer_geometry.py` 文档字符串。

## 3b. 第二条 oracle：搬运套索（`carry`，2026-08-25，用户提议）

「悬空的环套不进柱子」只对**从上方放下**成立。从**侧面**推则不同：两指张开钩住环时，悬挂环的底部
U 也有 70 mm 宽；把 U 底推向柱身，两股绳被柱子分到两侧，手再越过柱子，环就套住了柱子（套马索），
放低松手即可。步骤：钩住 A 与 B 之间那半个帽的两肩（`lift_left/right` band）→ 抬到指尖 0.235
（悬挂深度 (0.53 − 2×0.07)/2 = 0.195，U 底在柱身中段 0.040）→ 到 B 近侧 0.05 处 → 沿 A→B 推过 B
轴 0.06 → 放低到 0.020 → 松手。不借 A 撑开、不拉伸、柱距无关，因此对后续变体更通用；spike
`run.test=carry`、demo `run.motion=carry`。与 `transfer` 并列，取舍由实跑读数定。

## 4. 与 2.7 的关系

on-phase 结束时环同时围住 A、B（2.7 的终态）。但 2.7 要求终态绷紧（错误动作释放后回弹）需要周长
< 围两柱的最短周长 0.381，而钩开梯形在该周长下要求 >45% 拉伸；两者冲突，2.7 需另行设计
（更细的 B 柱或两点钩持），本任务终态是松的。

## 5. spike 读数（2026-08-24，GPU，无臂）

| 档 | 读数 |
|---|---|
| settle | 50 步收敛，winding {A:1,B:0}，A 间隙 33.8 mm，无穿模 |
| stretch | 钩带跟踪误差 ≤0.25 mm；平移段 A 顶未越过、B 顶越过；释放后 {A:1,B:1}，弧长比 1.013 |
| transfer | near band 距设计点 26.7 mm（demo 按实测位置抓）；释放后 {A:0,B:1}，全程最小间隙 2.0 mm（=势垒） |
| carry（2026-08-25） | 抬到指尖 0.295 时环离开 A（第 145 步 A 顶越过）；推过 B 第 50 步 B 绕数 0→1（两股分到两侧）；放低释放后 {A:0,B:1}，环远端搭在 A 柱面（松环，绕数 0） |

## 6. 待办

- demo 三视角录制与对照 motion（`drape_outside` / `lift_only`）的实跑读数。
- off-phase 夹爪与 A 柱的干涉：指垫沿 y 张开、手心离柱面 4 mm，若 rigid 求解器里手指碰柱需把
  抓取点沿环外移。
- 随机化 registry、stability_sweep、episode_spec。
