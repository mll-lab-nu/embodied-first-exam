# 按 seed 的场景随机变体（`variation_id="seeded"`）

日期：2026-09-29。计划与用户决定见 `~/.claude/plans/federated-leaping-eich.md`。

## 1. 一个具体例子

```python
import topogym
env = topogym.make("horseshoe_ring", variation_id="seeded", seed=7)
env.reset()                     # seed 7 → 7 % 3 = 1 → medium 档
env.episode_metadata["canonical_variation_id"]   # 'horseshoe_ring_medium'
env.episode_metadata["scene_variation"]
# {'version': 1, 'draws': {'center_xy_m': [...], 'yaw_deg': ..., 'target_ring_finish': 'coated_metal'}}
```

同一个 seed 每次都得到同一个档和同一套抽样值；换 seed 就换一套。显式写档名（`easy`、`medium`、`hard`、`base`）时场景和以前逐位相同，不做任何抽样。

## 2. 规则

- **选档**：`("easy","medium","hard")[seed % 3]`（`config/registry.py: seeded_variation`，即 `VariantRng.tier(3)`）。
- **抽样**：`topogym/tasks/scene_variation.py` 的 `AXES` 表列出每个任务可随机的配置叶子。每条轴用 `VariantRng(seed).stream(名字)` 取数，名字是 `<task_id>/<叶子路径>`，外观类加 `visual/` 前缀；增删一条轴不影响其他轴的抽样值。
  - `offset`：在该档自己的默认值上加 U[lo, hi]（逐分量）。
  - `choice`：等概率选一个。
- **只抽位置、朝向、颜色、材质**，不改尺寸和几何：谜题的拓扑、间隙、解法路径不变，只是整体刚体搬移或换外观。
- **调用方显式传的 `task_parameters` 优先于抽样值。**
- **接入点**：`Env.reset` 在构造 Task 之前把抽样值并入 `task_parameters`（`simulator/env.py`）；Task 本身只读自己的配置叶子，不知道 seed 模式。
- **目标区固定一侧**：放置类任务（horseshoe、hedgehog、keyhole、claws、orbits、slotted）的类属性 `goal_side` 固定为标称场景当前选中的一侧，挪动谜题不会把目标区换到桌子另一边（`tasks/placement.py`）。改动前后 18 个标称目标区逐位相同。
- **标称实例身份不变**：本轮新加的配置叶子列在各任务的 `hash_when_changed`，取默认值时不进入 `instance_id` 和 `scene_preset.json`；39 个标称档 × seed 0 的 `instance_id` 改动前后逐位相同，所以 Harbor i00 和 `solvability_proof/` 的审计不受影响。
- **Keyhole 资格**：标称实例仍走原来的严格比较；随机实例要求几何哈希一致、`AXES` 以外的参数等于默认、`AXES` 里的值落在范围内，目标区按同一规则在固定一侧重算（`tasks/cast_keyhole/qualification.py`）。

## 3. 每个任务的变量

Δ 是相对该档标称值的偏移（cm），yaw 单位是度。范围的来源：离线几何闸门（第 5 节）在全部包络顶点上都通过。

| 任务 | 变量 | 为什么不影响可解 |
|---|---|---|
| horseshoe_ring | 中心 Δx −3…+4、Δy −1…+3；yaw ±10；环表面 {copper, coated_metal} | 静置姿态相对中心/yaw 存储并随之变换；不用 silver 以免与蹄铁同色 |
| cast_coil | 中心 Δx ±3、Δy −3…0；yaw 90±10；金/银明度 ±10% | 两件一起动；+y 会让已在 y≈0.23 的银件远离双臂 |
| cast_keyhole | 中心 ±2；yaw ±5；金/银明度 ±10% | 参考策略 IK 容差 ±20 mm 以内 |
| hedgehog_in_cage | 中心 Δx −3…+1、Δy −2…+1；yaw ±5；木色系数 0.85–1 | Panda 基座在 x=−0.57，+x/+y 远离基座 |
| lock_picking | first_x −4…+1、center_y −1…+2；三个转盘颜色排列；底座 {coated_metal, engineering_plastic} | 判据与规划器都从 geometry 读位置；判据把世界 +x 写死为钥匙轴，所以不加 yaw |
| orbits | yaw 90±5；底座中心 Δx ±3、Δy ±2；绳色 {hemp, orange_rope, golden_rope} | 目标区固定 −y（原来两侧完全平局，+y 侧已有把手） |
| rope_threading | 平移 Δx −1…+2、Δy −1…0；yaw ±2；绳色三选一 | 标称场景已占 cam_high/cam_low 画面 95–96%，1.1 m 绳尾转 5° 会扫过约 5 cm，所以包络小；环色不动（指令按青→绿→紫指定顺序） |
| slotted_post_ring | 中心 Δx ±5、Δy −2…+5；绳色三选一 | FEM 体网格不能旋转，只平移 |
| knot_untying | 原点 Δx −6…+2、Δy ±4；yaw ±30；绳色三选一 | 判据是俯视无交叉，对平面刚体变换不变；yaw 烘焙进 FEM 体网格和 `rope_posed.obj` |
| buzz_wire_3d | 中心 Δx −1.5…0、Δy 0…+1.5；木色系数 0.8–1；导线 {copper, brass} | 判据相对夹具原点；−y 会让终点侧 IK 超容差 |
| fiber_bundling | 中心 Δx −2…0、Δy ±2；另有原本就按 seed 抽的丝形（扇角/弯曲/卷曲） | 送线时抓点距 Panda 基座约 0.8 m，不往 +x |
| interlocked_claws | 棕色目标件明度 ±15%；另一件颜色 {teal, 蓝, 绿, 灰} | 初态是双手预抓，位姿绑定关节角和焊接点，所以不动位置 |
| blanket_flatten | 布色（5 色）；花纹 {grid, stripes}；中心 Δx ±4、Δy 0…+3 | 覆盖率与位置无关；见第 4 节 |

颜色改动的实现：绳子直接换 `EntitySpec.surface` 的角色；烘焙在 URDF/GLB 里的颜色用 `assets/scene_visuals.py: scale_glb_color` 只改 glTF 的 JSON 材质块（贴图和网格字节不变），claws 同时改 URDF rgba、GLB 和 surface。

## 4. Blanket：抽样在冻结之前

Blanket 的初态是准备好的粒子存档，载入时核对身份（seed、配置、灯光相机、资产哈希）。seeded 实例先抽参数，再用准备脚本生成它自己的存档：

```bash
python scripts/prepare_blanket_initial_states.py --seeded --seed 3 --acceptance scene_layout --output <新目录>
python scripts/install_blanket_initial_state.py --candidate <新目录>
# 装到 topogym/assets/resources/variations/blanket_flatten/gathered_scene_v1/easy/seeded_v1/seed_3/
```

标称档存档仍在 `<tier>/seed_<N>/`，两者不冲突。没准备过的 seed，reset 会报错并给出上面的命令。每份存档约 20 MB，需要 GPU。

## 5. 验证工具

- `tests/unit/test_scene_variation.py`：seed→档、抽样可复现且在包络内、外观叶子只改外观、knot 平移旋转作用于 FEM 体网格、keyhole 标称资格不变。
- `tests/check_scene_variation.py`：离线几何闸门（CPU，不起 Genesis）。每档跑标称、全部包络顶点和 N 个映射到该档的 seed，检查桌边余量、目标区一侧、可达替代量（自由件顶点到最近臂基座的最大水平距离，比标称多出不超过 2 cm）、固定相机取景（标称已完整入画的相机 ≤0.98）、首抽拒绝率。用法：`PYTHONPATH=. python tests/check_scene_variation.py <task> --seeds 30 --jobs 4`。
- 本轮未做：变体下的机器人完整求解（oracle 延后）。buzz medium、lock、keyhole 的现有求解器里有世界坐标常数，换位置后会失效，这不等于场景不可解。
