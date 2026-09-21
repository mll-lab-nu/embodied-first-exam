# cast_coil_codex_002 结果

任务 `cast_coil / assemble` 未完成。服务端最终状态为 **`failed`**：solver 在确认无法继续后调用 `stop`，不是装配成功，也不是评测器检测到装配穿透所导致的失败。

- 已执行 **64 段，29,735 个控制 ticks**，累计仿真时间 74.3375 秒。
- 最终金色件直立、银色件平放，两件仍分离在桌面；未建立并验证目标装配关系。
- 已停止提交动作。没有重启、复制、重置、回滚环境或修改评测器、物理参数和 simulator state。

无法继续的直接依据是右夹爪持续不响应张开指令。第 60 段双手接近过程中出现夹爪/支架干涉，右夹爪随后闭合；第 61–62 段张开指令没有恢复开度。第 63 段通过正常关节动作将右臂撤到空旷的初始关节姿态，并执行闭合后全开；第 64 段又用仅夹爪指令检查，右侧轨道位移仍约为 `[0.00722039, 0.00719878] m`。作为对照，左夹爪正常响应 0.026 和 0.032 m 指令。这是轨道位移，不是夹持垫之间的开口。公开观测不足以确定内部故障原因，不能断言具体机械损坏或仿真缺陷。

前面的单手姿态调整多次出现滑转和掉落，尝试接触配合也没有验证穿入。随后规划的双手约束翻转尚未实现；右夹爪恢复尝试无效后，本 solver 无法继续可靠抓取和装配，按规则终止。

证据与产物：

- [服务端终态观察](final_observation.json) 与 [结构化结果](result.json)。
- [每段前后依据与结果](notes.md)、[动作脚本](policies/)、[本轮反馈](feedback/)。
- [最终段 manifest](feedback/segment_064/manifest.json)、[最终高位图](feedback/segment_064/cam_high/000360.png)、[最终低位图](feedback/segment_064/cam_low/000360.png)、[最终右腕图](feedback/segment_064/cam_right_wrist/000360.png)。
- [夹爪指令与实测响应曲线](analysis/gripper_response_060_064.png)、[恢复检查数据](analysis/gripper_response_063_064.json)。
- [异常闭合开始时的低位图](feedback/segment_060/cam_low/000483.png) 与 [右腕图](feedback/segment_060/cam_right_wrist/000483.png)。

运行时 bridge 计量：`usage_mode=manual`，`usage_measured=false`，当时未接入真实用量，余额未知。服务端 `success_within_budget=false`。以下事后审计补充了宿主实际记录，原始 bridge 账本和终态均未改动。

来源与工具：仅使用本轮任务包、bridge 返回的 RGB/关节/相机观测，以及本目录内自行生成的分析和动作文件；多视角图片均通过图像查看工具实际查看。使用 Python、NumPy、SciPy、OpenCV、Pillow、Matplotlib 和通用优化方法建立本轮 FK/IK 与视觉几何假设。`allow_internet=true`，但求解执行期间没有使用联网研究、外部物体参考或外部解法；没有读取其他目录的源码、demo、解法或旧试验记录。

评测限制：本轮沿用含上一轮交互内容的聊天上下文，初始 notes 已披露该信息暴露，不能认定为严格隔离的独立从头测试。本轮视觉尺寸和相对构型属于未完全验证的估计，不是参考真值。任务为 pilot evaluator，`physics_qualified=false`，本结果不构成完整物理验收。

## 2026-09-19 事后 token 核查

应用户在任务终止后的请求，读取当前 Codex 会话原生日志中的用量元数据和本轮起止标记，得到本轮累计 **69,452,496 tokens**。这不是估算，也不是整个聊天的累计值，而是宿主累计计数之差：`73,969,309 − 4,516,813`。

| 项目 | Tokens |
| --- | ---: |
| 输入合计 | 69,104,770 |
| 其中缓存输入（已包含在输入中） | 67,126,272 |
| 输出合计 | 347,726 |
| 其中推理输出（已包含在输出中） | 199,051 |
| 输入 + 输出 | **69,452,496** |

口径为本轮002启动用户消息之前的最后一个累计计数，到本轮最终答复结束后的累计计数；排除了此前001及解释消息，也排除了之后的讨论和本次核查。542次非零累计更新均与对应 `last_token_usage` 一致，未发现计数下降；重复的 `token_count` 事件未重复相加。重复上下文及缓存输入按本任务预算定义计入总输入。

因此本轮用量为2,000,000目标预算的 **34.726248 倍**，超过67,452,496 tokens，**不满足2M预算要求**。这是事后宿主日志核查，不是运行时自动计量或账单金额审计；原始 `usage_measured=false` 仍描述当时的bridge计量状态，新增 `usage_measured_posthoc=true` 描述本次核查。

原始计数、边界时间、日志行号与方法见 [token_usage_posthoc.json](analysis/token_usage_posthoc.json)。核查时另查阅了[官方 App Server 文档](https://learn.chatgpt.com/docs/app-server#turn-events)，其中说明了 `thread/tokenUsage/updated` 会话用量通知。此次文档查询发生在机器人任务终止之后；没有重开环境或读取其他项目、试验源码与解法。
