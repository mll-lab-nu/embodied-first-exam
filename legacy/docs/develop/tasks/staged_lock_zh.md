# Staged Lock：同向凸片钥匙与被动锁片

本任务属于 `connectivity`。目标是把带三个同向凸片的钥匙穿过三片可转动锁片，进入后方固定终点孔。它是结构约束操作任务：当前插入深度决定钥匙能带动哪些锁片，操作会改变后续允许通过的角度。

固定终点采用深绿色圆角方板（默认 160 × 160 mm，圆角半径 12 mm），双面带固定 `GOAL` 铭牌和四角螺栓，直接安装在底座上。前三片保持圆盘外形，使可转锁片与固定目标在形状和安装方式上可区分。目标板的孔位、孔型、厚度和成功条件沿用原定义；外轮廓的可见网格与碰撞体同步改为方板。铭牌和螺栓是表面装饰，不随成功状态变化，也不遮挡孔口。

## 当前执行契约

- 完整 Franka Panda 使用 IK 与关节位置控制，启用机器人重力补偿。环境重力仍为 `-9.81 m/s²`。
- 三个锁片是被动连续转轴，没有电机、目标角度控制或逐帧位姿写入。
- 钥匙是受重力作用的 **6 DOF 自由刚体**。初始放在下方伸出托板的两个 V 形承托块上，手柄悬伸以留出抓取空间；承托由真实碰撞接触提供。原先把钥匙固定在孔轴高度的滑动/旋转导向关节已移除。
- 辅助抓持使用 Genesis 的运行时 weld。开启前检查抓持位置误差、闭爪程度，以及左右手指与钥匙的同时接触。若普通 IK 留下的亚毫米居中误差使一侧悬空，先通过精确 IK 与实际关节控制小幅居中，最多重试三次；不会把历史单指接触合并为双指接触。weld 只连接手部与钥匙，保留接触阻挡；它不连接锁片，也不修改锁片角度。
- 钥匙、凸片、锁片和终点都存在碰撞体。凹孔由多个显式凸扇区围成，逐块凸化，避免把整个孔填成一个凸包。
- 机构初始姿态只在 reset 时设置。执行阶段通过机械臂、抓持约束与接触力演化，使用 readback 进行 oracle 决策和验收。
- 接触力保护安装在 task 的 `scene.step()` 上，对所有下游控制器生效。钥匙与机构的合计接触力超过 10 N 时，停止推进并终止该 episode；随后只允许停止后的物理收敛。10 N 是离散采样的触发阈值，不是瞬时峰值上界。不能忽略终止信号继续强推。
- 质量与转轴阻尼可配置。钥匙的重心与惯量根据杆、凸片、手柄的组合几何和配置质量估算；锁片仍使用近似常量，均未按实物标定。可动机构 URDF 的 `default_armature` 为 0；Franka 保留其机器人参数。

## 场景与尺度

使用共享桌面和 Franka 安装面。机构位于桌面侧前方。默认圆盘直径 160 mm、层间距 85 mm，轴高 1.105 m（高于桌面约 185 mm）；三个凸片始终保持同向。槽口外半径 45 mm、中心孔半径 14 mm、凸片半径 36 mm，视觉网格与碰撞体同步放大。手柄位于领先凸片后方 300 mm，确保最深插入时手柄和夹爪不会撞上第一片圆盘。接近时先抬高手臂，再转向并下降抓持，避免扫到降低后的机构。

托板表面默认高 1.005 m，钥匙静止轴高约 1.0142 m，低于孔轴约 90.8 mm。先让钥匙在重力下落座，再按实际六维位姿抓取；抬升清离承托块后，对准孔轴开始插入。V 形块没有把钥匙绑定到世界，也不会在抓起时切换回旧导向。改动与验证见 [实体承托与自由钥匙修订](../../progress/2026-09-14_staged_lock_supported_key_zh.md)。

Nyx 使用 `compact_lab`：3.8 × 3.4 m、顶高约 2.6 m 的四面围合房间，包含顶面、地面、储物柜、白板和闭合门板。灯光置于室内，强度按当前 renderer 的画面标定；尚未进行实测照度标定。旧两面墙布景仍供其他 demo 使用。

成功条件读取实际状态：领先凸片进入第四层固定孔，相关槽口方向相容，轴心偏移不超过 10 mm、轴向倾斜不超过 3°，钥匙速度降到阈值内，抓持解除，并且执行过程通过几何与接触检查。深度相同但从旁边绕开的位姿不能通过。松手后钥匙由孔壁接触支撑，会自然下沉到间隙下沿。回退次数、与某条演示动作序列的一致性不是成功条件。

## 变体与 oracle

| 配置名 | 变化 | 要验证的能力 |
|---|---|---|
| `aligned_entry` | 基准孔型和初始角度；名称指基准入口配置，并非钥匙已预先对准 | 分层啮合、持续旋转、逐层贯穿 |
| `reindexed` | 根据 seed 随机化三片初始角度与钥匙初始角度 | 根据当前状态调整动作，不复用固定角度脚本 |
| `asymmetric` | 改变各层孔口排列，并随机化终点方向和初始角度 | 在不同孔型下重新计算相容入口 |
| `tight_clearance` | 减小槽半角至 10°，同时随机化初始角度 | 更精细的对准与接触间隙处理 |

oracle 读取钥匙的实际六维位姿及锁片关节角度，选择下一层入口，再寻找当前已啮合层与下一层共同允许的方向；操作后重新读取状态。它是读取状态真值的 oracle，不是视觉策略。相机图像中不叠加真值、角度或阶段提示。

这些自由转盘允许单调增加插入深度的解。当前 oracle 不人为要求回退，也不把任务设计成猜密码或搜索离散机关序列。遇到受阻可在实际状态上重新对准并重试；不能通过直接设置机构位姿绕过碰撞。

计划中的“锁片数量 × 最少必要回退次数”可作为后续变体轴，但当前仅改槽方向不能保证必要回退或唯一解；2 片任务也尚未参数化。机构分析、61 个配置的零回退几何检查和旧录像的对应范围见 [变体可行性检查](../../progress/2026-09-14_staged_lock_variant_feasibility_zh.md)。

可选实体限位原型通过 `task.rotor_stops` 配置，当前默认样式为固定整环、每环一个贯通弧槽、与盘同色连接耳及圆柱销；外环和下方立柱、脚座统一材质。专用入口 `demos.connectivity.staged_lock_limits_demo` 进行施加测试力矩的台架演示；普通插入 oracle 尚未适配有限转角，也未认证必要回退次数。结构、Nyx 视频和关闭关节限位的碰撞对照见 [单槽整环方案](../../progress/2026-09-14_staged_lock_single_slot_ring_zh.md)。

## 录制与检查

默认录制四路原始视频：

- `front`、`side_oblique`：1280×720，包含完整机械臂与机构。front 恢复从桌面前方朝机器人方向观察。
- `wrist`：640×360，安装到完整机械臂的 hand 连杆。
- `lock_detail`：960×540，固定外部近景，补充小孔口细节。

需要三路机器人观察时，使用 `--config-name staged_lock_policy_views`：只录制 `agentview`、`wrist`、`front_oblique` 三个同步 MP4。它继承完整 Nyx 实验室，重新标定两台外部相机和腕部安装位置；实际参数、取舍和验收见 [三路相机修订](../../progress/2026-09-14_staged_lock_policy_views_zh.md)。原四路配置仍保留。

额外近景是第四个真实可放置的外部相机，不是图像裁剪或模拟器状态示意图。使用哪些视角训练策略，需要在评测协议中明确；当前实验不声称三路或低分辨率图像已经通过视觉决策验收。

每个录制帧检查完整机械臂的世界坐标视觉顶点投影，报告两路外部相机的最小画幅边距。这个检查保证机器人没有被画幅裁掉，不代表每个表面都没有自然遮挡。Nyx 录制还比较实际提交给 renderer 的相机位姿与共享 camera rig。

另外检查整套机构的画幅边界，以及抓持期间 wrist 图像上方在世界坐标中的 z 分量。水平抓持使手部局部 `+x` 朝下，所以 wrist 固定安装在局部 `-x` 一侧：`offset_pos=[-0.08,0,0.025]`、`offset_lookat=[0,0,0.35]`、`offset_up=[-1,0,0]`。视线仍朝指尖所在的局部 `+z`，相机位于夹爪上侧、略向下观察轴线。没有图像旋转或世界水平线锁定；相机会随真实手腕滚转。

输出包含 `config.yaml`、`layout.json`、`assets/`、`report.json`、`frames.json`、初末态 PNG、四路 MP4、四视角合成 `overview.mp4` 与本地播放页 `index.html`。`frames.json` 的角度、关节位置和 oracle 阶段属于调试/评测状态，不应直接当成图像策略的观察。当前入口尚未接入统一 H5 episode writer。

## 运行

```bash
cd /home/jianwen/topogym

# 物理执行与光栅化录制
.venv-gs121-nyx/bin/python -m demos.connectivity.staged_lock_physical_demo

# Nyx 录制；默认四路相机，20 fps，对应每 10 个 0.005s 的物理步采样
.venv-gs121-nyx/bin/python -m demos.connectivity.staged_lock_physical_demo \
  --config-name staged_lock_nyx run.output=runs/staged_lock_task/nyx_new_run

# 一个生成变体
.venv-gs121-nyx/bin/python -m demos.connectivity.staged_lock_physical_demo \
  task.variant=asymmetric task.seed=3 recording.enabled=false \
  run.output=runs/staged_lock_task/asymmetric_3

# 三个生成变体 + 不读孔型、固定角度推进的反例
bash bash_scripts/tests/staged_lock_variation_sweep.sh

# 离线几何、oracle 和资产检查
.venv-gs121-nyx/bin/python -m unittest tests.check_staged_lock_task
```

GPU 使用 `.venv-gs121-nyx`。普通录制使用 `staged_lock.yaml`；Nyx 配置继承相同物理任务，不再使用 pitch demo 的零重力或无碰撞机构。

## 文件职责

| 文件 | 职责 |
|---|---|
| `topogym/tasks/connectivity/staged_lock.py` | 场景、完整机器人、物理机构和状态读取 |
| `topogym/tasks/connectivity/_staged_lock_geometry.py` | 参数、变体、几何约束与 URDF/网格资产生成 |
| `topogym/primitives/staged_lock.py` | 抓持位姿和接触门控的辅助 weld |
| `topogym/planning/staged_lock_planner.py` | 下一层入口与共同角度区间 |
| `topogym/verification/staged_lock_verifier.py` | 终态判定 |
| `demos/connectivity/staged_lock_physical_demo.py` | 完整流程、逐步检查与录制 |

从原 demo 继承了同向凸片、孔型、实验室材质与观察思路；正式任务没有反向依赖演示脚本。
