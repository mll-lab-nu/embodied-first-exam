# 当前配置

`config.yaml` 只组合通用环境、机器人、prefabs、录像与运行参数；任务由具体入口选择。
旧任务配置位于 [`legacy/configs/`](../legacy/configs/)，不参与当前 Hydra 搜索路径。

| 入口/配置组 | 用途 |
| --- | --- |
| `presentation_preview.yaml` | 无任务物体的共享场景与 RGB/录像/HDF5 检查 |
| `aloha_lab_preview.yaml` | ALOHA 2 双臂实验室；配对 `world_tabletop_aloha_v1` 和 `aloha_position_ik` |
| `rope_threading_preview.yaml` | Wang 三环参考基础场景，U 形自由绳 FEM+IPC、侧置支架与 ALOHA 双臂 |
| `lock_picking_baseline.yaml` | 当前开锁基线，独立加载 `task_configs/lock_picking.yaml` 与 `run_configs/lock_picking.yaml` |
| `lock_picking_spaced_preview.yaml` | 加宽锁片间距的初态检查；长行程未完成机器人验收 |
| `hedgehog_in_cage_classic_preview.yaml` | CLASSIC 三星刺猬初态；自身组合共享组 |
| `horseshoe_ring_preview.yaml` | 完整双马蹄装配初态、三视图和相机绕行；可选重力落桌检查 |
| `cast_coil_preview.yaml` | 金银卷绕件 3 倍原型、初态预览和自由落桌检查 |
| `cast_coil_aloha.yaml` | 原型三段解的双臂物理执行；预抓取起点、接触门控辅助抓持、重新设置的位置控制增益与静摩擦修正 |
| `cast_keyhole_preview.yaml` | Keyhole 开口金叉 / 封闭银孔原型，双自由刚体、相机预览及短时静置 |
| `task_cards/` | 十项任务固定基线及资产状态，不是 Hydra 主配置 |
| `presentation_configs/nyx_lab.yaml` | 默认 Nyx、室内灯、封闭实验室、桌面材质 |
| [`camera_configs/`](camera_configs/README.md) | ALOHA 双臂四路观测和官方模型 demo 视角；合并到 `env.cameras` |
| `env_configs/` | 刚体/PBD 与 FEM 两个通用世界预设 |
| `common_configs/`、`robot_control_configs/` | 共用坐标、Franka + Robotiq 2F-85 与控制参数 |
| `render_bench.yaml`、`batch_render_probe.yaml` | 通用性能测量，显式使用各自对照后端 |

```bash
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.lock_picking --cfg job
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.lock_picking run.inspect_only=true
.venv-gs121-nyx/bin/python -m tests.check_configs_compose
```

任务表面材质写在 `env.appearance`，公共桌面材质写在 `env.presentation.appearance`。
显式更换渲染器使用 `env.renderer.type=rasterizer`；背景使用 `env.presentation.background=checker`。
配置修改需检查其当前 consumer；`run.record_dataset` 等通用字段的存在本身不代表每个任务入口已经实现对应能力。
