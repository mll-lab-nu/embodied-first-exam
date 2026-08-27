# rope_unwinding：从柱上解下 start_turns 圈绳 + 放置

任务书（`docs/develop/TopoGym_tasks.docx`）§2.5「从柱子上解下一圈绳（1 → 0）」的实现，
圈数扩展为 `winding.start_turns ∈ {1, 2, 3}`。2026-08-26 新建。

## 1. 任务定义

绳出生时已绕柱 `start_turns` 圈，锚定端由固定端子钉死，自由端的工业插头平躺在板面上，
由 spawn latch 钉住。夹爪抓插头（不抓绳身），从最上一圈的高度开始，沿与缠绕相反的方向
连续环绕 `start_turns` 圈、每圈下降 `climb_per_turn`，winding number 从 `±start_turns`
变为 0，然后把插头放到 C。

- **柱顶是改变 winding 的唯一 gateway。** oracle 全程在柱顶以下，判据 `below_post_top`
  与 rope_winding 相同；抬过柱顶把绳甩下来不算解绕。
- **方向敏感。** `winding.direction` 描述柱上已有缠绕的方向（`ccw` 出生读 +start_turns）；
  夹爪轨道方向由 planner 派生为反向。任务书的失败对照例「方向做错时 winding 变成 2 而不是 0」
  对应 `task.winding.orbit_direction=ccw`（在 ccw 缠绕上强制同向轨道）：读数
  `2·start_turns`，判失败。`task.winding.direction=cw` 是镜像布局（出生缠绕与轨道同时反向），
  仍应成功。

任务书 §2.5 没有成功判定段。这里沿用 rope_winding 的判据：
`|winding_number − 0| ≤ success.winding_tolerance` ∧ 缠绕段不高于柱顶 ∧ 插头落在 C 的
`connector_tolerance_xy` 内 ∧ 原语没中止。

## 2. 与 rope_winding 的关系

| 层 | 做法 |
| --- | --- |
| 场景装配、资产、材料 | 全部复用。`RopeUnwindingSceneBuilder` 是 `CableRoutingSceneBuilder` 的子类（`tasks/routing/rope_unwinding.py`），布局数值与 `rope_winding_topogym_tabletop_v1.yaml` 相同 |
| 出生路线 | 新增路线条目 `helix_around`（`planning/waypoint.py::helix_route_points`，`cable_routing.py::route_polyline` 解析）：从 S 沿切线接上柱，绕 `start_turns` 圈，再接尾弧 `arc_to` 到插头出生点 |
| oracle | 同一个 planner（`planning/rope_winding_planner.py`）。`WindingSpec` 新增 `start_turns`、`orbit_direction`，派生 `orbit_turns = |turns − start_turns|`、`turn_step`（每圈 +1 或 −1）、`orbit_sign`、`initial_winding`、`expected_winding`。`start_turns=0` 时行为与改前完全一致（`tests/check_rope_winding_geometry.py` 回归通过） |
| 判据 | `supervision/rope_winding.py` 不改；`target_winding = sign × turns = 0` |
| demo | `demos/routing/rope_unwinding_physical_handle_demo.py` 只有入口；主体 `rope_winding_physical_handle_demo.run_from_config` 按 spec 派生量工作（slack 检查、banner、任务描述） |
| 离线门 | `tests/check_rope_unwinding_geometry.py`，复用 rope_winding 门的 stand-in layout |

## 3. 出生螺旋的几何

- 螺旋半径 = 柱半径 + 绳半径 + 2 mm（`helix_around.standoff`），比落位半径多 2 mm，
  避免绳管出生在 IPC 的接触距离内。
- 从 S 到柱的切入点：`bearing(S) + sign·arccos(r/d)`，绳沿切线到达柱面后按缠绕方向继续。
- 最下一圈在 `wind_z_start`（0.045），每圈爬 `climb_per_turn`（0.014，圈间净空 6 mm），
  三圈最上一圈顶 0.091，柱顶 0.105。
- **尾弧必须沿最上一圈的切线离开柱子**，否则出生时绳在柱面上带一个折角。切线方向 −33°，
  顺时针（负 sweep）弯 130° 的尾弧，其弦相对切线偏约 −65°，因此插头出生点放在柱的 −y 方向
  0.216 m 处（`[-0.006, -0.218]`）；弧向 −x 侧鼓出，离柱轴始终 > 0.15 m。门里检查夹角 < 30°。
- 绳长由出生路线决定；松弛只来自尾弧的鼓出。最紧时刻在解绕**开始**（所有圈都在柱上），
  需求 = |S−柱| + start_turns × 2π × 落位半径 + |柱−插头|。出生螺旋每圈比落位周长多出约
  12 mm，抵消了大部分需求增量，所以 `spawn_arc.sweep_deg = −130` 一个值服务三档：
  松弛 8.5% / 8.9% / 9.2%（带 5~15%）。

## 4. oracle

航点与 rope_winding 同构：`lift_from_port` → `wind_entry`（在最上一圈的高度、轨道半径 0.140）
→ `wind_t{n}_{k}` × `start_turns × 8`（反向轨道、每圈下降 0.014）→ `wind_exit`（切向离开）
→ `to_C_hover` → `place_at_C`。搬运姿态、插头自转（`plug_spin_tracks_orbit`，按手的实际方位角
计算，方向自适应）、`before_release` 交接全部沿用。

出生时绳从最上一圈离开的方位比绷紧后的切点靠前约 50°，第一次抬起并拉入轨道时缠绕先少掉
约 0.14 圈；这使最后一圈能完整脱离柱面，`taut_demand` 因此偏保守约 2 cm。

## 5. 已知风险（待 GPU 实跑确认）

1. **多出的绳段没有去处。** `rest_shape=spawn` 使出生螺旋成为无应力构型，绳不会自己弹离柱子；
   代价是解开之后绳保留螺旋记忆，每圈约 0.151 m 的绳松散躺在板上，可能缠上柱底座或进入夹爪
   路径。`rest_shape=straight` 会让预绕的绳储存弯曲能、在静置时就试图弹离柱子，本轮不采用。
2. 柱面摩擦下，反向轨道拉动时圈是否逐圈脱离、还是整体上滑越过柱顶（`wound_max_z` 会记录）。
3. 解绕过程中插头出线口相对下方各圈的高度（`blocking_gap`，只报不判）。

## 6. 运行

2026-08-26 首跑（start_turns=1，GPU，无 viewer）：`success=True`，`winding_number=0.000`
（`swept_turns=+0.156`，`turn_complete` 时已读 0），`placement_error_xy=0.0034`，13/13 航点，
`wound_max_z=0.005`（解下来的绳躺在柱脚旁的板面上，没有越顶）。`post_contact` 沿轨道单调下降
（2079 → 1009 → 479），即圈是逐渐剥离而不是整体上滑。`twist_net` 累计 −1.1 圈，
`pad_gap` 最小 1.4 mm（绳末段贴在指垫上）——与 rope_winding 的同类读数相当，待 A/B
`plug_spin_tracks_orbit`。


```bash
python tests/check_rope_unwinding_geometry.py                     # 离线门，默认 start_turns=1
python tests/check_rope_unwinding_geometry.py --start-turns 3
python -m demos.routing.rope_unwinding_physical_handle_demo run.probe=true | tee runs/rope_unwinding_x1.log
python -m demos.routing.rope_unwinding_physical_handle_demo task.winding.start_turns=2 | tee runs/rope_unwinding_x2.log
python -m demos.routing.rope_unwinding_physical_handle_demo task.winding.orbit_direction=ccw | tee runs/rope_unwinding_wrong_way.log
```

实跑观察项：出生静置后 `winding_number` 读 ±start_turns、`post_contact` 稳定；每个
`turn_complete` 读数减 1；终态 winding 0、`placement_error_xy` 在容差内；多余绳段的去向。
