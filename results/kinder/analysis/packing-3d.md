**一句话**：packing-3d 要把一块方块和两块直角三角放进托盘，平贴底面、互不重叠。难在"放"：夹着的零件离能托住它的面不到 5 mm 才松得开，而往下放时手臂或零件一碰到托盘沿，这一步就不执行。limited 用 FK 加腕部深度找到了三件零件和托盘，但每局最多只有一件完整进托盘；被评分的 ep6 方块进了，三角松不开，60 min `timeout`。full 读真值、用 PyBullet IK 逐件放，9.1 min 交出 196 步，第 191 步成功。

## GPT-6 Luna
### limited
- **找东西没卡住**：开局 "The base camera is blocked by the robot body"。它用 spec 的 `position_m`、`axis`、`end_effector` 和相机位姿写 FK，转动关节让腕部相机看向桌面，按颜色分出零件和托盘，再用深度反投影，1.00 min 定出第一块三角。之后底座左转 0.8 rad，找到方块和另一块三角；后退 0.2 m 看全托盘，估出内沿 x 0.366–0.568、y ±0.159，深度量出底面 z 0.085。ep0 三件都是第一次合爪就夹住（2.85、9.58、26.23 min）。
- **最好的一局只有一件完整进托盘**：ep0 第一块三角 7.04 min 放进托盘中央。方块为了避开它往外挪（"it was overlapping the first triangle until I shifted it away"），松手时末端点在里程计 y 0.163，已在它自己估的内沿之外，回放里方块跨在托盘边沿上。第三块三角，它自己说 "appears to straddle the tray's far rim"。ep1、ep3–ep6 方块都平放进了托盘，三角一次也没放进去。
- **卡在松手**：第一块三角开爪 4 次没松（末端 z 从 0.206 降到 0.175），降到 0.17 才松开。方块 9.58 min 夹住后，13 次开爪读数都停在 0.30，下放时 "rejected at the rim"，24.93 min 才松开。ep1 合爪 12 次才夹住三角（52.07 min），端着走了约 5 min，一次也没开爪；`gen.py` 跑的 ep4–ep6，三角都夹住了，但到第 94–98 步都松不开。
- **压缩后误判，脚本又来得太晚**：30.3 min 上下文被压缩。30.95 min 合爪读数 0.075，和 26.23 min 夹住这块三角时一样，它却判断 "it was a miss"，又松开了；之后在托盘沿上的方块上空夹 9 次，38.37 min 才第一次 reset。ep1 靠手动一步步调（68 次调用各只走一步），57.25 min 才写 `gen.py`。被评分的 ep6 方块第 38 步放进托盘，三角第 71 步夹住后一直没松开，第 139 步时 60 min 到。
### full
- **真值、源码和末端点都是现成的**：打印 state 拿到三件零件和托盘 `rack` 的坐标（中心 (0.3, 0)，半边长 0.1×0.15×0.02），读了 `packing3d` 源码和抓取区尺寸 (0.01, 0.01, 0.035)。它用 PyBullet `calculateInverseKinematics` 驱动末端点，合爪后查 `grasp_active`，开爪后查 `grasped_object`，一失败就带着状态报错。
- **也卡在松手，靠内部状态查出原因**：part1 连续 5 次松不开，打印出 `_get_surfaces_supporting_object` 为空。6.73 min："the triangle pickup had descended lower than the square pickup, so the held triangle sat about 18 mm too high"，于是三件都改在同一高度（末端 z 0.1578）夹钉。试过把三角转 180°，两次 "IK missed target"，就改成两块三角斜向对拼。
- **7.91 min 第一次成功**：交 196 步，回放第 191 步成功，两次一致；最后一帧三件都在托盘里。
### 两种模式
- **两边卡在同一处，差在能不能看清失败**：full 每次松不开都能读到零件高度和支撑面，从第一次松不开到成功只用了 4.3 min。limited 只能看到 `gripper_pos` 没变和图像：方块开爪 14 次才松，还松在了托盘沿上，三角一直没放进去。
- **任务文字和服务里没发现问题**：`spec()` 给了末端点和抓取区大小，limited 在 ep0 三件都是第一次合爪就夹住。松手和碰撞的规则写在 `spec()["delta"]["units"]` 里，它照着写进了 `gen.py` 的注释（"Opening only releases within 5 mm of a supporting surface"）。没过的原因在放置方法和时间分配上。
