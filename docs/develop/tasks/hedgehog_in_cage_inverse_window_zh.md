# 刺球出笼：从可解 IK 反推偏心斜窗笼

本页记录路线一 `eccentric_window_v1`。从已完成的 CLASSIC 十刺工程重建实例出发，先改变解题路径并求连续机器人 IK，再用运动扫掠空间生成新窗口。原十刺球、S2 抓点和固定底座保持一致。

播放页与最终测量值以独立归档为准：
`runs/demo_metadata/hedgehog_in_cage/2026-09-17_eccentric_window_v1/index.html`。
视频在 `runs/demos/hedgehog_in_cage/` 平铺保存，前缀为 `2026-09-17_eccentric_window_v1_`。

## 设计顺序

1. 种子为 `runs/demo_metadata/hedgehog_in_cage/2026-09-16_classic_wood/` 中的已解物体路径、Panda + Robotiq IK 和落桌路径。
2. 对中段关键帧施加最大 3 mm 笼坐标 Y 侧移和绕 X 轴 −1° 倾斜，以正弦权重平滑进入和退出。初态、最终退出姿态与落桌目标相同。
3. 先生成完整提取及落桌的 513 帧 IK，将实际正运动学物体姿态写入 `ik_before_geometry.json`。该文件的 `geometry_pending: true` 是设计顺序的历史记录，不表示最终场景仍未生成。
4. 用球核、十刺和实际夹指盒碰撞体的保守球覆盖，形成连续运动的扫掠约束；每 2 mm 高度区间投影到笼壁角度范围，以线性规划拟合 19 个高度节点上的左右边界。
5. 修改正面 ±42.75° 扇区，将窗口边界限制在 ±41.5° 内，保留相邻笼条与上下圈。刺球、其他窗口和轴向开口保持原资产。修改后的笼体连通，视觉网格和碰撞凸块对应同一设计。

所有毫米数都是放大 3 倍后的场景尺寸。新笼为刚性工程设计，未测试实物薄笼条强度。较大的初始候选及夹指碰撞候选保存在工作目录 `attempts/`，不进入最终演示。

## 可解性与物理执行

几何证书采用 FCL 凸实体距离，覆盖“一个物体完全包含在另一个实体内”的碰撞情况。按物体材料点移动上界 0.1 mm 细分最终路径，共检查 13,287 个姿态，规划路径连续间隙下界为 0.611 mm。机器人、夹爪、笼体、桌面及底座另行检查。

这证明选定新路径能通过新笼。直线拉出发生碰撞；原路线在新笼中的采样最小间隙仍为 0.206 mm，未发现碰撞。因此当前版本尚未证明新增侧移/倾斜是必要动作，也未证明唯一解。原路线对照只做采样检查，不应将 0.206 mm 当作原路线连续间隙下界。

单臂足以执行，因为笼体固定在底座。流程从 S2 刺的预抓取位开始，双指同时接触后建立辅助抓持约束，随后穿窗取出、搬运、调整落桌姿态、降低、解除约束、张爪、撤离并自由静置 5 秒。没有从远处接近并识别抓点的阶段，也没有宣称依靠纯摩擦抓持完成。

Genesis 使用 64 位计算、5 ms 外层步长，分别以 10 和 20 个子步完整执行相同实例，即 0.5 ms 和 0.25 ms 内层步长。物理执行只控制关节，不在运行中重置物体或机械臂姿态。每步监测刺球—笼体及机器人—固定物碰撞深度，保存间隔为 10 ms。

执行后的独立检查重新验证保存的实际物体/机器人状态，并对相邻物体姿态插值给出连续几何间隙下界；该连续界限针对保存状态间的插值。物理子步内部由模拟器接触监测补充。解除约束后的最后两秒需满足漂移小于 0.2 mm、速度小于 1 mm/s、角速度小于 0.5°/s。

三路视频为同一次完整物理执行实际状态的离线渲染：`agentview / front_oblique / wrist`，另附 `three_views` 同步合成。保存完整渲染帧、源状态索引和相机姿态。不是将规划 IK 动画当作物理结果。

## 代码与复现

- `inverse_window.py`：运动变体、IK、扫掠反推、资产生成、几何证书。
- `inverse_runtime.py`：机器人检查、物理执行、实际状态检查和同步录制。
- `inverse_archive.py`：双步长结果核验、视频逐帧来源核验、完整解码、独立复制、播放页及目录登记。
- `tests/check_hedgehog_inverse.py`：凸体包含碰撞、插值材料点上界、种子 IK 一致性、无效证书拒绝。

在已有 Genesis/Nyx 环境中补充 `requirements/uv-topogym-hedgehog-inverse.txt`。从仓库根目录执行，使用新的输出目录，避免覆盖已验证运行：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.inverse_window ik --shift .003 --tilt -1 --output /tmp/hedgehog_eccentric_reproduce
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.inverse_window geometry --output /tmp/hedgehog_eccentric_reproduce
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.inverse_window certify --output /tmp/hedgehog_eccentric_reproduce
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.inverse_runtime plan-audit --output /tmp/hedgehog_eccentric_reproduce
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.inverse_runtime physics --output /tmp/hedgehog_eccentric_reproduce
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.inverse_runtime audit --output /tmp/hedgehog_eccentric_reproduce
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.inverse_runtime physics --substeps 20 --output /tmp/hedgehog_eccentric_reproduce
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.inverse_runtime audit --substeps 20 --output /tmp/hedgehog_eccentric_reproduce
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.inverse_runtime render --output /tmp/hedgehog_eccentric_reproduce
```

默认工作目录的正式归档使用 `python -m topogym.tasks.hedgehog_in_cage.inverse_archive`，已有同名归档时会拒绝覆盖。证书绑定生成器源码、IK 和所有资产哈希；修改这些输入后须重新生成证据。

查看 `certificate.json`、`robot_audit.json`、两次物理运行的 `report.json / audit.json`、`time_step_comparison.json` 和 `recording/recording_report.json`，可区分规划间隙、实际执行间隙、释放静置与渲染来源。独立归档不依赖原工作目录播放或读取核心证据；源码完整再运行仍使用项目的共享机器人与桌面资产。

## 本实例交付测量

2026-09-17 两次完整物理执行和独立状态检查均通过。每次 16,445 个外层物理步，82.225 秒、8,224 个保存状态；两份物理配置仅子步数不同。实际状态插值间隙下界分别为 1.037 mm 与 1.047 mm。两次末态位置差为 0.026307 mm、姿态差为 0.096979°。

录制为 12 fps、987 帧、82.25 秒；三个独立视角均为 960×720，合成为 1440×360。全部视频完整解码通过，源状态索引逐帧核对一致。相关单元及项目布局检查共 15 项通过。
