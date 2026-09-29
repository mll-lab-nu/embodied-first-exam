**一句话**：sweep-simple 要把地上十块 2 cm 方块弄进岛台一端地面上的区域（`sweep_region` x 0.125–0.875、y 1.0–1.375，每块离区域边 0.57–1.12 m），而 KinDER 里底盘碰不到这些方块（full 查接触列表、limited 回放里方块从底盘四角轮罩之间穿过），能推方块的只有夹爪指垫和一把立着的 T 形刮板。limited 找对了箱子，但两次整车推都从方块上开过去、六次伸臂下探卡在半空、两次合爪全空，箱里 0 块、方块基本没动；full 夹不稳刮板，改用指垫沿 +y 扫三道，536 步里 4 块前移 0.06–0.34 m，离区域最近的一块还差 0.46 m，0 块进箱。

## GPT-6 Luna
### limited
- **找箱子用了 19 min，找对了**：ep2（6.03–25.04 min，44 张图）挪一下拍一张底盘图，绕到岛台一端，方块的红色像素和地面上的半透明框都按 `spec()` 的 `robot_base` 位姿反投到地面；20.11 min "I’ve located the goal footprint at the island end (approximately centered near odometry `(0.61, -0.78)`)"，按起点位姿换到世界坐标约 (0.66, 1.19)，在 `sweep_region` 里。
- **整车推从方块上开过去**：20.15 min 绕到方块簇远端，朝箱子每步斜开 (−0.07, −0.07)；回放第 246 步方块在底盘四角轮罩之间，第 260 步还在原处。底盘相机看不到底盘下面，它判断 "The base sweep reached the island wall before the box"；被评分的 ep15 又这样推了一次，时间到时方块在底盘下面。
- **手到不了地面**：逆解以腕部相机为工具点，把相机送到方块上方 0.17 m；ep0、ep5、ep9、ep10、ep11、ep13 第 2 关节都差 0.39–0.87 rad 停住，46.82 min "the wrist reached the island surface before the cube"，没查出到底卡在哪。
- **一块没夹起**：ep4、ep13 两次合爪，`gripper_pos` 都是 0.984，合爪前腕部图里只有地板；刮板一次没碰。看过的 10 局回放末帧里箱内都是 0 块；`/app/output` 没留 `gen.py`。
### full
- **先查清了物理**：0.27 min 从 `task_config` 读到 `sweep_region`；底盘从方块簇正中穿过，10 块坐标一个没变，8.51 min "A broad base sweep doesn't contact the cubes in this model"。
- **刮板抓不住**：3.1–40 min 大半在夹 0.30 m 高的把手，腕部连杆一次次先把它碰倒（19.66 min "The wrist was knocking the wiper over during handle approaches"），43.21 min 交接时仍 "has not held it securely enough to carry it"。
- **指垫一次推一两块**：x 1.45、1.6、1.3 三道沿 +y 扫，536 步里 cube_1、4、5、8 前移 0.06–0.34 m，其余 6 块没动，所有方块 x 仍在 1.26 以上（区域上限 0.875）；朝区域的斜推 56.5 min 才开始试、没存下，57.58 min 第一次试夹方块，指垫中点只降到 z 0.042，没夹起。
### 两种模式
- **卡在同一处物理**：两边都是底盘推不动、指垫太窄、刮板难抓，都没有一块进箱。分界在接触信息：full 8.51 min 就知道底盘碰不到方块，limited 看不到底盘下面，最后一局还在用底盘推。
- **难点在任务本身，不在说明**：limited 按说明找到的箱子和 full 读到的区域一致；full 有全部坐标和接触列表，60 min 也只让 4 块挪了最多 0.34 m，离区域最近的一块还差 0.46 m。

## 改进意见
- **`spec()` 仍没有夹爪抓取点**：这次 limited 的逆解全程以腕部相机为工具点（`off=cam-P[-1]`），手指在哪只能靠猜；同总览里的建议。
