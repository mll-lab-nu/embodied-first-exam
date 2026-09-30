**一句话**：sort-blocks 难在任务本身的几何：四块方块贴在一起（相邻中心只隔 2.3–4.4 cm），夹一块会碰走或夹走邻块；四个箱子是散放的，手臂或手里的方块一碰就推开、撞倒；一个底座站位够不全方块和四个箱子，四趟抓放还要挤进 1000 步。limited 用 13 次 reset 反复重跑 `gen.py`，定下扫描位、箱子像素和夹住后开底座端运的放法，被评分的 ep13 前 394 步回放脚本放进红、黄两块，蓝、绿空夹后抬高重看、现场补夹，第 813 步 `success`；full 读真值、逐块选夹爪角度、分两个站位高处松手，42.6 min 交的 1000 步轨迹在第 1000 步才判成功。

## GPT-6 Luna
### limited
- **ep1 手动走一遍，ep2–ep12 反复重跑脚本**：ep1 抬臂后 4.97 min "The elevated wrist view now shows all four cubes and bins"，手动逐块 IK，907 步里蓝块被放进了绿箱，回放末帧绿箱歪倒。22.24 min 写成 `gen.py`，之后每局 reset 重跑、看停在哪一步、改一处：分割改按通道比值、连杆只取 z 间距、蓝块对齐修正、绿块从 +y 下探、先黄后蓝绿的顺序；每次 reset 回到同一开局，ep3 起开局估出的方块坐标都一样。
- **按键名读了 `end_effector`，仍有厘米级偏差**：`gen.py` 的 `EE_ZERO` 读 `SPEC["arm"]["end_effector"]["position_m"]`，`CAM_OFFSET = CAM_POS_ZERO - EE_ZERO`，合爪前按 FK 挪底座把 `end_effector` 对到方块上；但连杆只取 z 间距，`end_effector` 的 y −0.0249 一起丢了。脚本里蓝块 5 局空夹（ep3、ep8、ep9、ep10、ep13），它在注释里写 "The arm encoder FK has a centimeter-scale bias near the table"。
- **放法到 ep12 后才换成底座端运**：ep12 四块都夹起，但臂 IK 放黄块用了 212 步，绿块端去途中到第 1000 步；36.40 min 改成夹住后开底座把方块平移到箱子上方再松手，ep13 里红、黄各在夹起后 15 步放下。
- **被评分的 ep13 后半靠现场重看**：`gen.py` 第 394 步蓝块空夹（0.996）抛错退出；它抬高 0.16 m 看腕部图（38.07 min "The blue cube is about 3 cm ahead of the end effector"），第 453 步夹住、第 625 步在蓝箱上方松手；绿块第 715 步空夹，再抬高重看后第 789 步夹住，第 813 步 `success`，末帧四个箱子都直立在原位。39.71 min 才把这套重定位写进 `gen.py`（`pick_with_retry`），没整局跑过。
### full
- **真值和 pinch site**：读方块、箱子坐标和 `_check_goals` 的目标区域，在 `robot_pinch_site` 上做 IK；10.35 min 红块第一次进箱。
- **其余三块用了约 29 min，都花在簇和箱子上**：绿块 45° 夹不起，改 90°、侧移底座、下探后先停 8 步再合爪才提起（27.01 min）；"a direct return from the red bin to the next cube was blocked by the bin"，加高点路过；"Farther forward base positions reached the pile but not the bins"，改成两个站位；蓝、黄一对从同一前缀扫夹爪角度，"a straight jaw angle isolates yellow, while a diagonal angle isolates blue"。
- **1000 步刚好**：35.59 min 那条到第 1000 步蓝块还在桌上；删停顿后 38.34 min 第 997 步四块到齐；最终 `gen.py` 两次回放都在第 1000 步成功，回放里四个箱子全程没动。
### 两种模式
- **难点相同，都在贴在一起的方块**：full 从同一前缀扫夹爪角度，逐块选；limited 脚本里蓝块 5 局空夹，最后靠空夹后抬高重看。
- **都靠底座解决够不到箱子**：full 分两个站位、从箱底上方 0.15 m 松手，四趟用满 1000 步；limited 夹住后开底座把方块端到箱子上方，两次空夹后仍在第 813 步完成。

## 对照实验
- **不 reset 的那一局没过**：底座只在前 31 步动过，之后全靠手臂够；黄块第 8 次合爪（第 362 步）才夹住，往黄箱里放时末端点卡在 z 约 0.51，又花了 429 步；松手后手指卡在黄箱里，抬臂把黄箱提起、撞歪红箱；红块端到红箱口时第 1000 步用完，`failed`。第一种放法卡住后，一局里没有留下换放法的步数。

## 和旧版比
- **旧版（50 次 reset，没有抓取点）没过**：以腕部相机为工具点、偏移靠试，上下文压缩后丢了偏移，一局最多一块进对箱子；这一版用 `end_effector`，红块从 ep3 起都夹住了，但蓝块在脚本里仍空夹 5 局，它的通过主要靠 11 局调脚本和底座端运。
