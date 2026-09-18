# Cast Keyhole：从可解 IK 反推三个结构变体

这组三个实例以当前下部孔道初态的完整可解轨迹为种子。顺序是先改轨迹、求解双臂 IK，再利用实际 FK 得到的相对运动扫掠体生成结构。不是先随机改几何再搜索解法，也不声称是新的官方 Hanayama 产品或官方教程的逐帧复刻。

工作目录：`runs/environment-solvability/cast_keyhole/inverse_motion_variants_v1/`。
MP4 最终归档到 `runs/demos/cast_keyhole/`，各实例用独立文件名前缀区分；播放页和证据位于 `runs/demo_metadata/cast_keyhole/2026-09-17_inverse_<variant>/`。

| 变体 | 首先修改的运动 | 反推的金色件结构 | 对照结果 |
| --- | --- | --- | --- |
| `offset_window` 偏心转弯窗口 | 顶部绕行增加最大 1 mm 横向、0.5 mm 纵向模板偏移 | 非对称窗口边界 | 新轨迹可行，原解法仍可通过；属于兼容的结构变体 |
| `double_gate` 双重错槽 | 退出段加入右移、下移、左移对齐第二门、继续下移、右移退出 | 新增第二组错位挡齿 | 原解法的采样姿态发生 4.95 mm 碰撞 |
| `tilted_window` 倾转穿窗 | 窗口前追加 25° 侧转及 8° 出平面倾斜，穿窗后恢复姿态 | 三层不同截面的带止挡窗口 | 原解法出现 0.9 mm 碰撞；保留新平移但省略倾转出现 6.16 mm 碰撞 |

模板长度单位是 mm，场景整体放大 3 倍。表中对照碰撞距离使用实际场景米制换算。三版均保留银色件、两处抓持区域及当前初态。未做全局捷径穷举，不能据负对照推断解法唯一。

## 几何与 IK 证据

每个实例保留依次生成的 `proposal.json`、`ik_proposal.json`、`geometry.json`、`certificate.json` 和 `robot_motion.json`。哈希将提案、IK、反推几何和证书关联。`ik_proposal.json` 生成时几何尚未确定；后续机器人检查只更新单独的 `robot_motion.json` 报告，保持 IK 帧不变。

生成器将银色件在 IK 相对运动下的扫掠体从金色原件及显式候选材料域中扣除。平面投影按厚度区间切片，采样由最大材料点位移控制；每步不超过 0.1 模板 mm，扫掠扩张为 0.16 mm 余量加 0.05 mm 半采样距离。简化后的最终实体另经连续凸体 SAT 检查，每个相邻 FK 相对姿态插值区间要求至少 0.15 场景 mm 的间隙下界。

倾转版实际采用厚度区间 `[-1.5,-0.25] / [-0.25,0.25] / [0.25,1.5]` 模板 mm。中央层保留止挡，两侧层提供倾斜避让空间；可视网格由三层布尔并集生成，碰撞体是各层无重叠凸棱柱。金色件保持一个连通实体且 Euler 数为 2，银色闭孔件 Euler 数为 0。检查导出前后总体积、包围盒和 Genesis 实际装载的每个碰撞单元。

双臂 IK 同时约束两件的相对位姿及共同工作中心，保留固定抓持点。机器人碰撞检查包括每个 IK 帧以及相邻关节插值采样，最大关节采样步长 0.003 rad。

## 物理执行和视频范围

使用 ALOHA 双臂、Genesis float64、1 ms 时间步及 4 子步、有限关节力矩。起点为预抓取位姿；只有一件的两侧指尖在同一步实际接触后，才允许启用该侧辅助焊接。开始执行后不再写物体位姿或机器人关节位置，只施加关节控制目标。

保存同一次连续执行的真实关节与物体状态；独立复查每 10 ms 状态的机器人、桌面、两件碰撞和末态静置。录像从这些已审查物理状态重建画面，不从计划 IK 轨迹替代实际状态。每个视频帧保留 `source_trace_index` 和原物理步号；渲染器不再推进动力学。

演示包含完整解锁和分离，末态保持抓持，**不包含从桌面拾取、解除辅助抓持和释放落桌**，也未验证纯摩擦抓持。每版保留 `cam_high / cam_low / cam_left_wrist / cam_right_wrist` 四路同步视频，另有 `detail / oblique / four_views`。归档检查完整解码、帧数与时长、首尾物理帧、证据哈希和播放页本地链接。

## 复现

额外几何依赖见 `requirements/uv-topogym-keyhole-inverse.txt`。命令使用新输出根目录，避免覆盖已验证证据；依次对三个名称执行。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.inverse_variants \
  --variant offset_window --output runs/environment-solvability/cast_keyhole/inverse_motion_variants_v2
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variant_runtime physics \
  --variant offset_window --root runs/environment-solvability/cast_keyhole/inverse_motion_variants_v2
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variant_runtime audit \
  --variant offset_window --root runs/environment-solvability/cast_keyhole/inverse_motion_variants_v2
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variant_runtime render \
  --variant offset_window --root runs/environment-solvability/cast_keyhole/inverse_motion_variants_v2
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variant_archive \
  --variant offset_window --root runs/environment-solvability/cast_keyhole/inverse_motion_variants_v2 \
  --run-prefix 2026-09-17_inverse_v2
# 三个实例分别完成归档后生成统一播放入口：
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variant_archive \
  --overview --run-prefix 2026-09-17_inverse_v2 \
  --root runs/environment-solvability/cast_keyhole/inverse_motion_variants_v2
```

回归：`.venv-gs121-nyx/bin/python -m unittest discover -s tests -p 'check_cast_keyhole*.py'`。
新增测试覆盖分层实体的真实厚度避让、可视与碰撞体积一致、孔道不被凸包封闭、三版共同未解初态及分离终态，以及旋转偏心质心时的世界／规范坐标往返。
