# 当前检查

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
