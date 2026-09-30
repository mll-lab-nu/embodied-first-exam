**一句话**：packing-3d 要把一块方块和两块直角三角放进托盘：在内轮廓里、平贴底面、互不重叠，最后爪里不留东西。难在"放"：夹着的零件离能托住它的面不到 5 mm 才松得开，往下放时一碰到东西这一步就被拒（`blocked`），碰到了什么、放没放对都只能自己从相机判断。limited 50 次 reset 一次没用，在 ep0 里逐件现场装盘，54.94 min 三件都进了托盘仍没判成功，又摆平、挪位、压低，第 1657 步（59.19 min）过；full 读真值、用 PyBullet IK 逐件放，9.1 min 交出 196 步，第 191 步成功。

## GPT-6 Luna
### limited
- **reset 用 0/50，一局现场做完**：没调用过 `reset()`；找不到第三件（23–32 min）、第三件撞上方块（37 min）都在原局里补救，每改一处就查一次 `done`。`gen.py` 是成功后（59.60 min）才写的，只含第 1566 步之后的 4 次 `placement`，它自己说 "the earlier pick-and-place work was performed interactively and isn’t included in the script"。
- **`end_effector` 当 FK 工具点，夹得准**：0.82 min 起 FK 就算到 `end_effector` 的 [0.1199, −0.0249, 1.3022]，之后的脚本按键名读 `s['arm']['end_effector']['position_m']`；腕部深度定钉，IK 把这个点送到钉上，除第 16 步离钉还高约 5 cm 之外，对准钉的合爪都夹住了。没有 leak flag。
- **`blocked` 出现 35 次，每次都停下换做法**：13 次底座、22 次手臂。底座从第 13 步起停在 (0.1, 0.08, yaw 1.0)，之后 12 次挪底座都被挡，它改用手臂伸出去扫，32.57 min 才看到第三件；下探被挡就在该高度开爪，松不开再每降 2 mm 开一次（"Small incremental descents followed by open attempts worked when a larger planned descent was blocked"）。第 989–991 步第三件撞上方块，42.40 min 起用多边形分离检验在托盘轮廓里给三件重新排位。
- **三件进盘后没判成功，现场修到最后一分钟**：49.79 min 用深度拟合平面，把斜 7.4° 的方块和斜 14.2° 的一块三角重新夹起摆平；54.94 min "The service still hasn’t marked success"，又挪了两块三角的位置、各压低 2 mm（末端 z 0.158 → 0.156），第 1657 步松开最后一块时判 `success`。哪一处调整起了作用，记录里看不出来。
### full
- **真值、源码和末端点都是现成的**：打印 state 拿到三件零件和托盘 `rack` 的坐标（中心 (0.3, 0)，半边长 0.1×0.15×0.02），读了 `packing3d` 源码和抓取区尺寸 (0.01, 0.01, 0.035)。它用 PyBullet `calculateInverseKinematics` 驱动末端点，合爪后查 `grasp_active`，开爪后查 `grasped_object`，一失败就带着状态报错。
- **也卡在松手，靠内部状态查出原因**：part1 连续 5 次松不开，打印出 `_get_surfaces_supporting_object` 为空。6.73 min："the triangle pickup had descended lower than the square pickup, so the held triangle sat about 18 mm too high"，于是三件都改在同一高度（末端 z 0.1578）夹钉。试过把三角转 180°，两次 "IK missed target"，就改成两块三角斜向对拼。
- **7.91 min 第一次成功**：交 196 步，回放第 191 步成功，两次一致；最后一帧三件都在托盘里。
### 两种模式
- **分界在能不能知道碰到了什么、放得对不对**：full 每次松不开都能读到零件高度和支撑面，从第一次松不开到成功只用了 4.3 min；limited 35 次被挡都只拿到 `blocked: true`，三件进盘后只知道还没成功，靠深度拟合平面、挪位、压低一处处试，从 54.94 min 修到 59.19 min 才等到 `success`。

## 对照实验
- **无 reset 的对照没过**（60 min `timeout`，764 / 3000 步）：同样一局现场逐件放，但压缩前 36 min 一次调用只走一到几步、只到第 152 步；方块卡在第一块三角旁 30 min，压缩后才看出要先把三角挪开；第三件又放了 12.6 min，58.21 min 三件都松了手仍是 `done: False`，再挪一块三角时 60 min 到。

## 和旧版比
- **旧版（50 次 reset，PyBullet 已有 `end_effector`，没有 `blocked`）没过**：用了 6 次 reset，每局最多一件完整进托盘，60 min `timeout`；这次只多了 `blocked`，35 次都停下换做法，同一局三件都放进并过了。两边开爪松不开的次数相近（旧版方块开到第 14 次、这次三角开到第 13 次才松），各只跑一次，差别不能全算在 `blocked` 上。
- **无 reset 的对照是重跑的**：第一次任务文字和 spec 都一样，服务端 `blocked` 漏报了 2 步，也是 60 min `timeout`。
