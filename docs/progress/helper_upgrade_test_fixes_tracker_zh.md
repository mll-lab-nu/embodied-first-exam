# Helper 升级与两个测试文件修复：工程目标与进度

> 最后核对：2026-10-06（`dev/jianwen`，HEAD `2f3233023`）。每次推进后更新本页的状态表与变更记录。

## 1. 目标

本项完成时须满足以下四条，缺一不收口：

1. `ci_checks/test-harbor-simple-policy-context.py` 整文件通过（3 个用例）。
2. `ci_checks/test-cast-keyhole-oracle.py` 整文件通过（15 个用例）。
3. 两项接口语义（grasp_assist 类型、proof 起点）有书面决定，写在本页第 3 节，代码与测试按决定一致。
4. helper 仓库（<https://github.com/LUIGIVAMPER/topogym-sweep-release-v1>）升级到确定的目标版本，并记录升级后的测试结果。

**背景**：10 月 5 日的 merge `b1ab6b18d` 保留了协作方的两项 oracle 修复 FIX 2（`89cb08674`）和 FIX 5（`3bdc3a68e`），而 policy context 测试仍按旧约定写，因此在 merge 前的 `a8bbd5c12` 上通过、merge 后失败。keyhole 测试在 `a8bbd5c12` 上已失败，与 merge 无关。两类失败的修复记录分开写。

## 2. 状态总表

| # | 事项 | 失败用例 | 根因一句话 | 待决定 | 状态 |
| - | - | - | - | - | - |
| F1 | grasp_assist 类型 | `Context.test_actual_claws_and_lock_initializers_receive_declared_contract`（error） | `harbor_bridge/actions.py:117` 用 `dataclasses.asdict(...)`，测试的假 config 传 dict，`asdict` 抛 `TypeError` | 已定：只收 dataclass，改测试 | **测试已改，未提交**：假 config 改传 `GraspAssistConfig(model="contact_weld_v1", targets=(GraspTarget("part", "base"),))`；启用的辅助抓持必须带目标，所以补了一个最小目标 |
| F2 | proof 起点语义 | `FrozenOrigin.test_bound_restored_origin_is_not_a_standalone_birth_proof`（failure） | `solvability.py:155-157` 在 proof 模式接受 Harbor 恢复后的起点（`branch_id=1`、`state_id=0`、`physics_step=0`），测试期望拒绝并报 `fresh episode birth` | 已定：保留 FIX 5 | **测试已改，未提交**：用例改名为 `test_bound_restored_origin_is_a_proof_birth`，proof 接受该起点；新增两项检查，`state_id=1` 或 `physics_step=1` 时 proof 仍拒绝；session 部分不变 |
| F3 | keyhole 假 session | 3 个 `AttributeError: ... no attribute 'action_layout'` | `cast_keyhole/public_session.py` 调 `harbor_bridge.actions.public_row`，后者读 `session.action_layout`，测试的 `SimpleNamespace` 没有 | 无 | **已提交**（`99c3d27b0`）：测试补 `action_layout=['left/j0','left/j1','left/gripper']`，本机 15/15 通过 |
| H | helper 升级 | — | 正式 sweep 仍冻结在 v17（tag `rigid-v17-20261006-diagnostics01`）；v18 release 已导出 | 目标是 v18 还是 v19 | **待定目标版本** |

## 3. 待决定事项与选项

### F1 grasp_assist：接口是否接受 dict

场景：`SessionPolicyRunner.run_policy` 在调用 `policy.initialize(...)` 前，把 `env.config.grasp_assist` 转成 JSON 写进 `action_spec["grasp_assist"]`。真实 `Env` 里这是 dataclass；测试的假 config 里是 dict。

| 选项 | 改哪里 | 代价 |
| - | - | - |
| A. 实现改用 `topogym/utils/io.py:81` 的 `to_jsonable(...)` | `actions.py` 一行 | 接口变宽：dict 也能通过，不再与 `Env.action_spec`、`SegmentRunner` 的 `asdict` 写法完全一致 |
| B. 实现不动，测试改传 dataclass | 测试一处 | 接口保持只收 dataclass；测试需要构造真实的 grasp_assist 配置类 |

建议 B：生产路径只会遇到 dataclass，失败来自测试数据而非实现。

决定：2026-10-06 选 B，实现不动，只改测试。

### F2 proof 起点：Harbor 恢复后的起点算不算 episode 起点

场景：Harbor session 开始时，owner 恢复冻结的初态，于是 `branch_id` 从 0 变成 1，但 `state_id=0`、`physics_step=0`，机器人还没动过。问题是从这一点开始的连续运行能否算 proof（完整可解性证明）。

| 选项 | 需要改 | 需要重验 |
| - | - | - |
| A. 保留 FIX 5 | 测试改为 proof 接受该起点；session 模式保留 | 补一条测试：proof 仍拒绝 `n_steps>0`、reset、未绑定检查点、`physics_step≠0`（现有 `test_progress_reset_unbound_or_wrong_checkpoint_cannot_be_new_origin` 已覆盖一部分，需核对） |
| B. 撤掉 FIX 5，该起点只走 session | 回退 `solvability.py:155-166`；Harbor 下的 oracle 调用改用 `mode="session"`（已知调用方：`scripts/oracle_runners/run_horseshoe_oracle.py`，需全量搜索） | 所有此前在 Harbor 下以 proof 模式跑过的 oracle 重跑；其 `accepted_proof` 结论失效 |

取舍：A 不需要重跑物理；B 语义更严（proof 只认 `branch_id=0` 的原始起点），但重跑成本按 oracle 数量计。决定须与 Harbor oracle 检验口径一致。

决定：2026-10-06 选 A，保留 FIX 5（协作方提交 `3bdc3a68e`）。不需要重跑 oracle。

### H helper 目标版本

| 版本 | 现状（本机核对） |
| - | - |
| v17 | 当前正式 sweep 冻结版本；诊断 tag `rigid-v17-20261006-diagnostics01`（commit `cd6138070`） |
| v18 | 开发仓库 `d6242c65b` 已导出 `merged-v18-rigid`（48 个任务包）；本地 release 仓库 `~/helper-releases/topogym-rigid-v18-20261006-01` 有 tag `rigid-v18-20261006-01`、`-02`，本地 HEAD `fc21e12` 比 `origin/main`（`e2b0001`）多一个提交，尚未推送 |
| v19 | 未见任何导出或 tag |

决定：目标版本 _（待填）_；最终 tag _（待填）_。

## 4. 验收步骤

本机需用有 `python-fcl` 的环境，系统 `python` 缺 `fcl` 会在导入阶段失败：

```bash
.venv-gs121/bin/python ci_checks/test-harbor-simple-policy-context.py
.venv-gs121/bin/python ci_checks/test-cast-keyhole-oracle.py
```

- [x] F1 按决定修改，policy context 中该用例通过（未提交）
- [x] F2 按决定修改，该用例通过（选 A，无需重跑 oracle；未提交）
- [x] F3 提交（`99c3d27b0`，随 below-easy oracle 一并提交，不是单独的修复提交）
- [x] 两个测试文件整文件结果记入第 5 节
- [ ] 提交 F1/F2 的测试改动
- [ ] helper 目标版本确定、推送、tag 核对，升级后两个测试文件及 release 自带检查的结果记入第 5 节

## 5. 测试结果记录

| 日期 | 代码版本 | policy context | keyhole | 备注 |
| - | - | - | - | - |
| 2026-10-06 | HEAD `d6242c65b` + 暂存改动 | 3 用例：1 error（F1）、1 failure（F2）、1 pass | 15/15 OK | keyhole 通过依赖当时未提交的测试改动 |
| 2026-10-06 | HEAD `2f3233023` + 测试改动 | 3/3 OK | 15/15 OK | F1/F2 测试改动未提交；修复前后逐用例日志见 [runs/test_results/helper_test_fixes_20261006/](../../runs/test_results/helper_test_fixes_20261006/README.md)（runs/ 被 gitignore，只在本机） |

## 6. 变更记录

- 2026-10-06：建立本页；复现 F1、F2；确认 F3 已在工作区修复但未提交；核对 helper v17/v18 现状。
- 2026-10-06：Jianwen 决定 F1 选 B、F2 选 A（保留 FIX 5）；改测试后两个文件整文件通过；F3 已随 `99c3d27b0` 提交。剩 helper 目标版本。
