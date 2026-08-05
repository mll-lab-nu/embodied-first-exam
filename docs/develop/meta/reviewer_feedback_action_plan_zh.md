# Dev-log：Reviewer 反馈 → 落地实现计划

> 日期：2026-07-09
> 来源：外部 reviewer 对录制视频的反馈。本文把反馈逐条对应到当前代码/配置，给出具体改动步骤。
> 其中"绳子端点建模"一项按用户要求咨询了 Fable，见第 4 节。

---

## 1. 反馈原文摘要

1. **Size-sorting 任务（= Swap，小方块放进小区域）**：机械臂现在表现不太好，交互"不够物理"，尤其是**抓取**环节。建议调 **grasp scale / ratio**，让机器人更真实地操作物体。
2. **Untangle 任务**：
  - 思路不错，但**绳子端点(tips)太小**，希望**略放大**，方便夹爪操作。
  - 当前**绳子端点看起来不太自然**，问 **Fable** 有没有更好的端点建模方式。
  - **绳子中段有些地方会打结/锯齿(kink/zigzag)**，希望能消除/平滑这些 artifact。
3. **整体**：环境不错，但应**增强 photorealism（真实感）和 physical realism（物理真实性）**。
4. 特别喜欢**最后一个环境**（录制顺序里的最后一个 = cable_routing）。（正向反馈，无需 action）

---

## 2. 逐条对应当前代码 + 具体实现步骤



### 2.1 Swap 抓取更物理（grasp scale/ratio）

**现状（**`configs/task_configs/swap_topogym_tabletop_v1.yaml` **+** `prototypes/swap_physical_grasp_demo.py`**）**

- block 是 **3.8cm 立方体**（`blocks.*.size = [0.038,0.038,0.038]`）。
- Panda 夹爪 `open_qpos=0.04 / closed_qpos=0.00`（每指 0~4cm）。
- demo 的 `--grasp-qpos` 默认 = **"fully closed target" = 0.00**（见 demo 里 help）。
- ⇒ 抓取时手指被命令**闭到 0**，而 block 半宽是 0.019m，等于**手指往刚体里怼 1.9cm/边**、靠力限+摩擦硬夹住 → 这就是"不物理"的来源。

**改动步骤**

1. 把抓取目标 qpos 改成**贴合 block 半宽**：block 半宽 0.019 → `grasp_qpos ≈ 0.016~0.017`（留 2~3mm 轻压），而不是 0。
  - 最好**从 block 尺寸算**：`grasp_qpos = half_width - squeeze`（squeeze≈0.002~0.003），这样换 block 尺寸自动适配。
  - 落点：swap config `physical:` 下新增 `grasp_qpos`，demo 读它做默认（现在 demo 默认吃 primitive 的全闭）。
2. （可选）减小抓取冲击：夹爪 `kp`（现在 100）/ `force`（±100）偏大，或在闭合末段加缓冲步，减少"啪"一下贴上去。
3. 验证：viewer 里手指停在 block 侧面、不穿模；lift/搬运稳；`max_grasp_xy_error`、`min_lift_delta` 仍满足。



### 2.2 Untangle 绳子端点(tip) 放大

**现状（**`untangle_topogym_tabletop_v1.yaml`**）**

- `physical_handle.radius = 0.0085`（直径 17mm）、`height=0.024`——这是机械臂**实际夹住的刚体小圆柱**，绳端 PBD 粒子用 `fix_particles_to_link` 跟随它。
- config 注释本身就写了："handle 太小会产生很硬的接触力，容易让 PBD rope + rigid handle 的 native solver 崩溃"。

**改动步骤（按 Fable 意见修正：重点是"长度+形状+颜色+耦合带"，不是单纯放大直径）**

1. **加长** `physical_handle.height` 0.024 → **~0.035**（这才是 graspability 的主因——给夹爪一个像样的落脚区，24mm 拖拽时会打滑）。
2. 直径基本够用（当前 17mm 在 Fable 的"好抓"区间 13~20mm），`radius` 可保持 ~0.0085 或微增到 ~0.010，**不要超 0.010**（直径 20mm）。
3. `physical_handle` 抓取 `grasp_qpos` 跟着 handle 半径匹配（半径 r → 每指闭到 ~r-0.001 贴住）。
4. 验证：夹爪落脚更稳、solver 更稳（和 2.3 的形状改造一起做）。



### 2.3 Untangle 端点建模更自然（Fable 定案：aglet 圆头端头，详见第 4 节）

现状是"刚体圆柱怼在绳端"，视觉突兀且平头易打滑。**Fable 定案 = aglet（鞋带头）式端头**，落到代码上：

1. **形状**：把端头从平头圆柱改成**圆柱 + 半球头（capsule 感）**，free end 磨圆。Genesis 里可用 capsule morph，或圆柱上叠一个半球。
2. **与绳重叠**：端头往绳侧**多伸 ~10mm 盖住绳管末端**，视觉上绳"插进"端头，不再像外挂圆饼。
3. **颜色匹配**：端头颜色改成**跟该 strand 的绳色一致（或略深）**，而不是现在统一的深色 `[0.02,0.06,0.10]`——按 `rope.strands.*.color` 给每根绳的 handle 上色。
4. **固定粒子带**：`fix_particles_to_link` 改成固定**末端 2~~3 圈粒子（跨 ~8~~12mm）**而不是单圈，分散耦合、消掉接缝硬 hinge（顺带缓解第一段打折）。落点在 `topogym/tasks/entangle/untangle.py` 建 handle + `fix_particles_to_link` 的地方。
5. （可选）绳侧加 1mm 小凸缘 collar，像热缩套 + 防轴向滑脱。



### 2.4 Untangle 绳子中段 kink/zigzag

**现状**

- mesh：`segment_length=0.009` + `radial_segments=8`（偏粗 → 管子有明显 facet/棱）。
- 弹性：`bending_compliance=0.0030`（偏软）+ `max_bending_solver_iterations=6`。

**改动步骤（按 Fable 的影响力排序，每次只动一个量）**

1. **先加 solver 迭代**（kink 主因 = 约束没收敛）：`max_bending_solver_iterations` 6→**12+**、`max_stretch_solver_iterations` 10→更高。
  - ⚠️ Fable 首选是加 **substeps**，但我们 `sim.substeps` 被 locked preset 锁死为 4（见第 4 节警告）；所以 untangle 先靠**加迭代**，不够再考虑给该 task 开 preset 例外提 substep。
2. **particle_size 相对 radius 偏大 → buckling**：现在 `particle_size=0.004 = radius 0.004`，Fable 建议 particle_size ≈ 0.5~0.7× radius（→ ~0.0025）**或**把管加粗；并确认 **self-collision 距离 ≥ 粒子直径**，防止绳自折锁死。
3. **视觉锯齿（管子粗糙）**：`radial_segments` 8→**12**、`segment_length` 0.009→**0.006**（管更圆；注意别过细致 PBD 不稳，参考 cable_routing 体积失稳教训）。
4. **bending 刚度**：`bending_compliance` 0.0030→**~0.0015**（更挺），必要时加**阻尼** 0.01~0.1。
5. **限拖拽速度**：EE 每 substep 移动别超 ~1 个粒子间距（handle drag primitive 里限速）。
6. **rest-state**：绳按 rest 长 spawn、开局先 settle 几百步。

- **权衡**：绳太挺会难缠绕/解结（untangle 本身要能打结）。**循序微调**，一次一个量，GPU viewer 看，别一次全改。



### 2.5 Photorealism / Physical realism（整体，独立 workstream）

**现状**：几乎所有实体都是 `gs.surfaces.Plastic(color=...)` + 平色，`rasterizer` 渲染器。

**改动方向（先易后难）**

1. **材质分层**：给不同物体用更贴合的材质/参数——木纹桌面、金属感边框(我们已加的 table frame)、绳子/贴片用偏布/橡胶的 roughness，pole/连接件金属感。Genesis `gs.surfaces` 支持贴图/roughness/metallic。
2. **纹理贴图**：桌面木纹、substrate 表面纹理等（贴图文件放 assets，surface 用 texture）。
3. **渲染/光照**：评估从 `rasterizer` 换到 `batch`/光追渲染器 + 更好的光照/阴影，专用于**录制**（policy observation 仍可用轻量 raster）。
4. **物理真实性**：接续 2.1/2.4——抓取、接触、绳子动力学的参数打磨。

这是一条**跨所有 task 的横向线**，建议单独立项推进（先做录制用的高质量渲染 preset，不影响训练用的轻量 preset）。

---



## 3. 优先级 / 建议顺序

1. **Swap 抓取**（2.1）——影响最直接、改动小、单 config/demo。**先做**。
2. **Untangle 端点放大 + 建模**（2.2 + 2.3，等 Fable）——一起改，config 为主。
3. **Untangle 绳子 kink 平滑**（2.4）——需 GPU viewer 循序调参。
4. **Photorealism**（2.5）——横向线，另立项；先做一个"录制高质量渲染 preset"。

每项都遵循：**一次只动一个量 → GPU viewer/录制看 → 再动下一个**（cable_routing 那轮的教训：盲改多参数很难定位）。

---



## 4. Fable 咨询：绳子端点建模（已返回）

**总原则**：`fix_particles_to_link` 这套刚体耦合是当前设计里**稳定**的部分，别丢——问题纯粹是视觉/几何，把刚体核**藏起来**即可（把"碰撞+抓取几何"和"视觉几何"分开想）。

**Fable 推荐方案 = "aglet"（鞋带头/热缩套）圆头刚体端头**：

- 与绳同轴的刚体 **capsule / 圆柱+半球头**，半径 ~~6.5mm（约 1.5~~1.75× 绳半径），**长度 ~35mm**，与绳端**重叠约 10mm**（让绳管视觉上"插进"端头），free end 磨圆。
- **颜色/粗糙度匹配绳子**（或略深，像真实 aglet/热缩管）。
- 端头尾部**固定一"带"粒子（2~~3 圈、跨 ~8~~12mm），而不是单圈**——分散耦合、避免绳-handle 接缝处形成硬 hinge（这正是"端头乱甩 / 第一段打折"的常见根源）。
- 质量 ~~2~~5g（太重会甩绳、太轻刚体接触会抖）。
- 直径：13mm 在 80mm 行程的 Panda 上很好抓；**别超 ~20mm**（否则像个工具而不是绳头）。
- 可选：绳侧端加个 1mm 小凸缘(collar)，视觉像热缩套 + 机械上防止从夹爪里轴向滑脱。

**关键纠正我之前的判断**：graspability 主要靠**长度(夹爪落脚区)**，不是直径——当前 24mm "勉强"、拖拽时爪子会打滑，~35mm 宽容得多；当前直径 17mm 其实已在"好抓"区间。所以端点该改的是**长度 + 圆头形状 + 颜色匹配 + 与绳重叠 + 固定粒子带**，而不是单纯放大直径。

**不推荐**：纯锥形做唯一抓取面（爪子一夹会沿轴挤出去）；球/珠头（平爪下会滚、要 ≥12~15mm 才夹得住、在 4mm 绳上显得臃肿）；软 visual sleeve（渲染几何和碰撞几何不一致，爪子穿模）；直接夹 PBD 粒子（不稳）。

### Fable 关于减 kink（按影响力排序，已并入 2.4）

1. **先加 solver 迭代/substeps**（kink = 约束没收敛）。XPBD 里"多 substep + 少 iter"优于"少 substep + 多 iter"——优先 substep。
2. **particle_size 相对 radius 偏大会 buckling**：particle_size ≈ 0.5~0.7× radius，或把管加粗；并保证 **self-collision 距离 ≥ 粒子直径**，防止绳自己折进去锁死。
3. bending 刚度加大 / compliance 降低（stretch 接近最大=不可伸长，bending 适中；若有 volume/shape-matching 刚度也加）。
4. 加**阻尼** 0.01~0.1（压住快拖时的振荡），别过阻尼。
5. **限 EE 拖拽速度** < 每帧几个粒子直径（kink 常在 handle 每 substep 移动 > 1 个粒子间距时出现）。
6. **rest-state 卫生**：绳子按 rest 长度 spawn、开局前先 settle 几百步，避免 spawn 应力烙下永久 zigzag。

> ⚠️ 实现约束：我们的 `sim.substeps` 被 tabletop V1 locked preset 锁死为 4（`StandardTabletopSceneBuilder._validate_locked_preset`）。所以"加 substep"这条对 untangle 不能直接全局改——只能走**加 PBD solver 迭代**、或给该 task 开 preset 例外。落地时注意。


命令：

python -m prototypes.common_task_demo --task untangle --viewer --keep-open --backend gpu

