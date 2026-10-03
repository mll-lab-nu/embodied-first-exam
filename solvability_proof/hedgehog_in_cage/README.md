# Hedgehog in Cage 可解性证明

当前三个默认参数、seed 0 实例均已完成：**easy / medium / hard，3/3**。每档都有纯物体路线、机械臂 IK、默认 home 开始的连续原生成功、独立逐 tick 审计和独立证据副本；[机器汇总](summary.json)绑定各自的模型、源码及实例身份。

| 变体 | 模型修订 | 原生执行与独立审计 |
| --- | --- | --- |
| easy | `simulator_v1` | [正式证明](2026-09-30_easy/README.md)：两次抓取，238.875 s，9,556 个状态 |
| medium | `waisted4_dark_wood_v1` | [正式证明](2026-09-30/README.md)：四腰窗取出，56.5 s，2,261 个状态 |
| hard | `fixed_v3_s5_post` | [正式证明](2026-10-03_hard_s5_post/README.md)：高位支座起步，一次抓持从顶部转出，150.725 s，6,030 个状态 |

hard 采用用户 2026-10-03 批准的半径 8 mm 固定内支座、球心 z=72 mm 的 S5 站立初态，省去旧模型的笼底取球和中途换抓。初态严格无相交，保留原笼柱、顶孔、六刺尺寸及目标规则；[原生成功](2026-10-03_hard_s5_post/evidence/runs/native_03/oracle_report.json)和[独立审计](2026-10-03_hard_s5_post/evidence/runs/native_audit_02/execution_audit.json)均通过。旧 `fixed_v2` 未获得完整证明，不继承此次资格；easy 和 medium 原归档保持原样。

hard 解法先转向升至约 98 mm，边转边降到约 82 mm，再倾斜上提至 118 mm，最终升至 230 mm 完全出笼，随后进入原目标区低速保持 2 s。固定朝向直拔被阻挡，但封闭窄槽后同一路线仍通过；这证明当前自定义模型的顶部通路，不能据此认定窄槽必需或复现了实物 GEN 的解锁机制。

三档均为 Panda + Robotiq、真实接触触发的 `contact_weld_v1` 辅助抓持、CPU float64、25 ms tick / 40 子步、40 Hz action 与 Task 检查。证据覆盖保存的 tick 末状态，不构成纯摩擦、连续时间/全部积分子步、其他 seed 或整个参数域的证明；本轮没有新增 RGB/视频。hard 已使用 v12 刚体性能配置并在最终资源上重新验证。详见各批次范围、完整状态、动作、冻结源码和 SHA-256 清单。

历史失败、模型候选和恢复记录保留在[研究检查点](../../runs/hedgehog_three_20260930/progress.json)，不增加完成数；[任务说明](../../docs/develop/tasks/hedgehog_in_cage_zh.md)保留研究过程和当前正式入口。

[范围补查](2026-10-03_scope_review/README.md)确认 hard 终态也满足旧目标框的 2 s 要求；新初态的自动目标框数值略有变化。easy、medium 的当前资产与目标区不变，原生成功仍绑定原 v2 冻结终态版本，本轮未重新执行它们。
