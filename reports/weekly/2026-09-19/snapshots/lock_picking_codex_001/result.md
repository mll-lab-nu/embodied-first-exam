# Lock Picking 本轮结果

- 任务：`lock_picking` / `insert_release`
- 运行 ID：`lock_picking_codex_001`
- 环境最终状态：**failed**
- evaluator 原因：**`Key/fixture contact force exceeded 10 N`**（钥匙与机构总接触力超过 10 N）。
- 累计执行 10 段：前 9 段完整执行，第 10 段执行 157/260 控制步后提前终止。共 3257 控制步，仿真时间 16.285 秒。
- 第 1 段 attempt01 曾被语法预检查拒绝，无现场动作；修正后使用 attempt02。其余请求均为 attempt01。
- `success_within_budget=false`，没有完成任务；未将 ready、辅助抓持或无脚本错误视为成功。

## 实际操作与观测

1. 读取任务包，运行 observe，并在首次动作前实际打开 agentview、front_oblique、wrist 三路初始 PNG。
2. 抬高手部以减少遮挡，依据本轮相机标定和多视角图像估计握持端位置。自行编写通用 Panda 运动学，通过公开手部位姿校准末端偏移。
3. 移至圆头上方；因垂直低位接近关节限位，改用 45° 倾斜接近。下降后缓慢闭合夹爪并等待。
4. 第 6 段确认 `grasp_assistance.arm.active=true`，实际半开口约 18.18 mm。第 7 段竖直抬升约 88 mm，视觉确认钥匙脱离承托架。
5. 沿轴线推进约 100 mm，在第一锁片之前停下；根据图像中扇形孔槽轮廓的假设，将钥匙绕长轴滚转约 30°。
6. 第 10 段计划推进 45 mm，实际手部前移约 30.85 mm 时触发接触力失败。终态钥匙仍由夹爪保持，未完成第一锁片穿越，未到 END，也未执行最终松手稳定保持。

## 关键证据

以下均为本任务目录内的文件。

| 用途 | 路径 |
|---|---|
| 初始 prompt | [observations/dc944256-1497-4f3a-9780-f18cad56185d/prompt.txt](observations/dc944256-1497-4f3a-9780-f18cad56185d/prompt.txt) |
| 初始 manifest 与三路图像 | [feedback/initial/manifest.json](feedback/initial/manifest.json)；其下 `agentview/000000.png`、`front_oblique/000000.png`、`wrist/000000.png` |
| 有效抓持反馈 | [feedback/segment_006/manifest.json](feedback/segment_006/manifest.json)，末帧 000300 |
| 脱离承托架图像 | [feedback/segment_007/agentview/000280.png](feedback/segment_007/agentview/000280.png)、[front_oblique/000280.png](feedback/segment_007/front_oblique/000280.png) |
| 最终权威状态与原因 | [analysis/final_status.json](analysis/final_status.json) |
| 最终 prompt | [observations/e0e8af7d-4474-445a-9267-02db3d977efc/prompt.txt](observations/e0e8af7d-4474-445a-9267-02db3d977efc/prompt.txt) |
| 失败段 manifest | [feedback/segment_010/manifest.json](feedback/segment_010/manifest.json) |
| 最后三路图片 | [agentview](feedback/segment_010/agentview/000157.png)、[front_oblique](feedback/segment_010/front_oblique/000157.png)、[wrist](feedback/segment_010/wrist/000157.png) |
| 失败动作请求与响应 | [requests/seg010_attempt01.json](requests/seg010_attempt01.json)、[requests/seg010_attempt01.result.json](requests/seg010_attempt01.result.json) |
| 抓持与抬升请求 | [requests/seg006_attempt01.json](requests/seg006_attempt01.json)、[requests/seg007_attempt01.json](requests/seg007_attempt01.json) |
| 全部动作、笔记及外部规划 | [policies/](policies/)、[notes.md](notes.md)、[analysis/](analysis/) |

## 计量、输入范围与未验证事项

- `usage_mode=manual`，`usage_measured=false`。**token 用量未测量，真实余额未知**。目标预算为 2,000,000 tokens；bridge 的 used=0 / remaining=2,000,000 只是未接入真实 usage 的账本显示，不证明零消耗或在 2M 内完成。未上报伪造用量。
- `allow_internet=false`。全程未联网、未委派；仅使用任务包、本轮 bridge 返回的数据，以及通用机器人知识。工具包括本地 Python、NumPy、SciPy、Pillow 和图像查看工具。没有读取父目录文档、仓库实现、其他试验、现成解法、私有资产或 simulator state。
- 现场仅通过 bridge 执行动作；环境判定 failed 后停止提交，未重置、重启或修改环境及评测规则。
- 已知失败原因是接触力越限；公开反馈未给出精确接触位置或力峰值。孔槽可通行区域、钥匙轴线误差与动态接触各自的作用尚未验证，不能把视觉扇形假设当作正确几何。
- 三锁片全流程、END 插入、松手稳定保持均未完成。任务包声明 evaluator 为 pilot 且 `physics_qualified=false`，本轮也没有构成完整物理验收。
