# knot_untying 摆放：设计答案

给 Qineng。对应交接包 `knot_placement/README.md` 第 5 节的问题 (a)(b)。

> **范围（维护者注，2026-10-14，board 0114）**：本目录是交接分支 `dev/pingyue_handover` 上的设计材料，针对
> `dev/robotangle_softbody_redesign` 的 knot_untying 重设计（带目标区域和 curb 的 tier：`easier_v8_r2`、`hard_nostop_r2`）。
> main 上 RoboTangle 已改名为 RoboARC（#186 / #187），main 的 `roboarc-knot-untying-*` 任务没有目标区域和 curb，
> 这里的路点不是它们的答案，也不用于它们的 oracle。这些文件不得拷进 `tasks/`、任务镜像或任何 agent 可见的文件；
> 若重设计的 tier 将来进入 RoboARC，参考路点只能放在 `scripts/roboarc/oracles/`（只在 solution / 验证侧）。

- 快照：`easier_v8_untied`、`hard_nostop_untied`（`data/snapshots.json`）。
- 目标区域：按 10-12 定下的 `_r2`，即 `easier_v8_r2`、`hard_nostop_r2`。

**结果怎么来的**：下面的数字都来自我们的物体级 MuJoCo 自查，不是你们的机器人环境。
- 用的是 `mjlab.py` 的绳子模型，从快照中心线建绳，代码在分支 `dev/pingyue-knot-place`（基于 `dev/robotangle_softbody_redesign`）的 `topogym/planning/knot_untying/redesign/place_obj.py`、`place_plan.py`。
- 夹爪换成虚拟手：握力 20 ms 均值超过 2.7 N 即脱手；握住时姿态不变，相当于不转腕。
- 每个抓取点和搬运路径都用 `robot_ik.pinch_feasible` 检查了 ALOHA 竖直捏取是否可解。
- 正式结果以你们环境跑出来的为准。

**交接包的一处更正**：`params.json` 里 fixtures 的 `half_extents` 存的其实是全尺寸（`tiers.block()` 用 `pos z = size_z/2`）。所以 curb 实际是：
- 高 3 cm、厚 2 cm；
- 长度 easier 34 cm、easy 40 cm、hard 30 cm、medium 40 cm。

README、`figs/` 和 `viewer.html` 里画的 curb 都大了一倍。快照里的绳子正好贴着全尺寸的 curb，而 README 里"绳子搭在 curb 上 z = 36 mm"正好是 30 mm 的 curb 加绳子半径，两处都印证这一点。夹子同理。

## 答案 (a)：摆放动作

### 方法

一只手按住已铺部分的末端，另一只手铺下一段，左右手交替。

1. **拉直第一段到 B1。** 取 s1 = |夹子–B1| + 1.5 cm，抓 s1，沿 strip 远侧东西向拉直到东端 B1，右手按住。
   - 右手够不到 s1 时：左手先抓 s1 往后约 12 cm 的点，贴桌平拉到中间（x≈0）；右手抓住 s1 后左手再松开。两爪沿绳相距 ≥ 12 cm。
2. **折回第二段，放在第一段南侧，相距 ≥ 3 cm。** 取 s2 = s1 + |B1–B2| + 3 cm，左手抓 s2，需要时抬 8 cm 越过 curb，拉到西端 B2 按住。
3. **第三段。** 左手抓 B2 弯本身，右手抓尾巴末端，双手抬 11 cm 越过 curb，平移放下。弯一直在手里，所以不会被拧成圈。
4. **收边。** 把松手后弹开的弯底往区域里推 1–2 次，然后松手退开。

**hard a 要先“搬进”。** 解结后，a 的拱形段（s 0.36–0.80）从 curb 北侧拱过，把内圈、小环和自由端包在它和 curb 之间（见下面的起点对比图）。
- 从夹子端先铺的任何顺序，都要让被包住的绳子绕过拱形段末端。我们试了 5 轮，最好的结果是 17% 在外、2 个交叉。
- 所以先用 5 次搬运，按“先被包住的、后拱形”的顺序把整根绳搬进 strip，做到 0 交叉；再按上面的第 1、2、4 步重铺。
- 第 3 步省略：第 2 步后尾巴已经躺在两段之间；而且尾巴在 x < -0.15，右手够不到。

**通用规则**（都是自查中实测出来的）：

| 规则 | 实测依据 |
|---|---|
| 握住时不转腕 | — |
| 搬运 ≤ 3 cm/s | — |
| 离夹子 24 cm 以内不先捏再抬 | — |
| 腿不能绷紧，余量约 1.5 cm | 余量 0.5 cm 时握力 2.7 N 脱手；3 cm 时腿中间留下约 3 cm 的波浪 |
| B1、B2 离区域边 ≥ 2.5–5 cm | 折弯被压得比自然大小（直径约 7 cm）更紧时，松手会弹开，两侧各多出约 1.7 cm |
| 按住点的切向要指向剩余绳子要去的一侧 | 方向反了，拐点处会形成卷环，之后消不掉 |
| 跨 curb 的那段要抬过去 | 平拉时 curb 会把绳挡成一条贴着 curb 的直线，后面的拉动也拉不下来 |
| 搬起时夹子到手之间的松量 ≤ 约 2.5 cm | hard 近腿松量到 4.3 cm 以上时会搭上 curb |
| 抓取点离 curb 顶 ≥ 2.5 cm | 搭在 curb 顶上的那段，夹爪放不进去 |

### 结果

| 列表 | 步数 | 名义（从快照一次连续跑完，orbits3） | ±1 cm 扰动：只看 goal / goal + 离边 ≥ 8 mm | 扰动中的主要失败 |
|---|---|---|---|---|
| easier：`answer/easier_v8_untied_user.json`（commit 7cc194d7a） | 33 | goal 通过；0 交叉，0% 在外，离边 10.8 mm，最小间距 8.4 mm，最大握力 0.75 N | 8/8 / 4/8（16 个种子：14/16 / 6/16） | 大多是 B2 弯底离南沿不到 8 mm；两次是 B1 圈北侧；一次 3.8% 在外；一次一开始就交叉 |
| hard：`answer/hard_nostop_untied_user.json`（commit 16a132e59） | 53 | goal 通过；0 交叉，0% 在外，离边 a ≥ 18.0 mm、b ≥ 18.1 mm，最小间距 8.9 mm | 8/8 / 7/8 | 唯一没到 8 mm 的一次：a 离南沿 7.4 mm |
| 备选 easier（最少移动）：`answer/easier_v8_untied.json` | 33 | goal 通过；离边 9.5 mm | 7/8 / — | 双手抬过 curb 那一步把内圈拖上别的绳 |
| 备选 hard（F7）：`answer/hard_nostop_untied.json` | 47 | goal 通过；离边 a 17.9 mm / b 18.2 mm | 4/8 / 3/8 | 一次抓取点搭在 curb 上，被拒；近腿贴在 curb 南面，越出北沿 4–6 mm |

**说明**
- “扰动”：每个 move 目标的 xy 加独立均匀的 ±1 cm 偏移，种子 0–7；easier 另跑了种子 8–15。
- 名义版在 orbits3 上跑，和本机逐位一致；扰动在另一台机器（vast1）上跑，判定和本机相同，但终态形状最多差约 0.5 mm。
- easier 离边这一项卡住，原因是 strip 西端太挤，不是方法本身，见答案 (b)。

### 每一步的理由（easier，33 步）

| 步 | 动作 | 理由 |
|---|---|---|
| 1–5 | 左手抓 s 0.80，贴桌平拉到 (0.065, 0.225)；右手抓 s1 = 0.67，左手松开 | s1 在起点处右手够不到。平拉把夹子侧的卷环拉开（弧长/弦长从 4.2 降到 2.0），也把 s1 送进右手可达范围。 |
| 6 | 右手沿北侧拉到 B1 (0.285, 0.272) 按住 | 第一段拉直，留 1.5 cm 余量（峰值握力约 0.2 N）。B1 离北边 3.8 cm，给松手后的弹开留余量。 |
| 7–10 | 左手抓 s2 = 1.30，抬 8 cm 越过 curb 西端，拉到 B2 (-0.30, 0.17) 按住 | 第二段拉直，在第一段南侧 2–5 cm。尾巴 s 1.30–1.79 被拖到 curb 南面。 |
| 11–14 | 先松 B1，再松 B2 | 两只手空出来去搬尾巴。B1 发夹弹开成约 7 cm 的圈，仍在区域内。 |
| 15–21 | 左手抓 B2 弯（s 1.33），右手抓自由端（s 1.77），双手抬 11 cm，平移到左 (-0.31, 0.195)、右 (0.11, 0.188) 放下，松手 | 两手之间的绳会下垂约 7 cm，抬 11 cm 才能整段越过 curb。弯一直在手里，不拧圈。 |
| 22–27 | 左手抓 B2 弯底 s 1.36，抬 1 cm 推到 (-0.31, 0.17)，松手 | B2 弯松手后往南垂到 y≈0.152，出了 8 mm 边距；往西北推，西侧有空间，不压第一段。 |
| 28–33 | 左手抓 s 1.40（弯底东半边），推到 (-0.25, 0.175)，松手，抬 5 cm 退开 | 只推一次，弯底会回弹到 y≈0.163；推两次后离南边约 1 cm。 |

### 每一步的理由（hard，53 步）

| 步 | 动作 | 理由 |
|---|---|---|
| 1–17 | b 修整：右手抓 b 的 s 0.66（发夹弯顶），放到 (-0.04, 0.215)；左手在同一点接手，放到 (-0.20, 0.25) 按住；右手抓 s 0.89，放到 (0.00, 0.205)；松手 | b 只有约 25% 在外。三次搬运把它铺成一个 U，四边离边 ≥ 18 mm，之后不再碰它。 |
| 18–21 | 搬进 1：左手抓西南小环底 s 1.34，抬 7 cm 放到 (-0.359, -0.285)，按住 | 拱形段把后面的绳包在里面，唯一出口是 a 西侧那段和 curb 西端之间的空当，这个小环正在出口上。 |
| 22–26 | 搬进 2：右手抓内圈 s 0.90，放到 (0.045, -0.31) 按住；左手松开 | 被包住的材料先进 strip 的远侧（南带）。 |
| 27–31 | 搬进 3：左手抓自由端段 s 1.507，放到 (-0.212, -0.253)，松开 | 右手仍按着 s 0.90，防止拉回。 |
| 32–36 | 搬进 4：左手抓拱形 s 0.42（这时拱形里已空），抬 7 cm 越过 curb，放到 (-0.005, -0.215) 按住；右手松开 | 夹子到手之间只留 2.4 cm 松量。松量到 4.3 cm 以上时，近腿会搭上 curb 西端。 |
| 37–42 | 搬进 5：右手抓拱形东侧 s 0.66，放到 (0.195, -0.262) 按住；左手松开 | s 0.68–0.74 有时搭在 curb 顶上，夹爪放不进去；s 0.66 在所有扰动下离 curb ≥ 25 mm。到这一步整根 a 已在 strip 内、0 交叉。 |
| 43–44 | 第 1 步：右手抓 s1 = 0.635（夹子到 B1 直线 + 1.5 cm），拉到 B1 (0.22, -0.225) 按住 | 第一段拉直。B1 离北沿 5 cm，给松手后弯头弹开（约 3 cm）留空间。 |
| 45–49 | 第 2 步：左手抓 s2 = 1.212，拉到 B2 (-0.32, -0.31) 按住 | 第二段在第一段南侧拉直；尾巴 s 1.25–1.507 这时已躺在两段之间，相当于第三段。 |
| 50–53 | 收边：左手抓 B2 弯底 s 1.262，贴桌往里推约 1 cm 到 (-0.34, -0.2825)；松手退开 | 弯头松手后会弹开，先往里推，弹开后也不出西沿 / 南沿。 |

### 列表

坐标为任务系；z 是夹爪接触点离桌面的高度；`grasp` 的 s 是从夹子量起的弧长。每步的理由也写在对应 JSON 文件的 `reasons` 数组里。

easier（`easier_v8_r2`，33 步）：

```json
[
 {"op": "grasp", "hand": "left", "rope": "rope", "s": 0.8},
 {"op": "move", "to": {"left": [0.065, 0.225, 0.005]}, "speed": 0.03},
 {"op": "grasp", "hand": "right", "rope": "rope", "s": 0.67},
 {"op": "release", "hands": ["left"]},
 {"op": "lift", "hands": ["left"], "dz": 0.04},
 {"op": "move", "to": {"right": [0.285, 0.272, 0.005]}, "speed": 0.03},
 {"op": "grasp", "hand": "left", "rope": "rope", "s": 1.3},
 {"op": "lift", "hands": ["left"], "dz": 0.08},
 {"op": "move", "to": {"left": [-0.3, 0.17, 0.084]}, "speed": 0.03},
 {"op": "move", "to": {"left": [-0.3, 0.17, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["right"]},
 {"op": "lift", "hands": ["right"], "dz": 0.04},
 {"op": "release", "hands": ["left"]},
 {"op": "lift", "hands": ["left"], "dz": 0.04},
 {"op": "grasp", "hand": "left", "rope": "rope", "s": 1.33},
 {"op": "grasp", "hand": "right", "rope": "rope", "s": 1.77},
 {"op": "lift", "hands": ["left", "right"], "dz": 0.11},
 {"op": "move", "to": {"left": [-0.31, 0.195, 0.114], "right": [0.11, 0.188, 0.114]}, "speed": 0.03},
 {"op": "move", "to": {"left": [-0.31, 0.195, 0.005], "right": [0.11, 0.188, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["left", "right"], "width": 0.016},
 {"op": "lift", "hands": ["left", "right"], "dz": 0.05},
 {"op": "grasp", "hand": "left", "rope": "rope", "s": 1.36},
 {"op": "lift", "hands": ["left"], "dz": 0.01},
 {"op": "move", "to": {"left": [-0.31, 0.17, 0.014]}, "speed": 0.02},
 {"op": "move", "to": {"left": [-0.31, 0.17, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["left"], "width": 0.016},
 {"op": "lift", "hands": ["left"], "dz": 0.05},
 {"op": "grasp", "hand": "left", "rope": "rope", "s": 1.4},
 {"op": "lift", "hands": ["left"], "dz": 0.01},
 {"op": "move", "to": {"left": [-0.25, 0.175, 0.014]}, "speed": 0.02},
 {"op": "move", "to": {"left": [-0.25, 0.175, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["left"], "width": 0.016},
 {"op": "lift", "hands": ["left"], "dz": 0.05}
]
```

hard（`hard_nostop_r2`，53 步）：

```json
[
 {"op": "grasp", "hand": "right", "rope": "b", "s": 0.66},
 {"op": "lift", "hands": ["right"], "dz": 0.0298, "speed": 0.02},
 {"op": "move", "to": {"right": [0.05, 0.205, 0.034]}, "speed": 0.03},
 {"op": "move", "to": {"right": [-0.04, 0.215, 0.034]}, "speed": 0.03},
 {"op": "move", "to": {"right": [-0.04, 0.215, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["right"], "width": 0.016},
 {"op": "grasp", "hand": "left", "rope": "b", "s": 0.66},
 {"op": "lift", "hands": ["left"], "dz": 0.0298, "speed": 0.02},
 {"op": "move", "to": {"left": [-0.05, 0.25, 0.034]}, "speed": 0.03},
 {"op": "move", "to": {"left": [-0.2, 0.25, 0.034]}, "speed": 0.03},
 {"op": "move", "to": {"left": [-0.2, 0.25, 0.005]}, "speed": 0.02},
 {"op": "grasp", "hand": "right", "rope": "b", "s": 0.89},
 {"op": "lift", "hands": ["right"], "dz": 0.0298, "speed": 0.02},
 {"op": "move", "to": {"right": [0.0, 0.205, 0.034]}, "speed": 0.03},
 {"op": "move", "to": {"right": [0.0, 0.205, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["left", "right"], "width": 0.016},
 {"op": "lift", "hands": ["left", "right"], "dz": 0.05, "speed": 0.03},
 {"op": "grasp", "hand": "left", "rope": "a", "s": 1.34},
 {"op": "lift", "hands": ["left"], "dz": 0.0698, "speed": 0.02},
 {"op": "move", "to": {"left": [-0.359, -0.285, 0.074]}, "speed": 0.03},
 {"op": "move", "to": {"left": [-0.359, -0.285, 0.005]}, "speed": 0.02},
 {"op": "grasp", "hand": "right", "rope": "a", "s": 0.9},
 {"op": "lift", "hands": ["right"], "dz": 0.0698, "speed": 0.02},
 {"op": "move", "to": {"right": [0.045, -0.31, 0.074]}, "speed": 0.03},
 {"op": "move", "to": {"right": [0.045, -0.31, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["left"], "width": 0.016},
 {"op": "grasp", "hand": "left", "rope": "a", "s": 1.507},
 {"op": "lift", "hands": ["left"], "dz": 0.0698, "speed": 0.02},
 {"op": "move", "to": {"left": [-0.212, -0.253, 0.074]}, "speed": 0.03},
 {"op": "move", "to": {"left": [-0.212, -0.253, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["left"], "width": 0.016},
 {"op": "grasp", "hand": "left", "rope": "a", "s": 0.42},
 {"op": "lift", "hands": ["left"], "dz": 0.0698, "speed": 0.02},
 {"op": "move", "to": {"left": [-0.005, -0.215, 0.074]}, "speed": 0.03},
 {"op": "move", "to": {"left": [-0.005, -0.215, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["right"], "width": 0.016},
 {"op": "grasp", "hand": "right", "rope": "a", "s": 0.66},
 {"op": "lift", "hands": ["right"], "dz": 0.0698, "speed": 0.02},
 {"op": "move", "to": {"right": [0.195, -0.262, 0.074]}, "speed": 0.03},
 {"op": "move", "to": {"right": [0.195, -0.262, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["left"], "width": 0.016},
 {"op": "release", "hands": ["right"], "width": 0.016},
 {"op": "grasp", "hand": "right", "rope": "a", "s": 0.635},
 {"op": "move", "to": {"right": [0.22, -0.225, 0.005]}, "speed": 0.02},
 {"op": "grasp", "hand": "left", "rope": "a", "s": 1.212},
 {"op": "lift", "hands": ["left"], "dz": 0.08, "speed": 0.02},
 {"op": "move", "to": {"left": [-0.32, -0.31, 0.0842]}, "speed": 0.03},
 {"op": "move", "to": {"left": [-0.32, -0.31, 0.005]}, "speed": 0.02},
 {"op": "release", "hands": ["left", "right"], "width": 0.016},
 {"op": "grasp", "hand": "left", "rope": "a", "s": 1.262},
 {"op": "move", "to": {"left": [-0.34, -0.2825, 0.005]}, "speed": 0.01},
 {"op": "release", "hands": ["left"], "width": 0.016},
 {"op": "lift", "hands": ["left", "right"], "dz": 0.05, "speed": 0.03}
]
```

## 答案 (b)：区域和 curb

**结论**：按 `_r2` 区域，strip 类各档的摆放是合法的，也是合理的。
- **合法**：同一个形状生成函数在 12 个 strip 型实例上都找到了 3–4 条腿的形状（离边 ≥ 1.5 cm），各拐点在贴桌、抬 3 cm、抬 7 cm 时竖直捏取都可解。
- **合理**：两只手都能够到的范围只占 strip 面积的 12–20%，但 strip 上几乎每一处至少有一只手够得到，所以必须左右手交替。上面的方法在 easier 和 hard 上都用两只手完成，名义版都通过，hard 在 ±1 cm 扰动下也达到 7/8。

**easier 的边距卡在 strip 西端。** 夹子在 strip 西端的中间（y≈0.245），第一段西半段只能在 y 0.235–0.25。它到南边 8 mm 边距线之间只剩约 7 cm，而 B2 弯松手后的自然大小也约 7 cm。所以 easier 在 ±1 cm 扰动下，“离边 ≥ 8 mm”这一项停在 4/8（16 个种子 6/16）。我们试了三轮改摆放，都没有超过这个数。

**放大区域的效果**（用已有扰动终态重新判定；区域只影响判定，不影响物理，所以可以这样算）。每格是“只看 goal / goal + 离边 ≥ 8 mm”：

| 改动 | easier（交付版） | hard（交付版） |
|---|---|---|
| 原 `_r2` | 8/8 / 4/8 | 8/8 / 7/8 |
| easier 南沿 +1 cm（到 curb 面）+ 北沿 +2 mm | 8/8 / 8/8 | — |
| easier 只把 x < -0.15 那一半南沿 +1 cm + 北沿 +2 mm | 8/8 / 8/8 | — |

**建议**
1. 更正交接包里的 curb 尺寸（见开头）。
2. easier / easier_loose：可以把 strip 西半段（x < -0.15）的南沿往 curb 放 1 cm（到 y 0.145），北沿放 2 mm。这一改动让交付版在扰动下的“离边 ≥ 8 mm”从 4/8 变成 8/8。代价：西半段 curb 和区域之间不再留空，任务稍微变简单；摆放仍需三段、仍需翻 curb，不会变得太简单。另一种做法是保持区域，把夹子挪到 strip 西端的北侧或西边沿，给 B2 弯腾出位置（这一条没有仿真验证）。
3. hard：不需要改区域。
4. medium：方框几乎全在左臂一侧，右臂只覆盖约 26%，“东端右手、西端左手”交替不成立。若要用同一方法，方框需要往东移约 10–15 cm。这一条只做了可达性分析，没有仿真验证。

## 图和视频

（都在 `answer/figs/`；画图脚本是分支 `dev/pingyue-knot-place` 的 `knot_placement/tools/board_figs.py`）

- `easier_method.png`：easier 逐步图。每步画之前（灰）、之后（蓝）、两只手的箭头，以及按住的手。
- `hard_X1_steps.png`：hard 逐步图（第 2 版）。
- `start_compare.png`：两个起点的对比，说明 hard a 为什么要先搬进。
- 视频：`easier_full.mp4`、`hard_X1_full.mp4`，全程俯视。
