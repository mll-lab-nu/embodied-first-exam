# 新版 TopoGym 任务环境

本目录登记 13 项任务：翻新后的 10 项任务、杂乱被子展平、长孔立柱解环，以及 Orbits 四环阶梯解绳。历史实现位于 [旧版只读存档](../../legacy/README.md)。

当前已建立独立 Python 包和基线参数卡。工程状态以[环境汇总](../../runs/environment_bootstrap/index.html)及各实例报告为准。

- [十项任务环境部署提案](../../docs/develop/tasks/ten_task_environment_deployment_plan_zh.md)：任务定义、物理难度、参数与完整验收要求。
- [首晚工程清单](../../docs/develop/tasks/ten_task_first_night_plan_zh.md)：共用前置工作、逐任务第一步、产物与优先顺序。

后续按任务建立子包，名称见首晚清单。沿用 `Layout → SceneBuilder → Scene` 的现有职责划分，先完成几何、参数、初始化和环境诊断。

包入口保持轻量，由具体任务入口按需加载物理后端。复用旧代码时，先梳理它的导入依赖，再迁入需要的几何或场景模块。开锁执行、规划、证书与判定现已全部迁入 `lock_picking/`；当前包不依赖历史实现。

| 入口 | 范围 |
| --- | --- |
| `catalog.py` / `configs/task_cards/` | 固定基线、候选参数轴与资产状态；元数据校验不代表物理通过 |
| `orbits/` | 第 13 项 Orbits：按视频重建四只阶梯木环、五根支杆、顶球及带拉柄黄绳；绳套初始绕在最低环下的末端支杆。ALOHA / Nyx 三视角静态检查，未实现绳动力学，见[场景说明](../../docs/develop/tasks/orbits_zh.md) |
| `slotted_post_ring/` | 第 12 项长孔立柱解环：ALOHA / Nyx 初态场景；新增 MuJoCo 柔绳、保孔碰撞、自由滑珠与端部连接，10 秒重力落稳及半步长复验通过；36 mm 候选版完成 147 秒外力驱动解环，另有 ALOHA 辅助抓持过珠、端片穿槽与交接的局部录像。这些历史录像采用一维约束绳；另已接入[三维体积 FEM 绳](../../docs/develop/tasks/slotted_post_ring_fem_zh.md)，单独验证材料与稳定性。完整机器人解环仍未通过，见[场景说明](../../docs/develop/tasks/slotted_post_ring_zh.md)。 |
| `blanket_flatten/` | 连续被子的悬空折叠、视觉绑定审计、重力下落、单臂辅助抓角展开、释放后验收与三视角物理状态录制；完整通过范围以运行报告为准。见[任务说明](../../docs/develop/tasks/blanket_flatten_zh.md) |
| `rope_threading/` | Wang 三环与 ALOHA/FEM+IPC 场景、原生子步审计、公开动作参考及接触触发执行入口；单环加载通过，时间步对照未通过，完整穿环尚未录制 |
| `interlocked_claws/` | 作者演示的两件原始 Claw OBJ、精确参考初态、ALOHA 双臂姿态与放置支架；非凸碰撞网格、装配／拆件检查和 Nyx 预览，物理脱困待验证 |
| `lock_picking/` | 原三锁片、两次回退结构的新场景入口，完整单臂物理执行 |
| `hedgehog_in_cage/` | 三个木质结构家族、共享 seed / EpisodeSpec 变体生成器和完整辅助抓持 demo；随机实例须独立通过物理验证，详见[任务记录](../../docs/develop/tasks/hedgehog_in_cage_zh.md) |
| `fiber_bundling/` | 固定电源终端、连续余量粗线、开放承托架、8 根外弯细线与窄环；尾端永久连接，逐步判定分叉端先入环，完整机器人穿环待实现 |
| `knot_untying/` | 单根 8 mm 开放绳上的松 trefoil / overhand 单结，FEM+IPC 自接触和直绳参考态；基础场景、初始几何和短时静置检查，机器人解结待实现 |
| `horseshoe_ring/` | 教程结构为双马蹄、两只独立中间链环和目标圆环；v3 基础实例已连续完成重力下双臂交接、取环及自由落桌。含预抓持和接触确认后的辅助抓持；见[物理 IK 范围与复现](../../docs/develop/tasks/horseshoe_ring_physical_ik_zh.md)。旧几何变体需分别重验 |
| `cast_coil/` | 金银卷绕件原型；初态预览、连续路径证书、接触台架与变体。三段原型解的 ALOHA 双臂物理 demo 已验收并归档，五路同步录像、预抓取起点与接触后辅助抓持；包含解除约束、撤手、自由静置和半时间步复核。官方八步复现仍未验证 |
| `cast_keyhole/` | 标准 Keyhole 的照片轮廓原型：开口金叉、封闭银色阶梯孔；双自由刚体、11 场景接触台架、时间步复核及起始动作连续间隙证据。完整官方路线 / 双臂 demo 未验收；见任务文档和运行审阅页 |
| `buzz_wire_3d/` | 紧凑低矮 Panda + Robotiq 单臂版：74.3 × 52.7 cm 底座、最高约 26.6 cm，平面握柄和空间回折 / 螺旋；实际摩擦抓持的完整动作及减半时间步复验通过，三视角各 91.84 秒。预抓取起点；旧照片台架与平面接触回归保留。见[任务文档](../../docs/develop/tasks/buzz_wire_3d_zh.md) |

复现命令见 `demos/README.md`，实际结果与失败记录保留在各实例报告中。

## 工程验证产物与初态检查

`runs/environment_bootstrap/` 保存新版十项任务首次搭建与验证的运行产物：
`catalog/` 是参数卡快照，`asset_audit/` 是资产核对，任务子目录中保存实例配置、生成的 URDF/网格、图片、视频和测试报告；`index.html` 是这些产物的人工 review 入口。
其中的局部接触试验、初态预览和完整执行具有不同验证范围，读取各自报告，不能仅凭目录名判断任务已经部署。

- 环境源码：`topogym/tasks/<task_id>/`。
- 可复现配置：`configs/`；候选参数卡：`configs/task_cards/`。
- 运行与展示产物：`runs/environment_bootstrap/<task_id>/<run_id>/`。
- 设计、证明与进度记录：`docs/`。

刺球出笼 CLASSIC 三星初态：

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.demo
```

输出为 `runs/environment_bootstrap/hedgehog_in_cage/classic_initial/index.html`。
机器人和刺球在整个展示中保持不变，视频只移动相机；[建模来源与范围](../../docs/develop/tasks/hedgehog_in_cage_zh.md)。

开锁增间距的初态检查：

```bash
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.lock_picking_inspect
```

使用 `configs/lock_picking_spaced_preview.yaml`，输出到 `runs/environment_bootstrap/lock_picking/spaced_initial/`。
锁片及钥匙凸片间距为 150 mm（原固定实例为 85 mm），仅构建场景、短暂静置并渲染初态；未执行加长行程的机器人 oracle。逐盘正视相机仅用于人工检查。

新开锁配置的 `task.visual.aperture_outline` 控制锁眼的黄色描边，默认宽 1.5 mm。
描边写入锁片正反面的视觉纹理，轮廓取自实际孔型；它随盘转动，碰撞几何和质量 / 限位参数不变。
