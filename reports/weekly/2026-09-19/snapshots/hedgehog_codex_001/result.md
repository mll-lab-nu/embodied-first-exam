# Hedgehog in Cage 本轮结果

- 运行 ID：`hedgehog_codex_001`；任务：`hedgehog_in_cage / extract_release`。
- 服务端终态：**failed**。主动调用 stop；未完成取出、桌面放置、松爪和稳定静置。
- 完成 **7 段，2010 ticks，10.050 秒控制时间**。
- 最后动作后仍为 ready，未出现服务端自动物理失败；本次 failed 来自 solver 明确停止，不表示谜题不可解。

## 操作与结果

| 段 | ticks | 操作与反馈 |
| --- | ---: | --- |
| 001 | 410 | 保持闭合目标并逐关节微探测0.0002rad；接触辅助由未附着变为有效。用本轮公开位姿核对通用Panda运动学，位置误差约1.2e-15m。 |
| 002 | 140 | 向-y平移3mm，实际约3.1mm。attempt01因循环语法被预检查拒绝，未执行；改为range后以attempt02提交。 |
| 003 | 190 | 向-x,-y斜移5mm、6mm，实际与目标基本相符。 |
| 004 | 360 | 继续斜移12mm、15mm，实际约19mm；图像显示球核更多露出笼柱外侧。 |
| 005 | 330 | 目标斜移约29mm，仅实现约10mm，开口变大；明显接触受阻。 |
| 006 | 250 | 围绕估计球核、沿出口方向轴旋转0.25rad，实际约0.225rad；夹持保持有效。 |
| 007 | 330 | 再向外移动目标约39mm，仅实现约7.5mm；刺球仍与笼柱交错。 |

停止原因：只建立了局部取出进展，没有找到让全部刺越过笼柱的可靠姿态与路径。最新原生计量已接近2M，剩余预算还需覆盖终态确认和报告，无法可靠完成进一步几何辨识、取出及桌面释放。没有把名义IK目标或ready误判为成功，也没有执行未验证的远距离强拉。

## 关键证据

- 初始 prompt：`observations/b055b8fe-2f06-44a0-87cb-d8060b83a88d/prompt.txt`。
- 初始 manifest：`feedback/initial/manifest.json`。首次动作前已用图像工具实际打开 `agentview/000000.png`、`front_oblique/000000.png`、`wrist/000000.png`。
- 各段动作：`policies/segment_001.py` 至 `segment_007.py`；每段前后依据与结果见 `notes.md`。
- 最后反馈：`feedback/segment_007/manifest.json`，已实际查看其中 `front_oblique/000330.png` 与 `wrist/000330.png`。
- 请求：`requests/seg007_attempt01.json` 与 `requests/seg007_attempt01.result.json`。其他段同格式，段002有效请求为 `seg002_attempt02`。
- 停止响应：`stop_response.json`；最终observe：`final_observation.json`；最终prompt：`/home/jianwen/topogym/runs/agent_test_demos/agent_solutions/hedgehog_codex_001/observations/f388727f-3a36-4fab-9a6a-5422d43b5e87/prompt.txt`。
- 几何假设：`analysis/cage_fit.json` 与投影叠图；全部根据本轮RGB建立，不是真实物体几何。

## token 计量

bridge 为 **manual**，`usage_measured=false`：其账本未接入原生 Codex usage；仅据 bridge，token 用量未测量，真实余额未知。执行中另行只读取了宿主原生 token_count 元数据及本轮请求边界，未读取其他试验内容，也未改动bridge账本。

截至最近已落盘的原生记录：输入 **1,913,436**，输出 **20,731**，合计 **1,934,167 tokens**。其中缓存输入 **1,806,976** 已含于输入总量，未重复相加。详情见 `analysis/token_usage_latest.json`。

这个快照不包含之后尚未记入的终态报告及最终答复，不能当作整个episode最终总量，也**不能证明通过2M预算验收**。环境未成功，不声明success_within_budget。

## 信息来源与未验证项

仅任务包、本轮bridge观测和通用Panda串联运动学知识；使用Python、NumPy、SciPy、OpenCV和实际PNG查看，没有联网、读取仓库实现/demo/解法/私有资产或其他试验文件，没有重启、回滚或复制环境。宿主日志访问仅用于本轮计量边界和计数。此对话含其他任务的先前上下文，不是全新隔离会话；本轮未采用其物体参数或轨迹。

尚未验证：完整刺球几何与所有刺的碰撞路径、最终取出姿态、松爪后桌面稳定静置、整个episode精确最终token总量。接口和任务目标明确，基础关节控制与接触辅助可用；主要卡点是受遮挡的刺/笼柱几何及受接触约束的后续路径规划。任务包声明physics_qualified=false，本轮也不提供完整物理资格证明。
