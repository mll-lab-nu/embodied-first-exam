# Interlocked Claws 可解性证明

当前收录 easy / medium / hard 三个 seed 0 实例的连续机器人执行与独立审计。
hard 使用新版收薄几何；原未收薄 hard 未获本批资格。

| 变体 | 模型 | 物理时长／步数 | 审计 |
| --- | --- | --- | --- |
| easy | `pregrasp_weld_v2` | 18.55 s／742 | 通过，保留 1 s 抓持后脱离窗口 |
| medium | `opposed_pregrasp_wide2_v1` | 31.275 s／1,251 | 通过，保留 1 s 抓持后脱离窗口 |
| hard | `pregrasp_scaled_inset3mm_weld_v4` | 208.225 s／8,329 | 有界滑动接触审计通过 |

[完整批次与复核](2026-10-03/README.md) · [机器汇总](summary.json) ·
[工程说明](../../docs/develop/tasks/interlocked_claws_zh.md)

范围：原尺寸 ALOHA、普通 JOINT_ABS、CPU float64、25 ms tick／40 子步、
双手真实接触触发的 `contact_weld_v1`。从任务预抓姿态开始，无标准 home 接近段。
终态要求完整分离至少 10 mm 且双件静稳 0.5 s，允许保持抓持。无新增 RGB 视频。
不扩大为多 seed、默认任务包时序、纯摩擦抓持或全子步无穿透证明。

hard 将两件三角表面顶点内移 3 mm，握持块保留原尺寸，原路线重获 4 mm 连续净空证书。
六个轴向直拉仍有碰撞反例。实际执行允许最多 8 N 件间力、1 mm 引擎穿透和
0.5 mm 独立三角接触深度；实测件间力最大 3.412 N、三角深度最大 0.429 mm。
严格无接触审计的拒绝记录同时保留，不称为无接触解法。机器人禁碰、关节限位、
持件漂移及终态检查均通过，摩擦与机器人增益未改。
