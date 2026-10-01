**一句话**：obstruction-3d 要先挪开压在垫子上的红块，才能把紫块放到只比它略大的垫子上（垫子 7.8 × 5.6 cm，紫块 6.3 × 4.5 cm）。难在 kinematic 规则：会碰撞的那一步不执行，开爪只在物体离支撑面 5 mm 内才松，合爪时手指碰到垫子或邻块也夹不住。limited 只在 1.37 min 用了 1 次 reset 撤掉探看，之后 58 min 都在 ep1 里现场操作：挪走两块红块，紫块没放上垫子，第 1004 步时 60 min 到，`timeout`；full 读真值、先查碰撞，11.1 min 就交了第 1306 步成功的轨迹。GPT-6.1 Sol 两种模式都过：limited 不 reset，一局第 428 步成功（5.0 min）；full 2.7 min 交 1011 步。

## GPT-6 Luna
### limited
- **reset 用 1/50，没换来标定后重放**：ep0 探看 17 步（1.35 min "turning it sideways confirms it is too low to see the objects clearly"）后 reset，此后每次空夹、松不开手都在 ep1 里原地补救；`gen.py` 到最后还是 10 行的 reset 加存图，交接摘要自己写着 "It must be replaced with a complete runnable driver"。ep1 走了 1004 / 3000 步，用完的是 60 min。
- **`end_effector` 用上了，`blocked` 当成接触信号**：5.78 min 起 FK/IK 以 `spec()["arm"]["end_effector"]` 为工具点，按像素颜色加腕部深度定位，9.11 min 第一次合爪就夹住紫块（0.4375）。`blocked` 在 ep1 出现 37 次（8 次底座、29 次臂），步进循环遇到就停；21.48 min 由此看出 "The descent stopped at the red block on the pad, about 2 cm above the pad surface"，第 138 步（24.02 min）把紫块放到桌面空处，改去清垫子。没有 leak flag。
- **松手吃掉大段时间**：spec 写明开爪只在物体离支撑面 5 mm 内才松，交接摘要也记了这条，但中间那块红块 27.34 min 夹住后，在几个高度上直接开爪 21 次、到 44.11 min 才松；44.04 min 改成 "checking the release height in 5 mm increments" 后两档就松了。
- **上下文压缩后 FK 写反**：35.51 min 压缩，交接只写了 "a product of revolutions about the specified pivots"；35.94 min 按 "spatial POE" 重写、连乘顺序反了，一直用到 45.72 min，其间 45.24 min 按错的坐标去夹紫块，空夹。48.54 min 改正后才重新清垫子。
- **最后 2 min 直接放紫块**：垫上又一块红块前四批合爪空、53.77 min 才夹住，第 741 步放到桌上；剩下那块两次空夹。57.70 min "the episode clock is close to its limit"，夹起紫块往垫子空的一侧下探，第 972、976、1001 步 `blocked`，4 次开爪都没松。
### full
- **真值、源码加碰撞查询**：读状态表和 `obstruction3d.py`，查到抓取判定用的标记半尺寸是 (0.01, 0.01, 0.035)。用 PyBullet IK 驱动末端点，爪子保持竖直，从 z 0.30 分段下探到 0.14，底座一步没动。
- **两次夹取失败都离线查清了**：obstruction0 合爪时手指碰到垫子，扫一遍高度后把末端点定在块心上方 4 cm；obstruction1 合爪时碰到邻块 obstruction3，把抓取点挪 20 mm。每次各用 1–2 min。
- **11.1 min 交卷**：三块红块挪到 (0.20/0.30/0.40, −0.25)，紫块放在垫子中心、离垫面 2 mm。1306 步，第 1306 步成功，两次回放 state SHA 相同；花了 $0.0628，没看图。
### 两种模式
- **分界在碰撞信息和松手**：full 每一步之前都能先查会不会碰、为什么合爪失败，按块底离支撑面 2 mm 松手，1306 步离线跑完只用 11.1 min；limited 从 `blocked` 只知道这一步被拒、不知道碰到了什么，松手高度要现场一档档试，一块红块就开了 21 次爪。
- **先后顺序也不同**：full 先清三块红块，最后才碰紫块；limited 先夹紫块往垫子上放，被垫上的红块挡住才回头清垫子，60 min 到时垫上还有一块红块。

## GPT-6.1 Sol
### limited
- **一局做完，reset 用 0/50**：0.63 min 写 FK/IK（工具点 `end_effector`，相机位姿取 `spec()`），1.71 min 底座后退 0.2 m 从高处拍一张腕部 RGB-D，定出三块压垫红块 (0.224, 0.208)、(0.267, 0.219)、(0.224, 0.246) 和垫面高 0.0851，此后夹取点直接用这组数。第 428 步 `success`，5.0 min、$0.2718、15 张图。
- **空夹后转爪子，不在高度上反复试**：竖直下探两次 `blocked`（第 176、206 步），三次合爪都空；2.69 min 把爪子绕竖轴转 π/2，第 234 步仍 `blocked` 但夹住了，此后三块红块各一次合爪、一次开爪（3.26 min "The gripper needed a quarter-turn to approach the clustered blocks"）。
- **紫块松手两次**：下探到 z 0.165 时第 424 步 `blocked`（末端停在 0.183），开爪没松；改下到 0.169，第 428 步开爪即判成功。没有 leak flag。
### full
- **真值加一个通用的 `transfer`**：读状态表和 `obstruction3d.py`、`base_env.py`，IKFast 装不上改用 `pybullet_inverse_kinematics`，按 8 mm 一段的路径点驱动竖直的爪子；夹取高度取块顶上方 3.2 cm，放置用 `_grasped_object_transform` 反算末端位姿，块底离目标面 3 mm 开爪。
- **只调了一处**：第一次合爪（末端 z 0.140）没夹住 obstruction0，降到 0.137 后整条跑通；三块红块挪到 y −0.16 一排，紫块放垫子中心。
- **2.7 min 交卷**：1011 步、第 1011 步成功，两次回放 state_sha 都是 `7f85754103ebda7d`；$0.2163，没看图。
### 两种模式
- **两边都很快，limited 步数反而更少**：limited 把 `blocked` 和夹爪读数当反馈，转 90° 夹挤在一起的红块，一局 428 步；full 能读源码和抓取状态，竖直爪子加 ±1 cm 的抓取偏移，1011 步。用时 5.0 min 对 2.7 min。

## 对照实验
- **无 reset 的对照也没过**（ep0 第 163 步时 60 min 到，`timeout`）：163 次调用各发 1 步，关节增量在 REPL 里算出再手抄进下一条 `r.step`，模型生成合计 43.5 min；它端着紫块往被占的垫子上探了 10 次、约 16 min，放下紫块又用了 22 min，红块三次合爪都空。

## 和旧版比
- **旧版（50 次 reset，没有 `blocked`；PyBullet 的 spec 原本就有同一个 `end_effector`）没挪动一块红块**：283 步，底座移动不执行也查不出原因；这次 21.48 min 从 `blocked` 看出红块挡路，挪走两块，也没过。步数差主要来自旧版在 `python -i` 里 58 次各等满 30.1 s（这次所有工具调用合计 3.2 min）。
- **第一次无 reset 运行通过了**（第 408 步，27.1 min）：任务文本和 spec 与无 reset 的对照相同，只是服务当时把 16 步被拒里的 2 步报成 `blocked: false`（已修）；它只挪走中间那块红块就放上了紫块，单次运行之间差别很大。
