# Terminal 判据与执行链接入记录

日期：2026-09-26。用户授权按[工程计划](../tasks/terminal_judgement_engineering_plan_20260925_zh.md)完成独立工作包之后的接入。本轮已实现监测、判定、恢复、公开反馈和六项绿色区域的代码；**真实物理资格尚未完成，不能把单元测试通过写成任务已 solved**。

## 已接通的行为

Buzz 的金属工具触碰金属线时，`TaskResult` 当 tick 终止失败；零接触力不会把已发生的触碰过滤掉。工具木柄碰线、金属工具碰木挡块不算电气触线。事件来自场景级采集器包装的刚体 `substep`，包含 expected/sampled 子步数和语义覆盖。采样清理 Genesis 查询缓存，避免拿到前一个子步结果；负 penetration 的分离候选忽略。一次控制 action 中剩余物理 ticks 不再执行。

角色在 build 前映射：Genesis build 会把自由刚体局部几何重新表达为质心主轴坐标，不能在 build 后直接拿这些坐标与原 URDF 比较。映射依据 link、形状参数、局部位姿及 mesh 文件身份；不依赖导入数组顺序。未知/缺失形状使覆盖不完整。摘要可重复查询并随 World checkpoint 恢复，不由 segment 回调重新采样。采集适配限于当前 Genesis 1.2.1 刚体路径；IPC 与连续时间 CCD 仍明确不覆盖。

成功资格和已知失败分开。`goal_evaluation_complete=False` 不屏蔽明确的 `wire_touched`；`evaluation_status=unavailable` 也不再被公共层重写成可评估。证据不可用不能推进成功稳定窗口。`task_outcome` 为 success/failure/ongoing/unknown；公开失败原因限于 wire_touched/task_failed，任意内部错误和坐标不会因此泄漏。Task checkpoint 保存新结果字段；规则 revision 进入实例哈希、episode metadata 和公共结果。

Keyhole、Horseshoe、Hedgehog、Claws、Slotted、Orbits 在 Env reset 声明阶段部署固定绿色虚线。完整视觉/碰撞几何或全部 FEM 顶点必须入区，其余系统几何保持在分界另一侧，目标低速持续满足。Orbits 包含整绳和木柄，Claws 指定棕色件。继续抓持允许。区域与边框同源，标记无碰撞；默认算法避开机器人底座并确保区域处在真实桌面范围内。目标区数值、身份、速度阈值和稳定时长留在管理方 metadata；limited policy 通过既有 profile 接收静态任务说明和 RGB。

五项非区域新规则采用 `terminal_v2`，六项区域采用 `placement_region_v1`；未改规则的任务保持 `legacy_v1`。四项旧分离任务不能把旧成功资格移交新区域规则，现已补 solve gap。十一项规则会实际计算诊断和失败，但成功资格仍关闭。Cast Coil / Blanket 的既有规则不在这次资格切换范围。

## 文件与 segment 衔接

详细目录见工程计划第 14 节。新增运行模块只有 `tasks/placement.py`、`world/physics/rigid_contacts.py`。增量修改 `tasks/base.py`、十一项任务 common、Buzz 生成器、`world/genesis_world.py/state.py`、`simulator/env.py/interaction.py`、`simulator/rollout_simulation/policy.py`、registry 和六项任务卡。

新 segment 的单参数 `act(obs)`、`execution_state`、权限守卫、同 tick 保存顺序和最终通知保持现有实现。`public_info` 的实际定义在 `simulator/interaction.py`，`rollout_simulation/segment_contract.py` 复用它。现有 evidence 编码支持嵌套测量，不需要重写 `evidence.py`、history 或 privileged。合同测试覆盖终止后无额外 act/step、最终反馈、原始事件与 Task 结果同 tick 写入、rewind 去掉已作废失败。

## 验证与限制

初次广泛回归：unit/contracts/architecture/recording_data **398 passed、1 deselected**。随后对 build 前角色映射、区域接线和指令作了增量修正；最终固定源码回归结果见本页后续记录及报告，不用这次中间结果代替最终源码验收。

真实验收入口为 `scripts/test_base_tasks.py --checks terminal`，新增 `tests/integration/test_terminal_runtime.py` 共 13 个参数化用例。覆盖十一项出生/默认时序/恢复，以及 Lock 单转子隔离受力正反例。Lock 两种模式都移除测试资产的 URDF 角度限位，分别保留和移除实体外环，施加已记录转矩并检查方向反转、端点阻挡、负对照越界和 replay。Buzz 用管理方明确记录的位姿干预制造触线；这是机制探针，**不是机器人完成任务的 demonstration**。

首次实际运行在 CUDA 预检处失败：`torch.cuda.is_available() == False`，`nvidia-smi` 也无法连接驱动。没有推进物理、没有录像，未以 CPU 或其他 renderer 代替。已保存[硬件失败报告](../../../runs/test_results/terminal_runtime_20260926_01/terminal_buzz_wire_3d/report.json)、[源码与结果](../../../runs/test_results/terminal_runtime_20260926_01/summary.json)。此快照是预检时版本，之后的代码修改有单独最终快照。

驱动恢复后执行（现有准备好的 Nyx 资产位于 `.external/nyx-assets`；若部署位置不同，增加 `--visual-asset-root /实际目录`）：

```bash
.venv-gs121-nyx/bin/python scripts/test_base_tasks.py \
  --checks terminal \
  --tasks buzz_wire_3d lock_picking fiber_bundling rope_threading knot_untying \
          cast_keyhole horseshoe_ring hedgehog_in_cage interlocked_claws slotted_post_ring orbits \
  --output runs/test_results/terminal_runtime_cuda_20260926
```

这个命令通过也只增加机制/接线证据，不会自动启用 solve。剩余资格包括：

| 剩余项 | 相关脚本 | 需要的证据 |
|---|---|---|
| Buzz 实际覆盖与支承 | `tests/integration/test_terminal_runtime.py`、`world/physics/rigid_contacts.py`、Buzz common | 当前默认实例出生不触线、短暂触线/零力接触、木支架区分、终点支承和时间步敏感性 |
| Lock 实体限位 | 同一 integration 脚本、Lock 资产及 common | 去掉软件限位后转矩仍被实体槽挡住；无外环负对照能越界；反转脱离及 rewind |
| 六区域可达与视觉 | `tasks/placement.py`、六 common、机器人策略/现有 SegmentRunner | Nyx 边框、完整目标放置、夹爪接近撤离、绳柄完整容纳；几何排布不能替代这些证据 |
| 各任务成功阈值 | 各 common、`evaluation/task_metrics.py`、registry | 真实成功与接近边界的反例；用实测校准后同步改资格和任务卡 |

无需 segment 再提供新的 action schema 或 snapshot 接口。后续若统一 assist 接入，World 的 `assist_active=False/assist_model=none` 必须替换为真实约束状态；不能继续硬编码无辅助。当前项目尚未提供该 assist 模型，本轮字段准确描述当前无辅助的 World。

## 最终固定源码结果

| 范围 | 结果 | 证据 |
|---|---|---|
| 固定快照全量 unit/contracts/architecture/recording_data | 400 passed、1 deselected | [报告](../../../runs/test_results/terminal_integration_20260926_01/report.json)、[日志](../../../runs/test_results/terminal_integration_20260926_01/pytest.log) |
| 六类区域的全部 16 个已集成具体变体：真实资产生成、静态区域布置 | 16/16 passed；不包含机器人可达性 | [逐实例区域及资格](../../../runs/test_results/terminal_integration_20260926_01/all_regions.json) |
| 最终增量快照：terminal、子步事件、Env/segment/rewind、架构；补回四项刚体物理失败检查 | 199 passed | [最终报告](../../../runs/test_results/terminal_integration_20260926_02/report.json)、[日志](../../../runs/test_results/terminal_integration_20260926_02/pytest.log)、[源码哈希](../../../runs/test_results/terminal_integration_20260926_02/source_hashes.json) |
| 真实 CUDA / Nyx 机制验收 | 硬件预检失败，未执行物理，未生成视频 | [报告](../../../runs/test_results/terminal_runtime_20260926_01/terminal_buzz_wire_3d/report.json) |

最终快照相对全量回归快照只修改 `tasks/placement.py`、Horseshoe common、`test_terminal_region_deployment.py`：新目标保留刚体任务既有的掉落、非有限状态、过度穿透失败条件，修正旧的目标 metadata 描述，并增加负例。最终 199 项覆盖这些变更；两批计数有重合，不相加成独立用例数。最终快照中的 625 个文件与收尾时工作区哈希一致。静态区域算法在两份快照间没有变化，16 例排布结果仍适用。
