# horseshoe_codex_001 结果

任务 `horseshoe_ring / remove_ring` **未完成**。执行2段、820个控制ticks（1.64秒仿真时间）后，因本轮宿主累计token用量已超过2,000,000目标预算，solver通过bridge主动停止。服务端最终状态 **`failed`**，`success_within_budget=false`。这是预算原因终止；停止前服务端为ready，未报告物理失败。

初始四路PNG全部通过图像查看工具实际打开后才执行第一次动作。第1段保持辅助抓持，以0.0008rad微扰获得本轮机器人运动学数据，圆环在重力下下垂；第2段让左侧马蹄件绕视觉估计的双端连接区域抬转0.45rad（约25.8°）。两手辅助抓持仍激活，圆环仍挂在连接区域。没有完成取环、放桌、松开和静置验收，也没有验证完整解环路径。

原始bridge采用manual，`usage_measured=false`，其账本0并非零消耗。此次读取当前Codex会话的原生用量元数据和本轮起始标记，发现实际累计已超过预算；没有向bridge伪造/重置/扩展任何用量。预算检查时为2,172,308tokens；终止准备阶段最新宿主快照为 **2,385,756 tokens**（输入2,371,405，输出14,351）。缓存输入2,170,112已包含在输入中，没有重复相加；推理输出也已包含在输出中。最终回复及后续记录还可能增加用量，因此最新快照是完整本轮用量的下界，**明确不满足2M预算验收**。

证据：

- [终态observe](final_observation.json)、[stop返回](stop_response.json)、[结构化结果](result.json)。
- [本轮计量快照与基线](analysis/native_usage_monitor.json)、[每段依据与结果](notes.md)。
- [最终段manifest](feedback/segment_002/manifest.json)、[高位图](feedback/segment_002/cam_high/000340.png)、[低位图](feedback/segment_002/cam_low/000340.png)、[左腕图](feedback/segment_002/cam_left_wrist/000340.png)、[右腕图](feedback/segment_002/cam_right_wrist/000340.png)。
- [第一动作脚本](policies/segment_001.py)、[第二动作脚本](policies/segment_002.py)、[本轮运动学拟合](analysis/robot_fit.json)、[第二段规划](analysis/segment_002_plan.json)。

工具与来源：任务包SOLVER_INSTRUCTIONS.md、TASK_BRIEF.md、task_spec.json、bridge_config.json；本轮bridge返回的RGB、机器人和相机观测；Python、NumPy、SciPy、Pillow、本地图像查看工具。仅将当前会话token计数元数据用于预算管理，不将其他任务内容用于本任务几何或动作建模。allow_internet=false，无联网研究；未读取已有demo、源码、解法、私有资产、其他试验文件或环境内部状态；未启动、重启、复制、重置或回滚环境。

限制：同一聊天已有其他任务的历史上下文，不能宣称严格隔离的全新会话。本轮几何与运动学均由本轮公开输入新建，没有复制旧文件。马蹄件连接轴为视觉估计，尚未验证取环拓扑操作和完整碰撞路径。接口含接触触发辅助抓持；任务为pilot，physics_qualified=false，不构成完整物理资格验收。
