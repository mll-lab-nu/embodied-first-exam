## 总体结论
- **过线**：GPT-6 Luna 在 5 个计分任务上 limited 2/5（sweep-into-drawer、balance-beam）、full 3/5（tossing、balance-beam、shelf）；夹具 dynamo 两种模式都过。两种模式都过的只有 balance-beam；sweep-into-drawer 只有 limited 过了。
- **没有外部相机，找东西变成主动感知**：底座相机 0.335 m 高、俯 45°，只看得到脚下，agent 得转底盘、抬起腕部相机去找。dynamo 第 119 步才在抬起的腕部相机里看到绿格；tossing 55.17 min 才找到箱子；shelf 的绿块在 105 张图里一次都没出现。
- **腕部深度补上了高度**：sweep-into-drawer 的拉手直接量在 z 0.326（第一版估 0.75 m），scoop-pour 的方块 z 0.479 在 1.74 min 就定出，balance-beam 按深度拟合横梁倾角配平（ep11 −22.6° → ep12 −0.32°）。
- **抓取仍是最大卡点**：`spec()` 没有夹爪抓取点，每个任务都得自己试。scoop-pour 勺柄合爪 21 次只夹住 1 次；shelf 第 8 次合爪才夹住，方块一举高就掉；tossing 27.24 min 才第一次夹住。过线的两个都是先在 ep0 把定位和抓取标定好，再写成 `gen.py` 每局整局重放、每局只改一处。
- **判成功不要求松手**：balance-beam 两种模式、sweep-into-drawer 的 limited，都是最后一块还夹在手里时判成功。KinDER 的目标检查只看方块中心在区域里，这是上游的判定。
- **防泄漏**：limited 只用了底座 RGB、腕部 RGB-D、里程计和 `spec()`，leak flag 全空；full 读 kinder 包源码是设计允许的。
- **筛选其余 24 个任务族**：full 过了 23 个，多数在 20 min 内；limited（3D 的 14 个）过了 9 个。难的是 sweep-simple（两种模式都没过）、sort-blocks 和 constrained-cupboard（limited 没过，full 到步数或时间的最后才过），以及 limited 下的 obstruction-3d、packing-3d。

## GPT-6 Luna
### limited
- **过线的两个**：sweep-into-drawer 用深度定拉手，沿柜面法线横着夹住，ep0 第一次合爪就拉开抽屉；之后逐块从上方夹起放进去，IK 改成从 9 个初值里取最优，ep10 第 867 步过。balance-beam 三次闭合试出夹持偏移，写成脚本后 73 次闭合 62 次夹起，逐局按 1–2 cm 调落点，ep22 过。
- **没过的三个**：tossing 找到箱子时只剩约 5 min，4 次抛只有 1 次过墙；shelf 底座离起点没超过 0.31 m，一次也没在柜口前松手；scoop-pour 夹住勺子时只剩约 7 min，推了几回勺里没进方块。
- **时间和 reset**：5 个都用了 39.6 min 以上，3 个用满 60 min；reset 用 6–22 次，没有一个用完。
### full
- **靠真值和源码**：三个过线都读了物体坐标和目标检查，在模型的 `robot_pinch_site` 上做 IK；tossing 在快照上搜了上万组抛掷，shelf 用接触列表找到 45° 手腕。
- **多步接触操作没做成**：sweep-into-drawer 从上方下探拉手，41.79 min 才拉开约 7 cm；scoop-pour 夹得起勺子，舀、铲、掀箱都没送进一块，交的是最后一次实验。
### 两种模式
- **full 的优势在坐标和抓取点**：tossing、shelf 的 limited 输在找目标和抓取上，full 开局就有坐标和 `robot_pinch_site`。
- **sweep-into-drawer 反过来**：limited 横着夹拉手、逐块夹放，比 full 从上方下探再推方块更对路；两边量到的拉手高度一致（0.326 对 0.325）。

## 对照实验
- **外部相机（dynamo）**：同一新设置下加上外部相机，第一张图里就看到绿格，64 步、3.4 min 通过；标准设置（没有外部相机）要 165 步、4.4 min。

## 筛选：KinDER 其余 24 个任务族
- **范围**：每族一个偏难变体（上游 baseline 配置过的最难变体，否则物体不超过 10 个的最难变体），GPT-6 Luna 每种模式各跑一次，不计入上面的通过数。3D 任务两种模式都有：Franka 和 PyBullet 机器人也只给机器人自己的传感器，没画出来的目标用机器人自己的坐标系说明。2D 任务只有 full，因为能给的传感器只有整张地图。LimbRepositioning3D 需要的 IKFast 在镜像里编不了，没有跑。
- **full 23/24 通过，多数很快**：Kinematic3D 8/8（0.5–17.0 min），Kinematic2D 6/6（1.4–15.8 min）。几次通过靠的是运动学环境的特性：松手后物体停在半空（prpl-lab-3d、obstruction-2d），或者判定不要求松手（franka-pick-place、push-pull-hook-2d）。
- **sweep-simple**：两种模式都是 0/10。底盘从 2 cm 的方块上开过去，推不动它们；刮板夹不稳。full 最后用指垫扫了 536 步，只挪动了 4 块。
- **sort-blocks**：limited 最好的一局只放对 1 块，被评分的那局夹错了块，还撞翻了箱子。full 用了 42.6 min，轨迹到第 1000 步（最后一步）才成功。
- **constrained-cupboard**：要夹住杆的一端、转腕插进 10 cm 宽的格子，6 根要在 1000 步内做完。full 59.5 min 才存下能过的轨迹，离时限半分钟。limited 找对了六根杆和对应的柜子，但脚本把目标深度的符号写反，六根都放到了柜前地上；它 47 min 才发现，这时 reset 已经用完。
- **limited 没过的另外两个**：obstruction-3d 把方块和红块定位到毫米级，但往下夹时爪子停在红块上方，一直没夹住；它用交互式 shell，每条命令空等 30 s，一小时只走了 283 步。packing-3d 三件都一次夹起，但松手常被拒（离托盘面超过 5 mm），一局最多放进一件。
- **limited 过了的 9 个**：pick-place、franka-pick-place、base-motion-3d、table-3d、transport-3d、kinematic-shelf-3d、cylinder-shelf-3d、prpl-lab-3d，以及 rearrange。都是用底座相机和腕部深度加正运动学找东西。base-motion-3d 的球浮在 0.2 m 高，底座相机扫不到，抬起腕部相机才找到。Franka 合爪三次都空了（MuJoCo 机器人的 `spec()` 没有夹爪抓取点，见改进意见），改成用爪子把方块推过去。
- **rearrange**：full 用了 5.4 min。limited 找物体花了 12.6 min，试抓取又花了约 14 min，ep11 在约 49 min 时才过。
- **dyn-push-pull-hook-2d**：用了 34.4 min，其中 21 min 花在夹住钩子上。它利用钩子能穿过中墙这一点（KinDER 允许），从上往下扫。
- **dyn-scoop-pour-2d**：第一次运行两次回放都到了目标，但结束状态不同，因此判 0。这是我们工具的问题（见各版的改动）。修好后重跑，13.7 min 通过。

## 改进意见
- **`spec()` 补夹爪抓取点**：5 个任务的分析都指出了这一点。`arm` 有关节轴、位置和两台相机的位姿，却没有两指之间的抓取中心（模型里的 `robot_pinch_site`）和开合方向；这是 URDF 和夹爪手册里本来就有的机器人事实。建议补上它在关节为 0 时的位置和朝向（改后要重新 render 和 measure）。

## 各版的改动
- **第 1 版 → 第 2 版（09-29）**：场景换成 KinDER 的 MimicLabs 实验室（只影响画面）；limited 去掉外部相机，改给机器人自己的两台相机，腕部带深度。上线前发现并修复了服务端的串帧（RGB 和深度各用一个渲染器时，会互相拿到对方的帧），出 bug 的那批运行作废重跑。limited 从 0/5 变成 2/5；full 物理不变，结果沿用。
- **筛选工具（09-29）**：
  - 生成器扩展到 KinDER 的 2D、PyBullet 和 Franka 任务，这些任务只有 full。
  - 修了 Pymunk 回放不确定的问题：一步物理计算里新加入的物体，原来按内存地址的顺序加入。夹起由两段组成的钩子后，同一串动作会回放出不同的结果。受影响的一次 dyn-scoop-pour-2d 运行已作废并重跑。
  - 原来 6 个任务的说明和判定都没变。
  - 最早开跑的 13 个筛选运行，看到的是改正前的说明：单局耗时只按原地不动估算；非 MuJoCo 任务的 `set_state` 说明没写会漂移。分析里没有发现这对结果有影响。
- **3D 任务的 limited（09-29）**：
  - 服务端改成每种机器人一个适配器：TidyBot++ 的输出与之前逐字节一致。
  - Franka：模型里没有机载相机，就按 TidyBot++ 腕部相机相对同款夹爪的位置装了一台。
  - PyBullet 机器人：TidyBot++ 的两台相机装在同名的 link 上；腕部相机前移 3 cm，避开这个模型夹爪自带的相机壳。上游自带的机载相机因为四元数顺序写错，朝向不对，没有用它。
  - 11 个任务新写了 limited 的目标句：目标原来用世界坐标或状态名说明的，改成机器人自己的坐标系，数字都是实测的。
  - base-motion-3d 的球在 PyBullet 里画成不透明，所以目标句里去掉了 "translucent"。这一改动在两个运行之后。
