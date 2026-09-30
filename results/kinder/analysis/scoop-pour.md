**一句话**：scoop-pour 要把黄箱里 30 块小方块全部移进旁边的绿箱（场景里有一把小勺），方块得越过黄箱箱壁、落进绿箱内侧，两个箱子都在离地约 0.46 m 的岛台上。limited 只有一局：用上 `end_effector` 后第一次合爪就夹起勺子，推扫时勺里一直是空的，勺子滑脱后改单夹，最后夹住的是黄箱箱壁、把整个黄箱拖到贴住绿箱，第 1000 步 `failed`；full 7.3 min 就夹起勺子，但舀、铲推、掀黄箱、翻绿箱都没送进一块，交的 660 步回放失败。

## GPT-6 Luna
### limited
- **前 10 min 手动凑，用上抓取点后一次夹住勺子**：0.75 min 腕部相机就看到两箱和勺子（"a scoop-shaped object is between them"）；之后一次挪几步关节、看一张图，第 54–172 步 8 次合爪全空。10.27 min 起 FK 按键名读 `spec()["arm"]["end_effector"]`、关节位置和轴、腕部相机位姿，腕部深度反投出勺柄 z 约 0.50，用位置 IK 下探，第 210 步这样第一次合爪就夹住（0.786）。
- **勺子舀不上，推扫中滑脱**：勺子举到黄箱上方，底盘来回横移、压关节推了约 70 步，腕部图里方块在勺前、勺面始终是空的；第 282–284 步读数 0.867 → 0.976，28.95 min "The scoop slipped loose during the sideways sweep"，再合三次都没夹回。
- **单夹一次一块，也没送到**：合爪 5 次，只有第 444 步（0.883）提起一块，底盘每步 +0.1 m 往绿箱挪，第 450 步读数到 0.979，块掉了。这时已 38.5 min、第 451 步：前 451 步多是 1–10 步一次的试探，边走边看图（全场 133 张）。
- **最后夹住的是黄箱**：第 721 步合爪停在 0.632，它当成方块（46.35 min "The cube pickup registered finger contact"）；回放里抬手和底盘 +y 横移时整个黄箱跟着走，把绿箱推歪。之后来回找绿箱，第 1000 步松爪 `failed`，绿箱是空的；46.4 min 收尾，`gen.py` 只记了第 463 步之后那一段。
### full
- **读源码和状态**：读了 `ScoopPour3D-o30.json`、`_check_goals`、`Bin.check_in_region`，打印出勺子、两箱和 30 块方块的坐标；6.25 min "The task checker uses a box region attached to the green bin, so the bin's pose affects success"。
- **勺子夹得起、舀不上**：以 `robot_base` 体为末端做 IK 夹勺柄，7.28 min 勺子离台（z 0.46 → 0.557）；横扫 "drove cubes toward the bin's far edge instead of loading them"（12.64 min），47–57 min 又试倾 18°、40°、70° 和放平，扫完没有方块越过 y −0.05，57.24 min "The spoon tests still leave nearly all cubes inside the yellow bin"。
- **铲推、掀黄箱、翻绿箱都没进一块**：夹爪当铲子推了 7 块进两箱之间的空隙；夹住黄箱壁把它掀起约 90°，每次 `in green xy 0`；把绿箱侧翻（45.04 min）再往方块推，`goals False`。每个想法一个手写脚本、没有做参数搜索；32.23 min 才发现 IK 在改动正在跑的仿真，之前录的动作回放对不上。
- **交的是最后一次实验**：实验脚本末尾都无条件存 `/app/output/trajectory.npz`，交上去的是 58.65 min 推侧翻绿箱的 660 步；`NOTES.md`、`gen.py` 一直是开头的全零占位。
### 两种模式
- **夹勺子已不是分界，舀起方块是**：full 用状态坐标做 IK，7.3 min 勺子离台；limited 用 `end_effector` 加腕部深度解 IK，13.8 min 第一次这样合爪就夹起。拿到勺子后两边都没舀上一块：full 舀、铲推、掀黄箱、翻绿箱都试了，limited 推了约 70 步勺子就滑脱。
- **limited 的失手收不回来**：一局里掉进黄箱的勺子三次没夹回，拖歪的黄箱也留在那里；full 每次实验都从头重来。

## 对照实验
- **50 次 reset 也没过**：同一版本给 50 次 reset，用了 8 次、60 min 超时。reset 换来的是可回放的标定（勺柄停位和悬停关节角、接触高度 z 0.50、像素水平符号），ep5、ep8 夹勺子都一次夹住，`gen.py` 逐块夹放 ep7 送进 1 块（自报 3 块）；但 ep1–ep5 每局换一种做法、手动试，被评分的 ep8 在 58.92 min 才开始，第 193 步超时，绿箱是空的。

## 和旧版比
- **抓取点让夹勺子早了，结局没变**：旧版（50 次 reset、没有抓取点）勺柄合爪 21 次，ep9 52.83 min 才夹住，勺里没进过方块；对照组 39.26 min（ep4）夹住勺子，之后 ep5、ep8 都一次夹住，也没舀上。两边被评分那局的绿箱都是空的。`blocked` 只在 PyBullet，这里不涉及。
