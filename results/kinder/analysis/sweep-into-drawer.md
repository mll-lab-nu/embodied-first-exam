**一句话**：sweep-into-drawer 要先拉开关着的岛台上层中间抽屉（拉手是一根细横杆，在 z 0.325，比台面上的方块还低），再把台面上的五块方块弄进去。新版 limited 用腕部深度把横杆定在 z 0.326，手沿柜面法线横着伸进去夹住、拉出 12 cm，再逐块从上方夹起放进抽屉，ep10 第 867 步 success；full 41.79 min 才夹住拉手、把抽屉拉开约 7 cm，剩下 368 步用张开的夹爪推方块只挪了几厘米，949 步回放没成功。

## GPT-6 Luna
### limited
- **转底盘、压腕部相机、侧移找方块**：0.30 min "The service provides wrist RGB-D but no room camera, and the arm starts folded with the wrist camera aimed upward"；底盘左右转、停在 yaw −0.70，第 4 关节转 0.52 rad 把腕部相机压向台面，再左移到 y 0.42，2.16 min 五块方块都进了腕部画面；红色像素按深度和 `spec()` 的 `axis`、`position_m`、腕部相机位姿反投，方块中心 z 0.455。
- **深度定拉手、横着夹**：底盘相机只看得到下层拉手，它用木地板与柜面的分界拟合柜面法线，10.42 min "The visible pull is on the lower part of the cabinet, so I’m using the depth and camera geometry to aim at the drawer above it"；腕部相机贴到柜面前，横杆在深度 0.135 m 处反投到 (0.631, −0.180, 0.326)；手沿法线伸进、手指竖直合拢，13.23 min 第一次在拉手处合爪（0.934）就夹住，拉出 12 cm。
- **卡在 1000 步内放完五块**：22.06 min 把 ep0 的动作和标定写成 `gen.py` 每局照搬，ep1–ep9 最多放进 4 块：ep2、ep3 从正上方往抽屉里放，每次下放用满步数上限（28.28 min "the downward path was blocked by the island’s counter"）；ep4–ep8 改成端到抽屉前口外再平着塞进去，每块多走一段，够方块时几次卡满 100 步、合爪落空（0.974–0.989）。
- **两处改动过线**：37.50 min 逆解改成从 9 个初值里取最优，ep9 五次夹取都一次夹住，但第五块到第 1000 步还在路上；38.44 min 改成移到放置点（已在拉出的那段里）正上方竖直下放，每块从 143–190 步降到 119–132 步，ep10 第五块下放到第 867 步时判 success。
- **只用了 limited 给的东西**：leak flag 为空；用的是 `spec()`（手臂的轴、位置、限位，两台相机的位姿和视场）、腕部 RGB 和深度、底盘 RGB、里程计、关节角和 `gripper_pos`（大于 0.95 算没夹住）；`gen.py` 写死的拉手、柜面法线和方块坐标都是它 ep0 自己量的。看过的 36 张图 33 张在 ep0，之后靠日志里的数字调。
### full
- **读源码定目标、先拉抽屉**：0.84 min 从 `_check_goals` 和 `goal_state` 看出目标是上层中间那格，17.06 min 确认目标区域跟着抽屉 `kitchen_island_drawer_s1c1` 走；直接下探撞台面边沿，夹持点停在拉手外几厘米（37.47 min "the arm’s loaded joints settle a few centimeters away"），改了几版绕开台面的航点，41.79 min 第一次拉动 1.4 cm，46.38 min 找到先抬手再开回、抽屉停在约 7 cm 的办法。
- **推扫只挪几厘米**：打算把方块沿 +x 推过台面前沿（它记的约 x 0.875）掉进露出的抽屉，用张开夹爪的指垫推三趟；57.88 min "they only nudge the cubes a few centimetres per pass"，最终最靠前的方块在 x 0.838；两次试夹方块都没夹起。
- **步数被开抽屉占掉**：交的 949 步里开抽屉到开回占前 581 步（下探拉手一段用满 400 步上限），推扫 368 步；两次回放都没成功、终态一致；NOTES.md 停在 43.52 min 的旧版本。
### 两种模式
- **分界在开抽屉和搬方块的办法**：limited 把手沿柜面法线横着伸向横杆，ep0 第一次在拉手处合爪就拉开，再逐块夹起放进拉出的那段；full 从上方下探，撞台面边沿、夹持点停在拉手外几厘米，41.79 min 才拉动，最后用张开的夹爪推方块，两次试夹都没夹起。
- **拉手高度两边一致**：limited 用深度量到 z 0.326，full 读到 0.325；limited 没有接触信息，靠 `gripper_pos` 判断夹没夹住，full 看接触列表。两边都没用说明里提到的刮板。

## 改进意见
- **`spec()` 仍没有夹爪抓取点**：`arm` 有七个关节的轴和位置、`cameras` 有腕部相机位姿，却没有两指之间抓取中心的位置；这次 limited 从 3.87 min 起按第 7 关节前 0.18 m 解 IK（`gen.py` 注释 "jaw center from joint 7"），full 的 IK 用的是模型里的 `robot_pinch_site`。建议在 `spec()["arm"]` 里加上抓取点在各关节为 0 时的位置和朝向。

## 和旧版比
- **第一版 limited（白地面、有 `room_camera`、无深度）**：fail，50 次 reset 用完：靠 `room_camera` 像素按假设高度反投，拉手高度估成 0.75 m，73 次在拉手处合爪全空，抽屉一次没开。这次过：没有 `room_camera`，转底盘、压腕部相机找到方块，底盘相机里木地板与柜面的分界给出柜面方向。
- **深度解决了高度**：拉手直接量在 z 0.326（第一版估 0.6–0.85 m），ep0 第一次在拉手处合爪就拉开抽屉，时间转到了搬方块上。两轮都在 ep0 先夹起一块方块又放回台面。
