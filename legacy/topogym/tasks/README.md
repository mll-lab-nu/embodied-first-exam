# 新版 TopoGym 任务环境

本目录用于翻新后的 10 项任务。历史实现位于 [`../tasks_legacy/`](../tasks_legacy/)。

当前已建立独立 Python 包和十项基线参数卡。工程状态以[首晚日志](../../docs/progress/2026-09-15_ten_task_bootstrap_log_zh.md)及实际运行报告为准。

- [十项任务环境部署提案](../../docs/develop/tasks/ten_task_environment_deployment_plan_zh.md)：任务定义、物理难度、参数与完整验收要求。
- [首晚工程清单](../../docs/develop/tasks/ten_task_first_night_plan_zh.md)：共用前置工作、逐任务第一步、产物与优先顺序。

后续按任务建立子包，名称见首晚清单。沿用 `Layout → SceneBuilder → Scene` 的现有职责划分，先完成几何、参数、初始化和环境诊断。

包入口保持轻量，由具体任务入口按需加载物理后端。复用旧代码时，先梳理它的导入依赖，再迁入需要的几何或场景模块。

| 入口 | 范围 |
| --- | --- |
| `catalog.py` / `configs/task_cards/` | 十项固定基线、候选参数轴与资产状态；元数据校验不代表物理通过 |
| `lock_picking/` | 原三锁片、两次回退结构的新场景入口，完整单臂物理执行 |
| `hedgehog_in_cage/` | CLASSIC 三星十刺球的参数化重建与带静止 Panda + Robotiq 的初态演示；官方精确几何、退出路径及物理稳定性待验证 |
| `horseshoe_ring/chain_probe.py` | 三只闭合刚体链环的夹具接触试验，完整马蹄结构待资产 |
| `buzz_wire_3d/probe.py` | 直线加平面单弯的环杆接触试验，双向接触对照；完整机器人与空间路径后续扩展 |

复现命令、实际结果和失败记录统一放在首晚日志中。

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
