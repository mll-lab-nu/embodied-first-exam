**一句话**：sweep-simple 要把地上十块 2 cm 方块弄进岛台一端地面上的区域（`sweep_region` x 0.125–0.875、y 1.0–1.375，每块离区域边 0.57–1.12 m），而 KinDER 里底盘碰不到这些方块（full 查接触列表），能动它们的只有夹爪和一把立着的 T 形刮板。limited 用 ep0–ep12 试推扫、只靠手臂搬、底盘托扫，再标出固定站位、夹取高度和箱口松手点，被评分的 ep14 先跑 `gen.py` 再现场补夹，逐块夹起、开底盘送到箱口，第 905 步 `success`；full 夹不稳刮板，改用指垫沿 +y 扫三道，536 步里 4 块前移 0.06–0.34 m，0 块进箱。GPT-6.1 Sol 两种模式都过，都是逐块夹起送进区域：limited ep5 第 980 步，full 先试了约 20 min 刮板，交 982 步。

## GPT-6 Luna
### limited
- **前 11 局试错**：ep1–ep4 合爪后用底盘或手臂往箱子方向扫，ep3、ep4 最后一段手臂够不到（到位误差 0.16、0.121 m）；ep5 第 495 步第一次夹住，只靠手臂送差 0.177 m；ep10 手臂放低锁住、用底盘托扫，回放里方块还堆在原处、刮板被撞倒。中间 35.92 min 查出 "base turns were sent with zero arm deltas, which continually reset the arm target to its measured pose and let the wrist sag"，此后底盘动时每步锁住手臂。
- **ep11–ep12 标出能重放的数**：5 步 [0.08, −0.01] 的固定站位（47.89 min "makes both the detected cubes and the box reachable"），夹取高度 z 0.035 空夹、0.01 夹住，空夹阈值 0.88；夹住后抬起、底盘带着开到箱口松手，52.14 min 第一次在箱里看到方块，ep12 夹放 3 块。54.52 min "The high carry cycle is reliable but too slow to fit all ten cubes"，托运高度从 0.18 降到 0.10。
- **`end_effector` 就是 FK 工具点**：0.82 min 起 FK 工具点是第 7 关节加 R·[0, 0, 0.2054]，0.2054 正是 `end_effector` 的 z 1.7261 减第 7 关节 z 1.5207（没按键名读）；IK 直接对它求解，夹取高度仍靠试。
- **被评分的 ep14 前半回放、后半现场**：`gen.py` 放进 2 块后第 319 步空夹、脚本停下；它手动补夹一块，再跑一段加了空夹后重新检测、就近重试的内联循环（第 450、773 步空夹后重试夹住），一局夹放 9 次，第 905 步 `success`。留下的 `gen.py` 不含手动补夹那段。
### full
- **先查清了物理**：0.27 min 从 `task_config` 读到 `sweep_region`；底盘从方块簇正中穿过，10 块坐标一个没变，8.51 min "A broad base sweep doesn't contact the cubes in this model"。
- **刮板抓不住**：3.1–40 min 大半在夹 0.30 m 高的把手，腕部连杆一次次先把它碰倒（19.66 min "The wrist was knocking the wiper over during handle approaches"），43.21 min 交接时仍 "has not held it securely enough to carry it"。
- **指垫一次推一两块**：x 1.45、1.6、1.3 三道沿 +y 扫，536 步里 cube_1、4、5、8 前移 0.06–0.34 m，其余 6 块没动，所有方块 x 仍在 1.26 以上（区域上限 0.875）；朝区域的斜推 56.5 min 才开始试、没存下，57.58 min 第一次试夹方块，指垫中点只降到 z 0.042，没夹起。
### 两种模式
- **路子相反**：full 大半时间夹刮板、用指垫扫，57.58 min 才第一次试夹方块，0 块进箱；limited 从 ep5 起夹方块，ep12 标出 z 0.01 和箱口松手点后逐块夹、开底盘送，过了。
- **底盘推 full 一查就放弃，limited 试了几局**：full 8.51 min 查接触列表就知道底盘碰不到方块；limited 看不到底盘下面，ep1–ep4、ep10 还在推扫、托扫（ep10 底盘相机检出的方块数降到 1，回放里方块还在原处），46.50 min 的压缩摘要才写 "don’t treat those counts as evidence of placement"。

## GPT-6.1 Sol
### limited
- **工具点和定位都来自 `spec()`**：FK 按键名读 `end_effector`、IK 对它求解；腕部深度加相机位姿和里程计把红色方块反投到起始坐标系（z 约 0.020）。ep2 5.37 min "I’ve located all ten cubes and the box"，标出夹取高度 z 0.012 和空夹阈值（`gripper_pos` 大于 0.94），8.87 min 第一次看到方块进箱。
- **每局整局重来、各改一处**：ep3 放进 6 块，12.81 min "A direct diagonal transfer made the folded arm clip the island’s corner"，改成绕角路线；ep4 放进 8 块，转 45° 夹的那对两次空夹，改回不转腕，加了合爪前用腕部图像重测，第 1000 步 `failed`。
- **被评分的 ep5 是现场跑的 `collect.py`**：按前几局反投出的 8 个坐标逐块夹放，最后一对两次空夹后重测到 [1.128, 0.067]、手动对准，第 959 步夹住，往箱口开的路上第 980 步 `success`。reset 用 5/50，21.5 min，$0.8029；`gen.py` 嵌着这 980 步动作直接回放。
### full
- **先在刮板上花了约 20 min**：读任务 JSON 得到区域，IK 对 `robot_pinch_site`；1.96 min 就夹起刮板，但推的时候 "the blade tilts and rises over the cubes"（4.57 min），侧面夹、压低刮条都一样；19.47 min 查出 "the apparent grips caught the handle in the gripper linkage"，修好后仍骑过方块。
- **21.46 min 改逐块夹放**：每块用真值定位、竖直降到 z 0.043 合爪，底盘绕回 y 1.75 再开到区域里的 2×5 网格点松手；第一版 858 步只放了 6 块，压步数后 cube_0、2、4 没夹起，恢复分段下降、对挨着的 cube_2、4 先把夹爪合到 0.65，第 982 步 `success`。
- **交的是闭环控制器录下的 982 步**：10 块终态在 x 0.319–0.719、y 1.135–1.229；两次全新进程回放终态一致。27.2 min，$1.3492。
### 两种模式
- **最后的做法一样，limited 更快**：都是逐块夹起、开底盘送进区域；limited 一开始就没碰刮板，21.5 min 过；full 前 21 min 在刮板上，27.2 min 过。和 GPT-6 Luna 比：Luna limited 也是逐块夹放、到 ep14 才过，full 一直在刮板和指垫上、0 块进箱。

## 对照实验
- **不 reset 的那一局没过**：第 265 步就夹起一块，但转底盘找箱子时夹爪命令给了 0，方块掉了；第二块第 699 步夹住，只靠手臂送，第 1 关节还差 0.745 rad 就在第 826 步松手；第 844–991 步改用底盘推，第 1000 步 `failed`，1000 步在 19.6 min 用完。只靠手臂送和用底盘推，主运行在 ep1–ep10 也试过、都没成；这一局没有下一局去改。

## 和旧版比
- **抓取点起了作用**：旧版（50 次 reset、没有抓取点）IK 以腕部相机为工具点，六次伸臂下探卡在半空、两次合爪全空，方块基本没动；这一版 IK 直接对 `end_effector` 求解，ep5 第一次夹住，ep14 过了。两次运行只差这一处（`blocked` 只在 PyBullet），各跑一次。
