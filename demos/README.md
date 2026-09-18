# 当前运行入口

在仓库根目录用 `.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.<入口>` 执行。

| 入口 | 范围 |
| --- | --- |
| `presentation_preview` | 默认 Nyx 封闭实验室、腕部跟随、视频与 HDF5 RGB 检查 |
| `aloha_lab` | ALOHA 2 双臂相机预设：四路观测、官方模型展示位及实验室展示；可选短时位置保持检查 |
| `rope_threading` | Wang 三环参考初态：U 形自由绳、三环侧置支架、ALOHA 双臂、七路初态图与短时 FEM 静置；[说明](../docs/develop/tasks/rope_threading_zh.md) |
| `interlocked_claws` | 原始 Claw 网格、参考互锁初态、ALOHA 双臂姿态与支架；装配／拆件静态检查及相机绕行，未执行物理脱困 |
| `lock_picking` | 当前开锁物理执行，默认基线配置 |
| `lock_picking_inspect` | 加宽锁片间距的初态 review；不代表长行程执行通过 |
| `hedgehog_in_cage` | CLASSIC 三星刺猬初态场景 |
| `fiber_bundling` | 粗绳分叉细绳与窄环的基础场景、静置检查及 Nyx 预览 |
| `knot_untying` | 一个松 trefoil / overhand 单结的 FEM 初态、短时静置与 Nyx 预览；依赖 `requirements/uv-topogym-fem-ipc.txt` |
| `chain_links` | 三只闭合刚体链环的局部接触试验 |
| `horseshoe_ring` | 双马蹄、两条短链与目标圆环的完整装配初态；实物尺寸和取环路径待验证 |
| `cast_coil` | 金银方形卷绕件装配、拆件静态检查、绕行视频与自由落桌检查；原型三段解已验证，双臂执行使用下述独立入口 |
| `cast_keyhole` | 金叉与银色阶梯孔基础场景、拆件轮廓检查、相机绕行及短时自由静置；本地完整解法待验证 |
| `buzz_wire` | 环杆双向接触夹具试验 |
| `lock_aperture` | 钥匙和孔槽轮廓的几何初态检查 |

Hydra 入口可用 `--cfg job` 查看解析配置；argparse 入口用 `--help` 查看选项。
Cast Coil 双臂执行使用 `python -m topogym.tasks.cast_coil.robot_demo --plan <计划.json> --output <新目录> --record`；
计划生成、半时间步复核和正式归档命令见 [Cast Coil 文档](../docs/develop/tasks/cast_coil_zh.md#完整双臂物理执行与录制)。
该流程从预抓取状态开始，接触后采用辅助抓持，最终解除并自由静置。
结果汇总见 [`runs/environment_bootstrap/index.html`](../runs/environment_bootstrap/index.html)。
完整机器人多视角演示的 MP4 副本在 [`runs/demos/`](../runs/demos/)，播放页与配套材料见 [`runs/demo_metadata/index.html`](../runs/demo_metadata/index.html)；新 demo 交付前按 [项目规则](../AGENTS.md) 完成复制与检查。
旧任务入口移到 [`legacy/demos/`](../legacy/demos/)，只读保存。
