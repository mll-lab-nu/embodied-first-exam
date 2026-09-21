# 解绳结：一个松 Trefoil 的基础场景

Agent 接入见 [Knot Untying adapter](../modules/knot_untying_agent_adapter_zh.md)：本地文件队列、双臂四图、CUDA FEM 接触辅助与可复制 prompt。该接口的验证状态独立于下述历史 demo。

变体设计见 [固定结型与家族内参数构造方案](knot_untying_family_space_zh.md)：三叶结、开放八字结、双重单结分别作为 easy / medium / hard 的目标代表，每个结型配独立的动作与 IK 路径。三档均要求持续支撑、余量控制和受限方向下的操作；难度须经实际执行及简单路线对照确认，当前 v9 也需补查这一操作要求。新增家族与参数范围目前为设计提案。固定实例可直接选择，参数采样另设入口。

实施与结果见 [物理稳定性验收与三视角全过程 demo 计划](knot_untying_physics_demo_plan_zh.md)。已完成 [完整机器人解结录像](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/index.html)，实际连续模拟 75 s，保留五路同步视角。从双手张爪准备位开始，双指接触后使用显式辅助抓持；松手时解除全部约束。本次轨迹的局部物理检查通过，P3 网格收敛及通用双手交接验收仍未通过。详细记录见 [抓持与录像复测](knot_untying_recording_attempt_zh.md)。

完整 demo 的 MP4 已按视角独立归档至 `demos/knot_untying/varaition_<id>/<camera>/`；播放页、报告、轨迹和归档清单保存至 `runs/demo_metadata/knot_untying/<date>_<run_id>/`。

本阶段铺设一根绳上只打一次结的场景。采用开放绳的 overhand knot；将自由端从外侧无交叉地闭合后，得到 trefoil / 3₁。物理场景中保留两个自由端，可供后续抓取和退绳。结型参考：[MathWorld](https://mathworld.wolfram.com/TrefoilKnot.html)。

## 几何和配置

源码在 `topogym/tasks/knot_untying/`，Hydra 入口为 `configs/knot_untying_preview.yaml`，基线登记在 `configs/task_cards/knot_untying.yaml`。

| 参数 | 默认值 |
| --- | --- |
| 绳径 | 8 mm |
| 总长 | 约 1.074 m，由曲线和自由端共同决定 |
| 每端余长 | 180 mm，包含平滑转向段 |
| 结形平面尺度 a | 32 mm；参数卡圈径比定义为 2a / 绳径 = 8 |
| 高度幅值 h | 8 mm |
| 初态桌面净距 | 至少 1 mm |
| 网格轴向间距 / 圆周段数 | ≤2.5 mm / 12 |
| 自接触作用距离 | 0.8 mm |
| 材料 | E=100 kPa，ν=0.45，ρ=650 kg/m³，μ=0.3，沿用共享候选值 |
| 材料参考态 | 直绳，初始结形有弯曲预应力 |
| 时间步 / 子步 | 5 ms / 4 |
| 固定或跟随顶点 | 0 |

采用曲线 `x=a(sin t+2 sin 2t), y=a(cos t−2 cos 2t), z=h sin 3t`，截取 `[π+0.5, 3π−0.5]`，升高到桌面之上；两端用切向连续的曲线转向结外，再接直尾。镜像 x 可切换手性。

几何验收检查三个横截交叉、沿绳的交替上下顺序、Gauss 顺序 123123 和一致交叉符号，并确认外侧诊断闭合不添加交叉。因此不是仅凭“有三个投影交点”判断结型。初始管面最小间距使用线段到线段距离；排除沿绳距离小于 πr 的局部邻居，另查局部弯曲半径。

## 运行

Nyx 环境需要额外安装 FEM 接触库；本机补齐的是旧仿真环境已有的同版本：

```bash
uv pip install --python .venv-gs121-nyx/bin/python -r requirements/uv-topogym-fem-ipc.txt
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.prepare_assets
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.knot_untying
.venv-gs121-nyx/bin/python -m unittest tests.check_knot_untying
```

默认输出 [trefoil_initial/index.html](../../../runs/environment_bootstrap/knot_untying/trefoil_initial/index.html)，包含 Nyx 实验室全景、俯视、近景、相机环绕视频以及自由静置前后状态。视频只绕初始结形移动相机。`run.record_video=false` 可跳过视频；`run.settle_steps=0` 仅建场与渲染，不会声明静置通过。

`inspection_report.json` 保存实际求解参数、体网格检查、模拟时长与初末状态；`settle_trace.json` 逐步记录位移与交叉数，`settle_states.npz` 保留实际顶点与中心线。直绳参考态若会翻转四面体，任务在构建前拒绝，不能静默改成结形参考态。

当前预览包含单台待命 Panda＋Robotiq 2F-85；机器人与绳接触已接入，未执行抓取。独立物理探针已加入长时接触检查和 ALOHA 双臂试跑，实际通过范围见上方验收页面。短时预览记录只检查这一初态的有限状态、体单元方向与投影交叉保留，不能代替连续碰撞的全程拓扑认证。

## 本机检查结果

2026-09-16 的默认运行完成 40 步、0.2 s 自由静置。实际体网格包含 6,516 个顶点、21,519 个四面体；直绳参考态和静置末态均无反转单元。三个交叉在每个采样步保留，末态 Gauss 顺序、上下交替和手性复查通过。

最大顶点位移约 37.27 mm，属于初始预弯曲绳的松弛，不能称为静止不动。末态按中心线及名义半径重建的管面净距约 0.48 mm，距桌面约 0.60 mm；这两个数是中心线诊断，不是形变后 FEM 表面的精确碰撞距离。实际报告保存该检查方法和范围。

几何、配置组合、参数卡和当前目录引用共 14 项测试通过；新增 Python 文件通过 Ruff 检查。Nyx 视频已检查为 45 帧、15 fps，只展示初始结形的相机环绕。
