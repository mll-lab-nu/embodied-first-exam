# Task terminal 独立部分实施与接入记录

日期：2026-09-25。范围：[工程计划](../tasks/terminal_judgement_engineering_plan_20260925_zh.md)第 12 节 A—E。独立运行代码与测试已经实施，固定源码快照验收已通过。本轮不修改 `topogym/simulator/`、`topogym/world/`、registry、变体入口或场景预设。

## 已实现

- **Task 历史：**私有 `task_state`、纯计算 `evaluate_transition`、初始化、深拷贝、原子提交、校验与恢复；Task checkpoint schema 2。保留既有 `TaskResult` 字段、连续 tick/重复 tick 规则及失败优先。允许 `stable_duration_s=0`；没有全局改写各任务原有等待时长。
- **公共几何：**从生成 volume 的 rest/material_s 建立中心线索引，并校验运行材料身份；开放曲线穿有限孔的逐交点，处理正反抵消、端点/切触/共面不确定性；材料站按入口/出口两层边界有序推进，同 tick 按插值事件时刻处理，可回退重试；贴桌投影检查包含共线重叠、回折及退化。
- **完整入区：**有向有限高度区域、边界余量、完整目标包含与剩余系统分界。刚体缓存 visual 与 collision 的并集，解析曲面用保守外包；FEM 检查全部体顶点。检查目标静止、IPC 有效性/体积及附着残差。固定 link 变换纳入缓存，带活动关节的 URDF 被拒绝用这一单刚体路径。
- **绿色虚线：**`write_goal_region()` 从同一区域数据生成 OBJ 和 visual-only EntitySpec，明确 z-up、不重对齐、无碰撞；虚线内沿对应有效边界。尚未自动放进真实 Task 场景。
- **Buzz：**角色明确的金属接触立即失败，零接触力不作为豁免；木托架/手柄按独立角色过滤。有限孔穿套与相邻路线进度历史、终点姿态/支承/静止/释放候选。跨路线分支的模糊跳转不计完成，允许沿合法路径回退。出生或中途接触覆盖不完整会保留为可恢复历史，不能用终点的完整读数补造早先证据。实时事件来源和严格时间覆盖仍待 World 实施，未声称连续碰撞保证。
- **Lock：**有限角度盘越界失败、连续盘不按 ±180°误判；实际钥匙 SE(3) 下的轴线/倾角、前端榫片越过出口、杆仍占据 END 孔及厚盘槽形 clearance。实体外圈没有重写；新增静态销—槽碰撞回归，仍未做关闭关节限位后的动力学转矩实验。
- **Fiber：**从全部细芯 link 和最末端点取样，逐站 tip-to-root 穿入口/出口；前护套端面独立通过缩小孔径；实际切线弯折角而非 twist；历史随 Task 恢复。弯折过大阻止成功，不默认为不可逆损坏。属于 tick 采样与线性插值证据，不能证明 tick 中未被采样的所有运动。
- **Rope/Knot：**Rope 从布局 `required_crossings()` 消费目标序列（当前标准三环为 `R1−/R2+/R3+`），按实际环位姿检查精确顺序及孔边/厚度；新增两环候选回归，适配并行变体会话的布局接口，不激活其占位档。Knot 要求贴桌且投影无交叉/重叠。均使用全顶点最大速度和 IPC 有效性，尚未标定成功阈值。
- **六项目标区候选：**Slotted 为 `target_ring`；Orbits 为全部 `cord + handle`；Keyhole 固定为 `keyhole_silver`；Horseshoe 为 `target_ring` 且保留永久链连接检查；Hedgehog 为含尖刺的 `hedgehog_ball`；Claws 固定为声明时 `assembly.bodies[0].name`，公开说明返回具体名字。候选函数不动态交换目标身份，不强制松手。

## 实际修改/新增文件

修改公共文件：

- `topogym/tasks/base.py`
- `topogym/utils/geometry/rope.py`
- `tests/unit/test_task_state.py`

修改任务文件：`topogym/tasks/{buzz_wire_3d,lock_picking,fiber_bundling,rope_threading,knot_untying,slotted_post_ring,orbits,cast_keyhole,horseshoe_ring,hedgehog_in_cage,interlocked_claws}/common.py`。

新增公共实现：

- `topogym/evaluation/task_metrics.py`
- `topogym/utils/geometry/passage.py`
- `topogym/utils/geometry/regions.py`
- `topogym/assets/geometry/goal_region.py`

新增测试：`tests/unit/terminal_fixtures.py`、`test_terminal_geometry.py`、`test_goal_region.py`、`test_lock_stop_geometry.py`，以及 `test_terminal_<task_id>.py`（上述十一项任务各一个）。夹具都是合成测量，不是物理执行或机器人成功局。

## 当前接口与明确保留的缺口

### 子步接触输入（Task 侧已有消费者，World 侧尚无生产者）

```python
state["contact_events"] = {
    "schema_version": 1,
    "physics_step": current_tick,
    "substeps_complete": True,
    "geometry_roles_complete": True,
    "events": [
        {"role_a": "wand_metal", "role_b": "wire_metal",
         "touching": True, "substep": 1, "force_n": 0.0},
    ],
}
```

角色还包括 `wand_handle / wood_stop / finish_support / robot`。`touching` 必须来自明确物理接触语义，不能把 broad-phase 候选当触碰。额外 geom ID、原始力/穿深、精确子步号等字段可保留在事件里并进入失败 metrics。World 生产者与任务角色映射须一起验收；`link_a/link_b` 不能直接替代几何角色。`schema_version/physics_step` 不符会报错；缺少摘要为不可评估，摘要覆盖不完整不支持“全程无触线”，但已观察到违规事件仍立即失败。

Buzz 释放候选还要求显式 `state["assist_active"] is False`，缺失不会推断无辅助。此字段是当前 Task 侧接入约定，待 assist 统一状态可用后在 World 适配；不得在 segment 中凭空填 False。无辅助模型可由管理方固定模型身份提供明确 False。木托架角色能证明观察到接触，真实支承与终点阈值仍须物理验证。

严格 solver 子步采集点、Python 摘要缓存 capture/restore、geom 角色映射目前均未实现。采集必须在 `World.advance()` 内完成，之后走 `read_state → Task.update → checkpoint → state sink`。子步不另存完整世界快照、不增加子步 rewind，日志不能消费摘要。

### 目标区候选接口（尚未切换标准场景）

```python
candidate, failure, metrics = task.evaluate_goal_region(world_state, region)
public_goal = task.goal_region_observation(region)
marker_spec = write_goal_region(asset_dir, region)
```

`region` 是已校验的 `GoalRegion`；候选方法没有自己的稳定计时或成功锁存。接入时须在 declare 固定区域、校验可达性/完整尺寸/剩余系统侧条件并添加 marker，在 `Task.observe()` 提供 `public_goal`，在 `evaluate_state` 调用候选并交给现有 `Task.update` 计稳。区域与目标身份进入正式判据 revision/实例/episode 元数据；不能每 tick 改区去追目标。独立阶段允许显式传区用于测试，正式接入后必须固定为实例配置。

七项原来不完整的 Task 仍为 `goal_complete=False`，没有删除任何 `_goal_gap`。四项已有分离任务保留原 `evaluate_state`，新区域函数尚不成为它们的生效成功规则。Slotted/Orbits 的默认 `evaluate_state` 明确报告目标区未部署；已有 IPC 证据确认连接/体积失效时可以失败。

### 结果与 segment

Task 私有状态已经可由现有 `EpisodeState.task` 保存，也能由通用 TickRecord 编码器输出；无需新增历史循环。Task schema 2 和外层 TickRecord schema 各自版本化。

本轮新增的评估状态位于 `TaskResult.metrics`。当前 `Env._info/public_info` 尚未适配，仍须区分：规则是否完整、本次证据是否可用、是否明确失败。接入后公共反馈只传获准字段/原因码，不公开隐藏 contact/metrics。`terminal_revision`、生效参数和固定目标区身份还需接入已有 episode 元数据；不能由 segment 重新计算任务判断。

## 验收与证据

初轮基础/Env 合同 39 项通过；随后任务与既有 segment 合同 80 项通过。中间完整批次发现 Buzz 容差边界与 Fiber 回溯夹具问题，已修正并针对相关用例复测。以上批次有重叠，不相加。

固定快照分别保留源码/测试/配置及随包资源，`source_hashes.json` 记录每个文件身份。结果如下，批次不能相加：

| 快照 | 范围 | 结果 |
|---|---|---|
| `terminal_independent_20260925_01` | 全部 `tests/unit tests/contracts` | 260 passed；随后补充 Buzz 全程证据覆盖历史 |
| `terminal_independent_20260925_02` | 全部 `tests/unit tests/contracts`，包含当时并行会话新增的候选布局等测试 | 290 passed；随后只调整本轮 Rope 目标序列消费及其测试 |
| `terminal_independent_20260925_03` | 最终 terminal、Task 状态/支持、目标区、Lock 静态限位及全部既有合同测试 | **148 passed**；本轮 33 个实现/测试文件与工作区逐字节哈希一致 |

完整 suite 两轮各有一个已有 Pillow `mode` 弃用提醒，没有测试失败。最终快照以 `_02` 冻结依赖为基础，换入本轮最终的 33 个实现/测试文件，避免把其他会话持续修改的最新工作树称为全部已验收。最终命令在 `_03/source` 执行：

```bash
/home/jianwen/topogym/.venv-gs121/bin/python -m pytest -q \
  tests/unit/test_task_state.py tests/unit/test_terminal_*.py \
  tests/unit/test_goal_region.py tests/unit/test_lock_stop_geometry.py \
  tests/unit/test_task_support.py tests/contracts --junitxml=../pytest.xml
```

结果见[最终报告](../../../runs/test_results/terminal_independent_20260925_03/report.json)、[测试日志](../../../runs/test_results/terminal_independent_20260925_03/pytest.log)、[本轮文件哈希](../../../runs/test_results/terminal_independent_20260925_03/implementation_files.json)。本轮没有启动真实 Genesis 动力学、Nyx 录像或机器人完整解题；静态 FCL 销槽检查不计作机械受力验证。后续按[工程计划第 13 节](../tasks/terminal_judgement_engineering_plan_20260925_zh.md#13-独立工作包实施后的接入边界)接线和验收。
