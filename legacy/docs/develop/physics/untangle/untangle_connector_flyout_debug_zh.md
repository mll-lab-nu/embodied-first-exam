# Untangle 连接器时代绳中段飞出 debug-log

> 日期：2026-07-11
> 状态：**probe run #1（用户 GPU viewer，contact ON + lift 0.100 + column 0.020）全程干净未复现**——
> 556 个采样 0 parked、max jump 2.9mm、min finger_dist 13.3mm（H1 未发生）、endpoint_sep 159→65mm 被平稳吸收（H2 未引爆）。
> 结论：当前配置至少单局稳定；此前的飞出疑为非确定性边缘情形或中间状态。`--probe` 保留在 demo 里，复发时可直接抓判别数据（§4 判读规则）。
> **2026-07-11 用户验收 close**：大棋盘（spacing 0.105/0.100）+ 压低端头（柱 0.014、弧顶 34.9mm）+ 统一灰塑料端头，观感与稳定性均通过，本 debug 线暂闭。
> 背景：Phase B（插头连接器 + 双态 weld）已落地，见 `untangle_redesign_plan_zh.md` §8。

## 1. 症状

搬运（physical drag）过程中，某根 PBD 绳的**中段**粒子突然弹出求解域，被钳在 PBD 域角点 `(100,100,100)`（`PBDOptions.upper_bound` 默认值），蒙皮网格被拉成"直梁"射出画面。弹出后 `jump=0`、位置恒定——这是"粒子已出域被停放"的特征签名，不是持续震荡。

## 2. 各轮 run 事实表

| Run | 绳↔机器人接触 | lift_delta | column | 结果 |
|---|---|---|---|---|
| smoke2/3（headless 录像）| ON | 0.028 | 0.035 | 绿绳在**落座后张爪→撤退段**撕裂（27s 健康 → 31s 爆；梁方向=撤退方向）|
| smoke4 + oracle_full | **OFF**（needs_coup=False）| 0.028 | 0.035 | **全程干净**，task_success=True |
| 用户 GPU viewer 实测 | ON（已恢复）| 0.100 | 0.020 | 中段再次飞出（**发生阶段未记录**——本轮 probe 要补的关键信息）|

注意最后一轮**同时改了 3 个变量**（接触恢复、lift 0.028→0.100、column 0.035→0.020），违反"一次一个量"，所以不能直接归因。

## 3. 两个候选根因（用户提出 + 既往证据）

**H1 夹爪-绳接触**：移动中指垫钩挂/挤压绳（旧机理复发——smoke2/3 已实锤过一次"指垫钩住顶部出线的垂坠段"；contact OFF 那轮稳定是佐证）。高抬升后垂坠段更长、摆动更大，接触窗口可能反而变多。

**H2 端点间距压缩**：本局 planner 的 move（green:start [1,0]→[0,2]）使绿绳端距 144mm→72mm 减半，绳总长不变 → 大量余量在搬运中被压缩堆积；PBD 管（体积约束 + 自碰撞）受压 buckling → 爆解。lift 0.100 的摆动会加剧压缩瞬态。反证：smoke4（contact OFF、lift 0.028）同样端距减半却稳定——说明 H2 至少在低抬升时不致命，但高抬升下的动态压缩未验证。

## 4. 判别设计（本轮要做的 probe）

给 `untangle_physical_handle_demo.py` 加 `--probe`（对齐 cable_routing 的 `CableRoutingProbe` 先例）,每 N 步打印：

- 每绳：`parked` 粒子数（域角点判据）、`max_jump`（单步最大位移）、`min_z`/`max_z`；
- **绳↔指垫最小距离**（两 finger pad link pos 到被移绳粒子的最小距离）——H1 的直接证据；
- **被移绳的端点间距**（两 pin 之间 xy 距离）与**绳弦长/余量比**——H2 的直接证据；
- 当前 primitive phase / segment label（从 status dict 读）。

**判读规则**：首个 parked 出现的那一步——若 `min_finger_rope_dist ≈ 0`（近零）且发生在接触窗口 → H1；若手指远离（>3cm）而端距处于低谷/余量比高位 → H2。

**A/B 备份实验**：同参数下把接触切回 OFF（`UntangleSceneBuilder.build` 里恢复 `robot_material=Rigid(needs_coup=False)`，参数已保留）再跑一轮——若立刻稳定则 H1 实锤。

## 5. 修复候选池（按 probe 结果取用）

- H1 实锤：fallback `needs_coup=False`（已验证有效）；或只给**两根 finger link** 免耦合（若 Genesis 支持 per-link，待查）；或张爪后先横移出绳区再上撤。
- H2 实锤：降低 lift（0.100→0.05~0.06）；平移限速（move_steps 加大）；落座前中途 settle；**棋盘放大**（孔距 ↑，余量比整体下降，见 §6）。
- 通用缓冲：volume_compliance 放软 + volume iterations 加大（cable_routing flyout 实验 #1 同款）。

## 6. 棋盘放大提案（用户提出，待 plan 评审）

孔距 `[0.078, 0.072]` → 建议 `[0.105, 0.100]` 量级（约 +40%），孔径/绳径/端头尺寸不变，`top_left_pos` 重新居中：

- **对"凹"形**：出线弧顶高度不变（~48mm）而平直段拉长 ~40%，端头翘起在整根绳里的占比明显下降 → 更接近直线观感；
- **对 H2**：同样的端点移动，端距变化的**相对余量**下降，压缩堆积更少；
- **对 VLM/评测**：孔间留白更大，空孔/占用孔更易分辨（呼应 grommet 前的对比度问题）；
- **约束检查**：4×4 网格 @ spacing 0.105/0.100 → 格网 extent 0.315×0.300，重新居中后 x∈[-0.157,0.158]、y∈[-0.150,0.150]，均在 workspace x[-0.25,0.25]、y[-0.30,0.30] 内 ✓；绳变长 → 粒子数增加 ~30-40%，仿真略慢；
- **连带**：`rope.strands` 的点坐标是格点索引，无需改；oracle/topology 只读格点索引，无需改；相机取景不用动（front 视角本来就有富余）。
