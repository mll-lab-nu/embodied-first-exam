**一句话**：scoop-pour 要把黄箱里 30 块小方块全部移进旁边的绿箱（场景里有一把小勺），方块得越过黄箱箱壁、落进绿箱内侧，两个箱子都在离地约 0.46 m 的岛台上。limited 前 5 局每局手动试一种做法，勺子夹得起却没舀上一块，逐块夹放的 `gen.py` 一局最多看到 1 块进绿箱，被评分的 ep8 在 58.92 min 才开始、第 193 步 60 min 超时，绿箱是空的；full 7.3 min 就夹起勺子，但舀、铲推、掀黄箱、翻绿箱都没送进一块，交的 660 步回放失败。

## GPT-6 Luna
### limited
- **抓取点用上了**：2.17 min 起 FK 的夹爪点是关节 7 沿连杆 z 0.2054 m，正是 `end_effector` 的 z 1.7261 减关节 7 的 1.5207；32.20 min 的 `gen.py` 点列末尾就是 [0.1199, −0.0249, 1.7261]。腕部红色掩码加深度把方块定在 z 约 0.487，ep1 第 157 步合爪 0.951 夹住一块。
- **reset 用来一局换一种做法、手动试**：ep1–ep5 分别是单夹、找勺子、夹勺柄、推扫、再单夹，每局一步步试，ep1 一局就从 1.11 min 到 20.39 min；27.53 min 才在两箱之间看到勺子（"hidden from the close wrist views"），`gen.py` 54.19 min 才第一次整局跑。换来的是可回放的标定（勺柄停位和悬停关节角、接触高度 z 0.50、像素水平符号），ep5、ep8 夹勺子都一次夹住（0.787、0.791）。
- **勺子没装上方块**：ep4 39.26 min 夹住勺子，在黄箱里推扫到第 996 步，47.11 min "the pan stayed empty"；ep5 推两次后松手，勺子留在黄箱里，之后把勺柄当方块夹到绿箱上方松手，仍说 "placed one cube into the green bin"。
- **逐块夹放只看读数**：`gen.py` 合爪读数没到 0.993 就记 "Placed"，松手后不看绿箱；ep7 整局 989 步报 "Placed 3 cubes"，末帧绿箱里只看得到 1 块，58.89 min 它自己说 "it cannot finish the 30 cube task within one episode"。
- **被评分的 ep8 刚开始就到时**：58.92 min reset，内联脚本照 ep5 夹勺子（第 97 步 0.791），把勺面压进黄箱的方块堆、向前推 4 cm，第 193 步 60 min 到，`timeout`；末帧勺子插在方块堆里，绿箱空着。
### full
- **读源码和状态**：读了 `ScoopPour3D-o30.json`、`_check_goals`、`Bin.check_in_region`，打印出勺子、两箱和 30 块方块的坐标；6.25 min "The task checker uses a box region attached to the green bin, so the bin's pose affects success"。
- **勺子夹得起、舀不上**：以 `robot_base` 体为末端做 IK 夹勺柄，7.28 min 勺子离台（z 0.46 → 0.557）；横扫 "drove cubes toward the bin's far edge instead of loading them"（12.64 min），47–57 min 又试倾 18°、40°、70° 和放平，扫完没有方块越过 y −0.05，57.24 min "The spoon tests still leave nearly all cubes inside the yellow bin"。
- **铲推、掀黄箱、翻绿箱都没进一块**：夹爪当铲子推了 7 块进两箱之间的空隙；夹住黄箱壁把它掀起约 90°，每次 `in green xy 0`；把绿箱侧翻（45.04 min）再往方块推，`goals False`。每个想法一个手写脚本、没有做参数搜索；32.23 min 才发现 IK 在改动正在跑的仿真，之前录的动作回放对不上。
- **交的是最后一次实验**：实验脚本末尾都无条件存 `/app/output/trajectory.npz`，交上去的是 58.65 min 推侧翻绿箱的 660 步；`NOTES.md`、`gen.py` 一直是开头的全零占位。
### 两种模式
- **夹勺子已不是分界，舀起方块是**：full 用状态坐标做 IK，7.3 min 勺子离台；limited 27.53 min 才看到勺子，39.26 min 用 `end_effector` 加腕部深度解 IK 夹住。拿到勺子后两边都没舀上一块：full 舀、铲推、掀黄箱、翻绿箱都试了，limited 推扫后勺面一直是空的。
- **两边都是一个想法手动试一次**：full 每个想法一个手写脚本、没有参数搜索；limited 每局 reset 换一种做法，8 局用完 60 min，被评分的 ep8 不是回放，是又一次试勺子。

## 对照实验
- **不给 reset 时绿箱也是空的**：同一版本只有一局，前 10 min 手动挪关节、8 次合爪全空，10.27 min 起按键名读 `end_effector` 写 FK/IK，第一次合爪就夹起勺子；推扫约 70 步勺面一直是空的、勺子滑脱，改单夹提起的一块在路上掉了，最后夹住的是黄箱箱壁、把黄箱拖到贴住绿箱，第 1000 步 `failed`。前 451 步就用了 38.5 min，多是 1–10 步一次的试探。

## 和旧版比
- **抓取点让夹勺子早了，结局没变**：旧版（50 次 reset、没有抓取点）勺柄合爪 21 次，ep9 52.83 min 才夹住，勺里没进过方块；这次 39.26 min（ep4）夹住勺子，之后 ep5、ep8 都一次夹住，也没舀上。两边被评分那局的绿箱都是空的。`blocked` 只在 PyBullet，这里不涉及。
