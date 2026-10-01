**一句话**：cube 难在初始蹲姿自己站不住（保持初始目标 84 步就向后倒），要先站满 500 步，再尽早把两块方块转到带符号的目标朝向并一直保持。limited：GPT-6 Luna 29.34、GPT-6 Sol 96.06、Claude Opus 5.5 87.86，都没过（最长一局 112、283、182 步），GPT-6.1 Sol 338.91（第 491 步掉方块）也没过；full：Luna 325.05、Opus 247.48，都走满 500 步没过，GPT-6.1 Sol 478.13 过，Sol full 没跑。

## GPT-6 Luna
### limited
- **站不住**：只用骨盆 IMU 的 gravity x、gyro y 做比例修正或换固定腿姿，50 局最长 112 步（ep45），最高 54.14（ep34，110 步）；14.94 min 结论 "changing the hip pitch has a much larger effect on forward lean than changing the ankle target"。
- **转方块和站稳分开试**：ep11–18 在不修正平衡的局里合手、转腕、抬左肩看画面，8.41 min 说 "Large shoulder rotations change the cube faces, but they also shift the robot's balance too far"。
- **被评分段开环转腕**：ep50 固定腿姿、两腕 yaw 转到 0.55，第 61 步掉方块（head_h 1.67，没倒），29.34；50 次 reset 23.6 min 用完，$0.1867。
- **新 spec 事实只打印**：0.15 min 打出整个 `spec()`（含 `links` 的 `com_m`、`feet`），之后没有命令用到，没算过质心。
### full
- **25 min 才站满**：骨盆俯仰、x、vx 的线性反馈，随机增益最长 147 步、CEM 175 步、加腕目标 371 步，25.14 min 靠右臂偏置第一次走满 500 步。
- **转肩转腕对齐**：第 35 步起把两肩 yaw 转到 2.0 / 1.5 rad，配两腕和右臂分段目标；起点点积只有 0.046 / −0.181，它自己说前 40–50 步是 "weak stretch"。
- **判据是线性均值**：按带符号点积全程均值选优（交卷时 0.8927），instruction 写明朝向项 sharp，52.1 min 算过 exp 只作旁证；回放 325.05（平均每步 0.650，过线要 0.74），58.1 min，$0.4591。
### 两种模式
- **差在站不站得住**：full 用仿真状态搜出能站满 500 步的腿；limited 只有骨盆 IMU，最长 112 步，被评分那局没有任何平衡反馈。
- **转法相同**：两边都靠转腕转臂改朝向；full 每个候选都读带符号点积，limited 只能看画面判断。

## GPT-6 Sol
### limited
- **分段踝角站到 283 步**：一条命令扫 3–6 个踝角、髋角或 IMU 增益，每点一次 reset；按步数把踝从 −0.49 换到 −0.42、−0.40，ep48 283 步（135.82），到 7.2 min 已用掉 49 次 reset。
- **IMU 号读反**：没打印 spec 的 `imu` 说明（x > 0 为前倾），把向后倒的 ep0 说成 "pitches forward"，把 gravity x 为正的 ep41、ep50 说成 "backward fall"。
- **被评分段只弯了一次腕**：ep50 右腕 WRJ1 0.25，第 140、160 步把踝改 −0.30、+0.30，第 198 步前倾时掉方块（head_h 1.27），96.06；它说 "the small wrist bend did not visibly turn the right cube's top face"；10.8 min，$0.6682。
- **新 spec 事实没读**：存了 `spec.json`，只从里面取过 `proprio.joints` 的名字。

## Claude Opus 5.5
### limited
- **最早的纯踝反馈最好**：`K*gravity_x+KD*gyro_y` 加到两踝，ep8（K 0.7、KD 0.2）182 步，之后加髋、积分、直腿网格都没超过；26 次 reset 在 3.4 min 用掉。
- **想到质心却用踝角代替**：2.88 min 说 "controlling CoM position directly might work better"，4.83 min 把踝角误差当 "a useful proxy for CoM position"；`links` 只截前 3000 字符打印过，没进代码。
- **提前收工**：ep37 重跑 ep8 的参数（182 步，前倾时掉方块，87.86）后 5.8 min 结束会话，还剩 13 次 reset，当时 `status()` 的 `elapsed_s` 是 325.6；腕和臂一次没动，$0.8771。
### full
- **质心反馈 3 min 站满**：`subtree_com` 与两脚中点的 x 差加到两踝（kp 20、kd 3），500 步站稳、方块留在掌心。
- **搜不出转动**：采样 MPC 或原地不动或把方块翻掉；CEM 搜每 50 步的手臂和手指结点（手臂采样幅度 0.05），代理分按带符号 sharp 朝向写，四元数距离只从 1.38 / 1.54 降到最好 0.974 / 1.203。
- **17.3 min 就停**：6.67 min 以为 "about 28 minutes left"，整场没查过时钟，停时代理分还在涨；回放 247.48，$0.9580。
### 两种模式
- **能不能算质心是分界**：full 用 `subtree_com` 3 min 站满；limited 有 `links` 的质量和质心，却没和关节角合成质心，最长 182 步。
- **都提前结束**：两边都没把方块转向目标，都在预算剩一大半时收工。

## GPT-6.1 Sol
### limited
- **3 min 用 spec 算出质心**：2.84 min 写 `kin.py`，用 `mass_kg`、`com_m`、`position_m`、`axis` 算质心，质心相对脚的 x 差加到两踝；此后 ep11–48 一局没倒（head_h 1.66–1.67）。
- **握法花了大半时间**：扫手指、拇指和小指侧的握法，11.10 min 说 "the far cube slips when its palm turns past roughly vertical"，ep30 握着翻转的方块到第 338 步。
- **看图对齐朝向**：在放大的房间图上手标角点、拟出方块和目标方块的旋转，IK 转手掌并把方块靠在躯干上；52.31 min 自己估计可见的方块还差约 70°。
- **最后一局 59.13 min 才开始**：ep48 撑到第 491 步掉方块，338.91（线 370），是全场最高；60 min 超时，48 次 reset，$3.4802。
### full
- **质心反馈 2 min 站满**：读上游 Cube 类（`get_reward` 已删），质心相对脚的偏差和速度加到两踝，2.12 min 两块方块都握到第 500 步。
- **带符号四元数反馈转方块**：0.80 min 看出目标 "requires a turn beyond 180 degrees in quaternion space"，用带符号相对四元数加有界雅可比转掌心，补拇指对握、多进程搜手指目标；10.57 min 两块误差都低于 0.05 的有 404 步。
- **按说明改尖代理**：之后提前到第 10 步开始转、加积分和力补偿，43.61 min 起用对误差更尖的朝向代理选全程漂移小的版本；终点误差 0.0003 / 0.0007，回放 478.13；跑满 60 min，$2.4058。
### 两种模式
- **都先算质心站稳，差在读不读得到朝向**：limited 用 spec 算质心 3 min 站稳，但朝向只能看图手标角点，最后一局第 491 步掉方块，338.91（60 min、$3.4802）；full 直接读方块四元数，10.57 min 就两块对齐保持，478.13，花费少 $1.07。

## 模型对比
- **limited 都卡在站立**：三家都只用骨盆 IMU 做比例修正或换固定腿姿，没有一家用 `links` 和关节角算质心；最长 Sol 283、Opus 182、Luna 112 步，被评分 96.06、87.86、29.34。
- **reset 花法**：Sol、Opus 一条命令扫多个点，7.2 min 用掉 49 次、3.4 min 用掉 26 次（Opus 停在 37 次）；Luna 一局一局看图，23.3 min 才开最后一局。
- **full 差在转没转方块**：Luna 转肩转腕，均值点积 0.8927，325.05；Opus 站得早（3.0 对 25.1 min），但方块几乎没转，247.48。
- **6.1 Sol 对 6 Sol**：6 Sol 只用骨盆 IMU 扫踝角、读反了 IMU 号，最长 283 步，7.2 min 用掉 49 次 reset，腕只弯过一次（96.06）；6.1 Sol 第一个用 `links` 和关节角合成质心做反馈，3 min 后再没倒，把时间花在握法和看图对齐上，被评分一局 491 步、338.91，离线差 31.09；6.1 Sol full 用带符号四元数反馈过线（478.13），是三家 full 里唯一过的。

## 改进意见
- **说明和设置没发现问题**：limited 的 `spec()` 给了连杆质量质心、关节位置和 `imu` 朝向，`status()` 有已用时间，full 说明写明朝向项 sharp；没算质心、IMU 号读反、线性判据和提前收工都出在 agent 自己。

## 和旧版比
- **第 6 → 7 版 limited**：回报 39.08 → 29.34（最长一局 140 → 112 步）；新 spec 事实只打印过一次，仍只用 IMU 比例修正站立。
- **full 重跑**：回报 252.53 → 325.05；判据仍是线性点积，这次第 35 步就转肩转腕（上次第 340 步才转左肩）。
- **Sol、Opus 第 4 → 7 版**：limited 91.89 → 96.06、36.58 → 87.86（最长 239 → 283、163 → 182 步），都没算质心；Sol full 本轮没跑，Opus full 没有旧版。
