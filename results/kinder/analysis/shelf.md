**一句话**：shelf 要把地上的红、绿两块方块放进三层柜子的上层格，得先找到并开近柜子，再让夹爪从柜前开口伸进上层格（竖直手腕会撞上层格顶板）。limited 用前 3 局找到方块和柜子、写成 `gen.py`，之后 21 局 reset 后重跑，夹块和开到柜前都重放得出来，放置高度却换了 8 次，多数局把方块放在柜子顶板上，被评分的 ep23 到第 659 步 60 min 用完，`timeout`；full 读到坐标和目标区域，用接触检测改成 45° 倾斜手腕，交 955 步通过。GPT-6.1 Sol 两种模式都过：都用夹爪水平朝前的姿态从开口送进上层格，limited ep2 第 784 步，full 第 785 步。

## GPT-6 Luna
### limited
- **前 3 局用来找东西、定路线**：ep0 夹住绿块，转底座时夹爪命令给了 0（9.99 min "a later base turn sent an open command and released the green cube"），没找到红块；ep1 按网格扫 171 步仍没找到；ep2 往西扫到（18.53 min "places it near (−0.1, 0.3) m in odometry"），一次夹住、开到柜前，用腕部深度量出 z 0.551 和 0.817 两层板。27.6 min 写成 `gen.py`，ep3–ep23 都是 reset 后重跑它。
- **用了 `end_effector`，夹和运都重放成了**：FK 点列末尾是 [0.1199, −0.0249, 1.7261]，即 `end_effector`（代码直接写数）；脚本里红块除 ep3 空夹外每局都夹得起（ep15 起每局第 126–127 步读数 0.587），柜前停位也每局重放。
- **放置高度没定下来，多数放在顶板上**：`gen.py` 的放置高度在 0.857、0.591、1.14 之间换了 8 次；ep2、ep19 的末帧里方块都在柜子顶板上。42.79 min 它自己说过 "the cubes are on the cupboard’s exposed top board. The upper compartment is directly underneath it, with its floor around 0.55 m"，但伸进那一格的几次（ep13、ep14、ep16）手臂没够到或撞了板（46.27 min "the arm stopped as it tried to reach deeper into the cubby"），又改回 0.857 和 1.14。
- **交接后 0.55 m 成了假设，最后一局来不及跑完**：43.53 min 上下文压缩，交接稿写 "This is not yet confirmed"，之后 10 局在三个高度间来回。被评分的 ep23 在 59.74 min 才开始，放置高度又改回 0.857，第 126 步夹住红块、第 217 步开到柜侧，第 659 步 60 min 到；末帧手臂竖在柜前，三格里没有方块。
### full
- **真值加源码**：直接读柜子 (1.5, 0) 和方块坐标，读 `check_in_region` 后说 "The cupboard goal is a narrow height band centered on the top shelf"，方块目标定在 (1.48, ±0.075, 0.57)。
- **接触列表找到转腕**：竖直手腕在上层格口卡住（NOTES："A vertical wrist pose collided with the top compartment roof"），列出 `s.data.contact`、在 IK 采样里比接触深度，2.6–6.6 min 找到 45° 倾斜姿态；11.14 min 红块已稳定进格。
- **绿块的路线最费时**：自碰撞、悬停卡住、转腕不收敛，16 次整条运行前 15 次中途报错；19.98 min 第一次成功，交 955 步（上限 1000），两次回放一致，21.4 min 结束。
### 两种模式
- **分界在放进上层格**：full 读 `check_in_region` 就知道目标是上层格的高度带（块放 z 0.57），难点只剩插入姿态，靠接触检测换成 45° 手腕；limited 靠 reset 把找块、夹块、开到柜前都重放稳了，板层只能用腕部深度量，放置高度来回换，伸进上层格的几次手臂没够到或撞了板。

## GPT-6.1 Sol
### limited
- **先量出柜子的三层板**：按 `spec()` 写 FK/IK 和深度反投影，手臂举高斜看、底座原地转几个角度，量出绿块 (1.816, 0.743) 和柜子板面 z 0.285、0.551、0.817（2.42 min "I found the green cube and the three-compartment cupboard"）。
- **ep0 碰顶板后换逆解**：夹起绿块后底座转向柜子，第一次伸向上层格 IK 误差 0.46、手臂碰到顶板（5.15 min "The arm contacted the cupboard’s roof"），离线换初值、把目标推远到底座前 0.70 m，找到夹爪水平朝前、关节 6 为 +1.71 的关节角，绿块放进上层格（6.82 min "released inside the top compartment"）。
- **ep1 找红块，ep2 一次做完**：红块在起点附近、被底座挡住，ep1 开到 (1.8, 0) 回头才看到 (−0.090, 0.240)；ep2 先红后绿，两次都用同一组水平关节角送进上层格，第 784 步 `success`。14.8 min、$0.6187，看图 42 张，reset 用了 2 / 50。
### full
- **读配置判断开口**：读 `Shelf3D-o2.json` 和状态，0.82 min "The top compartment’s floor is 55 cm high, and it opens toward the robot. I’ll grasp each cube from above, then turn the gripper horizontally"；放置点定在 (1.48, ±0.12, 0.575)。
- **修了抓取和转腕**：抓方块角在转腕时滑脱、转腕超关节限位，改成经 z 0.15–0.04 分段下降、IK 越界再加限位重解、先抬到方块前 0.35 m 的 z 0.65 再在空旷处转成水平。
- **红块跑通后照抄绿块**：3.69 min 红块已进格（564 步），4.76 min 加上绿块那段（只换 y），第 785 步成功；两次回放一致，5.9 min、$0.3237。
### 两种模式
- **两边都靠水平送入**：都用夹爪水平朝前的姿态从开口把方块放进上层格；full 从配置读到底板高度和开口方向，limited 用深度量出三层板、碰过一次顶板后换出这组关节角。GPT-6 Luna 的 limited 放置高度换了 8 次、多数放在柜顶，full 用 45° 倾斜手腕、交 955 步。

## 对照实验
- **不 reset 的那一局没过**：找块、找柜子和放置挤在唯一的 1000 步里。绿块夹住后转底座时滑落，重找重夹用了约 300 步；它把墙边一件黑色家具当成柜子（23.23 min "I’ll move it toward that structure"），第 759–778 步在它前面松开绿块，红块和棕色柜子一次也没看到，第 1000 步 `failed`。

## 和旧版比
- **旧版（50 次 reset，没有抓取点）**：以腕部相机为工具点，红块合爪 7 次全空、第 8 次才夹住，方块一举高就掉，一次也没在柜口前松手；这一版用 `end_effector` 后，红块除 ep3 外每局都夹得起、能端到柜前放下，卡点移到了放置高度。两次都没过。
