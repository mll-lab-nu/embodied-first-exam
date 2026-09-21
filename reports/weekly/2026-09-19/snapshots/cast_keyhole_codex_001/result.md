# Cast Keyhole 本轮结果

运行 ID：`cast_keyhole_codex_001`。任务：`cast_keyhole / disassemble`。

**未完成分离。服务端最终状态为 `failed`，由 solver 明确放弃后调用 `stop` 产生。** 停止前状态为 `ready`，环境没有先触发物理失败终态；金色和银色仍然穿插，双手辅助抓持仍为 active。共执行 **19 段、9010 ticks**，控制步长 0.001 s，对应仿真控制时间 9.010 s。终态 observe 的 `expected_segment=20`，终态后未再提交动作。

## 操作及实际结果

| 段 | 操作 | 实际结果 |
| --- | --- | --- |
| 001 | 保持闭合目标，六关节各 0.00025 rad 微扰并返回本轮初始角度 | 双手接触辅助激活；用本轮公开关节与末端数据拟合运动学 |
| 002 | 双手共同绕零件长轴转 0.7 rad | 获得新的观察方向，保持两件相对关系 |
| 003–009 | 两侧偏移、短距离退出、重新对中后直退 | 多次被槽齿限制；有时命令臂到位但另一臂被带动，未穿过开口窄隙 |
| 010–013 | 小幅面内转动、侧移，再向槽内推进 | 面内约 −0.25 rad 转动可执行；向内推进约 35 mm 后出现新限制 |
| 014–015 | 引入另一轴偏转，斜着通过错位齿 | 达到向内约 60 mm、偏转约 −0.60 rad，双手跟踪稳定 |
| 016–018 | 尝试继续向内，退让并校正毫米级高度，再推进 | 两次均未到达约 97 mm 的目标，在约 85–87 mm 附近受阻 |
| 019 | 改由右手移动银色，左手保持实际姿态 | 右臂确实运动，但左臂被带动；相对构型几乎不变，仍未通过卡点 |

上述“向内位移”是根据两手位姿及刚性辅助抓持假设推算的闭合端相对初态位移，**不是物体真值，也不是已完成的分离距离**。末态估计为沿初始长轴向内约 86.9 mm。初始与末段四路图片均已实际打开查看，首次动作前已查看全部四路初始 PNG。

## 停止原因与未验证事项

我没有找到能可靠穿过内部槽齿并完成分离的连续动作。左右手分别驱动时，最终都停在几乎相同的相对构型。接触使关节与末端偏离目标；图像重建对遮挡处、闭合端轮廓和窄槽间隙仍有毫米级歧义，部分离线候选路径不能在现场实现。

本轮进行了平移、两种转角及其组合的有界离线搜索，仍未建立完整通路。这些搜索基于近似几何，不能证明任务不可解。部分单左臂候选触及腕部限位；名义 IK 检查表明可以改由右手分担相对转动，但后续大角度转动未实际执行。整体降低等离线候选也没有提交到环境。

基础关节控制、初始接触抓持、共同转动和部分相对运动已得到验证。没有测试松爪或换抓，不能据此宣称这些操作已验证可用。完整分离、分离后的稳定保持及完整物理资格均未验证；任务包标记 `physics_qualified=false`。

## 关键证据

- 初始观测：[manifest](feedback/initial/manifest.json)，四路 `feedback/initial/{cam_high,cam_low,cam_left_wrist,cam_right_wrist}/000000.png`。
- 稳定向内推进：[segment 015](feedback/segment_015/manifest.json)；高度校正：[segment 017](feedback/segment_017/manifest.json)。
- 最后动作：[脚本](policies/segment_019.py)、[请求](requests/seg019_attempt01.json)、[响应](requests/seg019_attempt01.result.json)、[manifest](feedback/segment_019/manifest.json)。
- 末态图像：[高位](feedback/segment_019/cam_high/000580.png)、[低位](feedback/segment_019/cam_low/000580.png)、[左腕](feedback/segment_019/cam_left_wrist/000580.png)、[右腕](feedback/segment_019/cam_right_wrist/000580.png)。
- 终止证据：[stop 响应](stop_response.json)、[终态 observe](final_observation.json)。
- 每段依据与结果：[notes.md](notes.md)；逐段公开状态汇总：[episode_progress.json](analysis/episode_progress.json)。
- 全部提交脚本在 `policies/segment_001.py` 至 `segment_019.py`；请求在 `requests/segNNN_attempt01.json`；本轮感知、IK 与搜索产物在 `analysis/`。几何搜索中的误差容差仅用于近似模型，没有修改环境碰撞阈值。

## 计量与信息访问

**执行时采用 manual 模式：当时 token 用量未测量，真实余额未知。事后经用户要求核对原生记录，本轮累计 12,487,795 tokens，已超过 2,000,000 token 预算。** 执行期间未接入原生 Codex usage；bridge 的 `used=0` 是未记账，不代表真实零消耗。原始 bridge 计量账本和环境终态未修改。

`allow_internet=false`。输入为本任务包四份说明、当前 episode 的 bridge 观测及通用机器人/数值计算知识。工具为 bridge_client、图像查看及 Python（NumPy、SciPy、Pillow、Matplotlib）。未访问外网、委派任务、读取父目录源码/demo/解法/其他试验/私有资产或 simulator state；未启动、重启、复制、重置或回滚环境，未修改实现和评测规则。

当前对话保留了此前其他任务的讨论，故不宣称严格的新会话隔离；本轮没有读取旧试验文件或复用其轨迹、物体几何和动作参数。

## 事后原生 token 用量核对

用户在任务结束后要求检测用量，遂只读取宿主会话中的计量元数据及本轮边界标记。统计范围从本轮 Cast Keyhole 任务请求开始，到求解结束的最终答复为止，不包含后续这次用量查询。

| 项目 | tokens |
| --- | ---: |
| 输入总量 | 12,363,113 |
| 其中缓存输入（已包含在输入内） | 11,655,552 |
| 输出总量 | 124,682 |
| 输入加输出合计 | **12,487,795** |

合计为 2M 预算的 **6.2438975 倍**，超出 **10,487,795 tokens**，因此本轮不满足 2M token 预算限制。缓存输入未重复相加；输出中的 reasoning 81,497 tokens 也未重复相加。

原生累计计数从 79,082,683 增至 91,570,478；区间内 99 条计数事件均无计数回退，每次累计增量均与对应 last_token_usage 一致。证据与边界时间、日志行号见 [analysis/token_usage_posthoc.json](analysis/token_usage_posthoc.json)。这属于完成后的原生记录核对，不是执行时 bridge 已实现实时预算控制的证明，也不改变环境的 failed 终态。
