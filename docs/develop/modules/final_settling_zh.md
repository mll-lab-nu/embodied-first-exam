# 公共终态确认：夹爪离开后的稳定

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

日期：2026-09-27。实现范围按用户最新确认收窄：公共模块确认物体在解除辅助、机器人离开后持续稳定；具体装配、入区、桌面或托架位置要求属于各任务。

`declare()` 和 `finalize_spec()` 是 `topogym/tasks/base.py` 中 Task 类的方法，不是目录；分别用于声明场景实体和结合实际场景完成配置。新公共确认入口是 `final_settling_spec()`，不要求新建这两个名字的目录，也不要求任务重做场景声明。

## 1. 运行链

```text
Task.evaluate_state / evaluate_transition → 任务目标与失败
evaluation/terminal/evaluate_settling      → 解除辅助、离开、速度、漂移
TaskDefinition.update                    → 共同连续成立才累计 stable_duration_s
Env                                      → 保存当前 tick，成功/失败时结束
```

只保留 `TaskDefinition` 已有的一个确认时钟。任一必需条件失效或证据不可用，确认时间和漂移参考归零；首次满足从 0 开始。物体重新接触、assist 重新开启、速度或累计漂移超限、任务目标失效，都需要重新确认。失败仍即时优先。查询不推进时间，重复 tick 幂等，time limit 仍是 truncation。

公共模块不读取 planner 的“完成”标签，也不自动开夹爪或推进物理。策略必须继续通过正常 step 提供确认时长。所谓最终动作完成，以任务目标和实际状态为依据。

## 2. 接入方式

```python
from topogym.evaluation.terminal import SettlingSpec

def final_settling_spec(self):
    return SettlingSpec(
        rigid_targets=("part",),
        clearance_m=.005,
        maximum_speed_m_s=.001,
        maximum_angular_speed_rad_s=.02,
        maximum_drift_m=.001,
        maximum_rotation_drift_rad=.02,
    )
```

软体选择 `fem_targets` 或 `particle_targets`。FEM 测量全部材料顶点；PBD 测量全部粒子并为包围盒添加 `particle_radius_m`。Blanket 使用其现有粒子尺寸作为保守膨胀量，并沿用自身速度/漂移阈值。默认返回 None，允许握持的任务不增加释放要求。

`evaluate_state()` / `evaluate_transition()` 仍是任务自身候选条件；最终成功必须读取经 `update()` 产生的 `TaskResult`。不能把直接调用任务候选函数的 True 当作完整 terminal。

## 3. 证据与边界

- `World` 按需启用 `physics/release_geometry.py`；缓存局部碰撞几何范围，读取当前原生 world-frame geom 位姿，输出保守世界包围盒。解析球/盒/圆柱的完整解析尺寸与 mesh 的顶点范围，不把 visual 网格用于释放判断。未知碰撞类型返回覆盖不足。
- 检查整个机器人碰撞几何，覆盖手指、掌部和手臂。包围盒之间的距离是表面距离下界，满足间距可以确认分开；重叠会保守阻断，可能需要撤得更远。软体使用整体包围盒，较为保守。
- assist 使用全局活动状态；所有辅助解除才允许确认。启用确认的 World 还会核对 manager 绑定与原生约束。当前尚不采用“忽略其他物体上的辅助”的目标级优化。
- 当前检查范围是每个 physics tick 末端，不能声称连续时间内从未接触，也不证明长期永久稳定。真实重力下持续无辅助、无机器人接触的低速及低漂移，是本模块的确认依据。
- 本模块不求解桌面承载力、支撑接触图或通用力平衡。Coil 自己补充接近桌面及实际桌面 XY 包围范围的必要几何条件；Buzz 保留指定托架接触；Knot/Blanket 保留贴桌/高度与各自形状条件。这些几何条件不单独构成承载证明。
- 缺 assist/几何证据或明确不支持的几何覆盖，返回 unavailable，不累计时间；已经提供但过期、非有限或损坏的数据抛出错误，不能默认当作释放。

默认间隙 5 mm、刚体速度 1 mm/s、角速度 0.02 rad/s、漂移 1 mm、转角漂移 0.02 rad 是当前工程阈值，尚未进行新的真实物理标定。各 Task 可通过 spec 使用自身阈值。

## 4. 本次修改

| 文件 | 内容 |
|---|---|
| `topogym/evaluation/terminal/settling.py` | 无引擎依赖的释放、间隙、速度与漂移计算及参考状态校验 |
| `topogym/tasks/base.py` | 统一组合终态条件，复用原计时，将漂移参考纳入原子提交/快照/恢复及元数据 |
| `topogym/world/physics/release_geometry.py` | 原生碰撞几何的保守范围采集，无物理推进与历史 |
| `topogym/world/genesis_world.py` | 按需开启证据、读取时核对 assist 绑定；恢复后从真实位姿重新计算证据 |
| `topogym/simulator/env.py` | reset 时按 Task spec 接线 |
| Coil/Buzz/Knot/Blanket 的 `common.py` | 声明最终确认目标，更新 terminal_revision；Coil 补接近桌面的必要条件；Blanket 删除独立漂移参考和定制 update/恢复 |
| `tests/unit/test_terminal_settling.py`、`test_terminal_cast_coil.py` | 公共正反例、三档 Coil 反例、计时/回溯/缺证据测试 |
| `tests/integration/test_terminal_runtime.py` | 补 Coil/Blanket 的实际出生/回溯入口，检查释放证据与恢复一致 |

计时 checkpoint 继续使用原 schema 2；启用任务增加必需的 `final_settling` schema 1 子记录，缺失或与活动窗口矛盾的记录拒绝恢复。任务 terminal_revision 已升级，旧实例快照不能冒充新判据。未启用任务保持原格式。公共输出仍通过原有过滤器，详细几何和数值诊断仅用于管理侧证据。

四项任务均接入后验确认，但 Buzz/Knot 原有 `goal_complete=False` 保留；不以公共能力接线代替完整任务资格。

## 5. 验证命令

本轮新增的 31 项释放后稳定/三档 Coil 合成测试通过；扩大回归为 442 passed / 5 failed。其一为沙箱禁止 Unix socket.bind，沙箱外单独重跑 1 passed。另四项涉及未改动的 Knot medium `planar_scale_m` 旧断言（三项）和现有 `planning/cast_coil`、`planning/lock_picking` 目录与架构规则冲突（一项）。没有把它们通过修改任务参数或放宽规则来隐藏。新增集成入口只做收集检查，15 项成功收集，未执行 GPU 物理测试。

```bash
.venv-gs121-nyx/bin/python -m pytest tests/unit tests/contracts tests/architecture -q
```

当前会话 CUDA 检查返回 `False`、设备数为 0，未执行新的真实 Genesis/Nyx 验收。具备 GPU 的环境使用现有统一入口，产物、配置/源码身份和录像由其证据模块保存：

```bash
.venv-gs121-nyx/bin/python scripts/test_base_tasks.py \
  --checks terminal --tasks cast_coil buzz_wire_3d knot_untying blanket_flatten \
  --variation easy --device cuda
```

该命令使用独立输出目录，记录真实出生、逐 tick 证据和回溯；机制测试不等于完整机器人任务成功。可另用 `--variation medium` / `hard` 分别验证已实现的对应入口。
