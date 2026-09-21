# 当前检查

`bash tests/check_agent_rollout_setup.sh` 是 evaluation 前的 Linux 环境检查入口：检查 Python 依赖、
`codex / bwrap / ffmpeg / ffprobe`、本机代理端口和隔离环境中 Codex 的初次调用及续轮参数。
默认使用仓库的 `.venv-gs121-nyx/bin/python`；可用 `--python /path/to/python` 指定环境。
加 `--regression` 会继续运行 `tests.check_agent_rollout`、`tests.check_agent_task_spec` 和
`tests.check_agent_rollout_budget`、`tests.check_agent_rollout_tools`；使用本机 HTTP 代理与真实 Codex CLI，API 响应全部模拟，
验证逐请求输入计数、输出缩限、未知 usage 停止和密钥隔离，需允许本机临时端口。
检查失败返回非零退出码；不需要 API key、不调用模型或启动 Genesis 场景。
完整用法见[用户教程](../docs/develop/modules/model_service_design_zh.md#openai-api-evaluation)。

`python -m unittest tests.check_agent_rollout -v` 检查固定变体、RGB / privileged 信息边界、连续分段 MP4、初态复验、预算和 Codex 目录隔离。模型传输使用模拟响应，不调用付费 API；见[视频 rollout 管线](../docs/develop/modules/agent_rollout_pipeline_zh.md)。

`python -m unittest tests.check_agent_rollout_tools -v` 检查新 SDK 的 RGB/simulator 权限、固定初态 reset、
跨 episode 预算、请求去重与 revision、失败恢复及真实 Codex 终端调用；模型响应全部模拟。
`bash tests/run_agent_rollout_tools_smoke.sh --task cast_coil --output runs/agent_rollouts/NEW_NAME`
会运行真实 Genesis CPU 场景、查询/重置并保存四视角视频，不调用模型。
使用 `--task counter` 可先做合成环境检查；输出目录必须全新。实操见 [rollout 手册](../docs/develop/modules/agent_rollout_usage_zh.md)。

`python -m unittest tests.check_orbits tests.check_task_baseline_catalog tests.check_configs_compose`
检查第 13 项 Orbits 的四环五杆、固定连接、孔洞与绳初态间隙、末端杆绕数、资产重载、
目录和 Hydra 配置；不代表绳动力学或完整解法通过。见[场景说明](../docs/develop/tasks/orbits_zh.md)。

`python -m unittest tests.check_orbits_robot` 检查 Orbits 原生动力学模型与 IK 的坐标一致性、
双侧指尖接触门槛、错误绳段拒绝、无瞬移的辅助抓持、两臂独立换抓和释放、
完整检查点恢复、自然绳圈与双端连接，以及不可达路径在规划失败后不改变物理状态。
接触状态来自局部夹持抬升测试；这些检查不代表完整解环成功。

`tests.check_knot_agent` 检查 FEM agent 信息边界、接触自动选带、双手重叠约束拒绝、释放与平面展开判据，以及 IPC 约束容量重叠回归。
`python -m tests.probe_knot_agent --output 新目录` 是需要 CUDA 的四路协议短测，只有 6 个控制步，不是解结执行。见 [接入文档](../docs/develop/modules/knot_untying_agent_adapter_zh.md)。

`python -m unittest tests.check_lock_picking_variants -v` 检查开锁固定家族接入公共 seed、条件尺寸域、外观流独立、跨调用顺序复现、真实 IK 拒绝与确定性重试、无需原型库的快照恢复及篡改拒绝。256 seed 和九代表的几何／IK 审计入口为 `topogym.tasks.lock_picking.verify_variants`；不步进物理，不生成数据集或 H5。见[生成器说明](../docs/develop/tasks/lock_picking_zh.md)。

`python -m unittest tests.check_buzz_wire_3d tests.check_buzz_wire_physics tests.check_rigid_bootstrap_geometry -v` 检查空间电流棒的全程连续净空、保持穿环、触壁与错误姿态反例、平面退化、底座碰撞、URDF 碰撞体一致性及配置复现，并回归自由刚体的局部力矩、力矩限幅、录像实测时间轴和碰撞资产一致性；另行运行 `demos.environment_bootstrap.buzz_wire_3d` 检查实际场景加载，见[说明](../docs/develop/tasks/buzz_wire_3d_zh.md)。

`.venv-gs121-nyx/bin/python -m unittest tests.check_blanket_flatten tests.check_blanket_execution -v` 检查被子连续网格、等距折叠、层间三角面净空、材料坐标重建、展平反例、持续静置窗口，以及失败/未释放/瞬移/不完整视频不能归档。实际重力下落另用 `python -m demos.environment_bootstrap.blanket_flatten`；完整物理尝试和三视角录制见[任务文档](../docs/develop/tasks/blanket_flatten_zh.md)。

`python -m unittest tests.check_agent_bridge -v` 检查独立 coding-agent 接口的不可回滚执行、全帧反馈、幂等请求、token 计量和 HTTP / 模拟模型闭环；HTTP 检查需要本机临时端口。真实环境与手动/API 测试方法见 [agent bridge](../docs/develop/modules/agent_bridge_zh.md)。
`.venv-gs121-nyx/bin/python -m unittest tests.check_agent_task_spec -v` 离线检查文字目标、ALOHA 关节/夹爪单位、相机投影/随动外参及物体真值不泄漏，不启动或推进 Genesis。

`tests.check_horseshoe_agent` 检查 Horseshoe 接触辅助、连续稳定判定、动作和信息边界；
`tests.check_agent_local` 用真实本地常驻进程检查任务包、图像下载、幂等和关闭，不需要 HTTP socket。
`python -m tests.probe_horseshoe_agent --output 新目录` 是可选的真实 Genesis 短程冒烟，非完整取环验证；
使用 `.venv-gs121-nyx/bin/python` 及 headless 渲染环境，见 [接入说明](../docs/develop/modules/horseshoe_agent_adapter_zh.md)。

`tests.check_keyhole_agent` 检查共享机器人 runtime、统一注册、公开信息边界，以及 SAT 包含碰撞和分离保持判据。
`python -m tests.probe_rigid_agent --task cast_keyhole --output 新目录` 用同一公共协议执行三段真实物理短程检查；
`--task horseshoe_ring` 复验共享模块对原任务的兼容。探针仅保持、小幅运动和单手释放，不加载解题轨迹。

`tests.check_claws_agent` 检查 Claw 静态初态哈希、公共 ALOHA 复用、信息边界、原三角网格相交/包含，
以及双件释放、向上支架承载和连续静置判定。`tests.probe_rigid_agent --task interlocked_claws --output 新目录`
验证保持 50 步、小幅运动 50 步和左手释放命令 1 步；不代表完整拆解或重新抓持验证。
见 [Interlocked Claws adapter](../docs/develop/modules/interlocked_claws_agent_adapter_zh.md)。

`tests.check_hedgehog_agent` 检查 Panda 七关节／半开口单位、三路初态要求、控制器无隐藏步进、信息边界和取出后释放静置判据。
`python -m tests.probe_rigid_agent --task hedgehog_in_cage --output 新目录` 连续执行 80 步保持、20 步小幅运动和 1 步开口指令；
只验证辅助解除，不代表完全张爪或完成取出。见 [Hedgehog adapter](../docs/develop/modules/hedgehog_agent_adapter_zh.md)。

`tests.check_lock_agent` 检查 Lock Picking 公开信息边界、END／松手判定、连续转角、过载失败锁存和偏轴接近不误判。
`python -m tests.probe_rigid_agent --task lock_picking --output 新目录` 检查 home 初态、保持、微动和无附着开口命令，未执行抓起或插入。
见 [Lock Picking adapter](../docs/develop/modules/lock_picking_agent_adapter_zh.md)。

`tests.check_buzz_wire_agent` 检查静态资产哈希、无参考轨迹依赖、公共 Panda 信息边界、纯摩擦模式不启用附着，
以及穿环连续性、通行禁碰、末端释放承载、机械能和静置判据。
`python -m tests.probe_rigid_agent --task buzz_wire_3d --output 新目录` 验证 80 步保持、20 步微动和 1 步张爪指令；
核对双指真实接触、无辅助、三路逐步图像和幂等。只验证短程接口，未验证完整释放或通行。
见 [Buzz Wire 3D adapter](../docs/develop/modules/buzz_wire_agent_adapter_zh.md)。

```bash
.venv-gs121-nyx/bin/python -m unittest discover -s tests -p 'check_*.py'
.venv-gs121-nyx/bin/python -m tests.check_rope_tube_mesh --obj <tube.obj> --radial 20
bash tests/check_genesis_ipc_patch.sh
```

单元检查覆盖当前配置解析、任务卡、归档后的导入和资产路径、开锁几何与回退证书、
松手接触门槛、刚体夹具几何、共用 Robotiq 接口、Nyx 相机与 RGB 录制协议。
`check_rope_tube_mesh` 是可复用绳网格的独立命令检查；IPC 检查需要支持该后端的环境。

GPU 实际渲染与数据入口：

```bash
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.presentation_preview
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.aloha_lab --check-steps 100
```

`check_aloha_shared` 覆盖双臂模型来源、源物理参数、双底座占地和左右臂命令隔离。
ALOHA demo 只验收静态集成及可选短时保持；双臂任务执行与双臂数据 schema 尚未验收。

`render_bench.py` / `batch_render_probe.py` 及对应 shell 脚本继续用于公共渲染性能检查。
旧任务测试在 [`legacy/tests/`](../legacy/tests/)；一次性 `*_spike.py`、`study_*`、`diagnose_*` 已清理。
测试通过范围以具体检查为准，不代表十项任务均完成物理验收。

Horseshoe Ring 连续路径检查使用 `python-fcl`；缺少该依赖的环境会明确跳过这六项：

```bash
PYTHONPATH=. .venv-gs121/bin/python -m unittest discover -s tests -p 'check_horseshoe*.py' -v
```

`check_cast_coil` / `check_cast_coil_verification` 覆盖原型实体、质量惯量、连续碰撞证书、
控制速度、错误路径和不完整报告拒绝。CUDA 受力台架另行执行：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.qualify --run-physics
```

该命令保存默认及半时间步的全部通过/失败结果；不代表官方八步解法或机器人抓持已通过。

`check_cast_coil_inverse` 复核三个运动反推结构的连续无碰撞路径、旧路径阻挡、
螺旋运动位移界、变体中间步骤不可跳过，以及离线物理视频的原始状态哈希、步号和释放证据。
完整机器人执行与半时间步对照仍由各 demo 的 `validation.json` 单独记录。

`check_cast_coil_appearance` 检查基础版的三个单参数外观模板、质量变化、全路径仿射对应关系和连续解锁证书，防止只缩放端点或误用运动反推变体作为种子。

`check_cast_coil_official_trial` 验证官方指导试验使用的加速碰撞计算、步骤连续性，
以及“第 3 步已完全分离、随后空中转动”候选必须被拒绝。

`check_cast_coil_solvability` 检查旋转中途的桌面碰撞、已知解法的整体抬升余量，
以及模板未变但 URDF 碰撞体已变时必须拒绝复用旧证据。

`check_cast_coil_robot` 检查 float32 仿真关节状态输入后的逆运动学数值精度，
以及部分流程、缺少相机、未释放辅助约束、运动学回放或曾经穿透时不得归档为完整机器人 demo。
完整双臂物理执行与录制分别使用 `topogym.tasks.cast_coil.robot_plan`、`robot_demo`、`robot_archive`，
具体命令和辅助抓持范围见 `docs/develop/tasks/cast_coil_zh.md`。

`check_cast_keyhole` 检查开口金叉与封闭银孔、实际碰撞槽口、质量惯量、无穿透候选初态及导出契约；
使用已安装的 `python-fcl`。实际 GPU 检查入口如下，包含逐块碰撞加载核对和 0.5 秒自由静置：

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.cast_keyhole
```

官方实物有公开解法；本地尺寸为照片重建，完整拆解路径尚未验证。

`check_horseshoe_physical_grasp` 检查有载荷的双指垫接触路径：两只马蹄须位于指垫之间，
不能把悬挂在已夹住马蹄上的另一只马蹄、无载荷触碰或桌面支撑当作共同夹持。
完整重力执行由 `topogym.tasks.horseshoe_ring.verify_physical` 独立复核；
它要求原始初态、初始圆环下落、换抓接触证据、保持链眼连接和无辅助的圆环落桌静置。
运行方式见 `docs/develop/tasks/horseshoe_ring_zh.md`。

`check_horseshoe_timestep.py` 检查半时间步对照的条件一致性：拒绝换几何、换控制增益、
换执行代码或未实际减半时间步的比较；允许各运行按实测状态独立重规划。
运行：`PYTHONPATH=. .venv-gs121-nyx/bin/python -m pytest -q tests/check_horseshoe_timestep.py`。

`check_horseshoe_variant_generator.py` 检查 v2 的公共 seed / EpisodeSpec 接入、固定家族与类内联动参数、
快照恢复与篡改拒绝、尺寸变化后的初态/折合 IK、保持家族的有界重试，以及物理或家族区分检查失败时禁止放行。
这里的模拟验收夹具只测试接口，不构成物理成功证据；实际执行与 256 seed 参数检查见
`docs/develop/tasks/horseshoe_ring_zh.md`。

`check_horseshoe_ring_gravity_phase.py` 检查自由圆环自转时，重力参考抓点的世界位置和姿态不变，
同时保留旧基础 runner 的材料相位行为。它不替代完整抓环动力学验收。

`check_horseshoe_ring_release.py` 用保留的两个 F3 失败末态检查：原落桌点仍因 IK 不可达被拒绝，
邻近位置能得到通过原门槛的携环路径；已成功的 F1 原位置与路径保持不变。
夹具位于 `tests/fixtures/horseshoe_ring_release_v2.json`，测试不依赖原始运行目录，也不把规划当作物理成功。

`check_buzz_wire_robot.py` 检查紧凑单臂实例的完整倾斜环净空、平面握柄 URDF 可加载性与保守包络、最终直立段释放条件、姿态输入拒绝和原始机器人关节限位。实际动力学与步长复验见 Buzz Wire 任务归档。

`check_buzz_wire_families.py` 检查 F2 / F3 的关卡顺序、两端支撑、工具尺寸保持、姿态插值与非法输入；包含两个端点均无碰撞、旋转中途却撞障碍的反例，防止把离散姿态误报为连续通路。联合运行 `tests.check_buzz_wire_3d tests.check_buzz_wire_physics tests.check_buzz_wire_robot tests.check_buzz_wire_families`。
