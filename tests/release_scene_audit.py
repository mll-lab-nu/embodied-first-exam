"""Release-grade passive-hold audit for any registered variation, every physics tick.

Coarse by design: on 2026-09-29 the user ruled that small-amplitude motion and
particle-level jitter do not block release. Soft motion therefore uses p95
over vertices instead of the maximum. Samples cover committed physics ticks,
not native solver substeps, and are no continuous-collision certificate.
"""
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation


# Release gates. STRICT gives the stricter value used by earlier per-task audits,
# kept in every report so the relaxation is explicit.
LIMITS = dict(rigid_penetration_m=.001, attachment_residual_m=.001, minimum_volume_ratio=.2,
              table_penetration_m=.0001, fall_below_table_m=.005,
              rigid_window_drift_m=.005, rigid_window_rotation_deg=3.,
              soft_window_drift_p95_m=.010,
              grasp_rotation_deg=10., grasp_translation_m=.005,
              grasp_window_rotation_deg=1.5, grasp_window_translation_m=.0015,
              entangled_gap_m=.010, lock_disc_deg=2.)
STRICT = dict(rigid_window_drift_m=.002, rigid_speed_m_s=.002, soft_max_speed_m_s=.005,
              soft_drift_m=.002, orbits_soft_speed_m_s=.001, grasp_rotation_deg=3., grasp_translation_m=.002,
              source="tests/slotted_scene_stability.py, tests/orbits_stability_evidence.py, "
                     "topogym/planning/rigid_reference/feedback.py")
SCENERY_PREFIXES = ("table_frame", "lab_")
SCENERY = {"ground", "table", "robot", "goal_region"}


def angle_deg(a, b):
    return float(np.degrees((Rotation.from_quat(np.roll(a, -1)).inv()*Rotation.from_quat(np.roll(b, -1))).magnitude()))


def pose(body):
    return np.asarray(body["position_m"], float), Rotation.from_quat(np.roll(np.asarray(body["quaternion_wxyz"], float), -1))


def ring_frame(local_vertices):
    """Centre, unit normal and inner radius of a torus from its local vertices."""
    v = np.asarray(local_vertices, float)
    center = v.mean(axis=0)
    normal = np.linalg.svd(v-center)[2][-1]
    planar = (v-center)-np.outer((v-center)@normal, normal)
    return center, normal, float(np.linalg.norm(planar, axis=1).min())


class TaskInvariants:
    """Discrete per-task state that a passive hold must not change (check G4)."""

    def __init__(self, env, initial):
        self.env, self.task = env, env._task
        self.task_id = env.config.task_id
        world = initial["world"]
        self.description = "none; this task only runs G1-G3"
        self.ring_names = self.volume = None
        if self.task_id in {"knot_untying", "rope_threading", "slotted_post_ring", "orbits"}:
            name = next(iter(world["fem"]))
            self.volume = self._surface_rings(name, len(world["fem"][name]["position_m"]))
            self.fem_name = name
        if self.task_id == "orbits":
            from orbits_stability_evidence import measure
            rings = self.volume
            with np.load(self._volume_path) as volume:
                centers = volume["spawn"][rings].mean(axis=1)
            self._orbits = lambda w: measure(w, layout=self.task.layout, origin=self.task.origin,
                yaw_deg=self.task.config["yaw_deg"], surface_rings=rings,
                initial_lengths=np.linalg.norm(np.diff(centers, axis=0), axis=1),
                handle_vertices=self.task.placement_vertices["handle"],
                fixed_positions={n: world["bodies"][n]["position_m"].copy() for n in self.task.placement_remainder
                                 if n in world["bodies"]})
        if self.task_id == "slotted_post_ring":
            self.ring = ring_frame(self.task.placement_vertices["target_ring"])
            post = np.asarray(self.task.placement_vertices["post"], float)
            self.post_local = post
        if self.task_id in {"horseshoe_ring", "hedgehog_in_cage", "interlocked_claws"}:
            vertices = self.task.placement_vertices
            self.target = self.task.placement_targets[0]
            self.anchor = [n for n in self.task.placement_remainder if n in world["bodies"]]
            rng = np.random.default_rng(0)
            def thin(v, n=4000):
                v = np.asarray(v, float)
                return v if len(v) <= n else v[rng.choice(len(v), n, replace=False)]
            self.local = {n: thin(vertices[n]) for n in (self.target, *self.anchor)}
            if self.task_id == "horseshoe_ring":
                self.ring = ring_frame(vertices[self.target])
            if self.task_id == "hedgehog_in_cage":
                cage = np.asarray(vertices[self.anchor[0]] if len(self.anchor) == 1 else
                                  vertices[next(n for n in self.anchor if "cage" in n)], float)
                self.cage_name = self.anchor[0] if len(self.anchor) == 1 else next(n for n in self.anchor if "cage" in n)
                self.cage_box = cage.min(axis=0), cage.max(axis=0)

    def _surface_rings(self, name, count):
        episode = self.env.episode_metadata["episode_id"]
        for path in sorted(Path(self.env.config.work_dir).rglob("*volume*.npz")):
            if episode not in str(path):
                continue
            with np.load(path) as volume:
                if "surface_ring_indices" in volume and len(volume["spawn"]) == count:
                    self._volume_path = path
                    return volume["surface_ring_indices"].copy()
        raise FileNotFoundError(f"No FEM volume with surface rings for {name}")

    def centerline(self, world):
        return np.asarray(world["fem"][self.fem_name]["position_m"])[self.volume].mean(axis=1)

    def values(self, record):
        world, metrics = record["world"], record["task"]["result"]["metrics"]
        t = self.task_id
        if t == "knot_untying":
            from topogym.assets.geometry.knot_untying import projected_crossings
            hits = sorted(projected_crossings(self.centerline(world)), key=lambda h: h["segments"][0])
            self.description = "projected crossings of the rope centreline: count, then over/under flag and sign in material order"
            return dict(crossings=len(hits), pattern=[(h["first_over"], h["sign"]) for h in hits],
                        planar_clear=bool(metrics.get("planar_clear")))
        if t == "rope_threading":
            self.description = "ordered ring-crossing sequence of the rope (Task metric crossing_sequence)"
            return dict(crossing_sequence=json.loads(json.dumps(metrics.get("crossing_sequence"), default=list)))
        if t == "orbits":
            m = self._orbits(world)
            self.description = "absolute post winding numbers; last post still encircled; cord below the lowest ring"
            return dict(winding=m["winding_absolute"], last_post_encircled=m["last_post_still_encircled"],
                        cord_below_lowest_ring=m["cord_below_lowest_ring"])
        if t == "slotted_post_ring":
            from topogym.utils.geometry.passage import aperture_crossings
            p, r = pose(world["bodies"]["target_ring"])
            center, normal, inner = self.ring
            c, n = p+r.apply(center), r.apply(normal)
            pp, pr = pose(world["bodies"]["post"])
            post = pr.apply(self.post_local)+pp
            axis_xy = post[:, :2].mean(axis=0)
            axis = np.array([[*axis_xy, post[:, 2].min()], [*axis_xy, post[:, 2].max()]])
            cord, _ = aperture_crossings(self.centerline(world), c, n, inner)
            posts, _ = aperture_crossings(axis, c, n, inner)
            self.description = "times the cord centreline and the post axis pass through the ring aperture"
            return dict(cord_through_ring=len(cord), post_through_ring=len(posts))
        if t in {"horseshoe_ring", "hedgehog_in_cage", "interlocked_claws"}:
            from scipy.spatial import cKDTree
            def world_points(name):
                p, r = pose(world["bodies"][name])
                return r.apply(self.local[name])+p
            if t == "horseshoe_ring":
                p, r = pose(world["bodies"][self.target])
                center, _, inner = self.ring
                others = np.concatenate([world_points(n) for n in self.anchor])
                distance = float(np.linalg.norm(others-(p+r.apply(center)), axis=1).min())
                self.description = (f"distance from the {self.target} centre to the nearest point of the other parts "
                                    f"stays <= the ring inner radius {inner*1000:.1f} mm (some part still passes through the ring hole)")
                return dict(linked=distance <= inner, nearest_part_to_ring_centre_m=distance)
            if t == "hedgehog_in_cage":
                bp = pose(world["bodies"][self.target])[0]
                cp, cr = pose(world["bodies"][self.cage_name])
                local = cr.inv().apply(bp-cp)
                low, high = self.cage_box
                self.description = f"{self.target} centre, in the {self.cage_name} frame, stays inside the cage's bounding box"
                return dict(inside=bool(((local >= low) & (local <= high)).all()), ball_centre_in_cage_frame_m=local.tolist())
            gap = float(cKDTree(world_points(self.anchor[0])).query(world_points(self.target))[0].min())
            if not hasattr(self, "initial_gap"):
                self.initial_gap = gap
            self.description = (f"nearest mesh-vertex distance between {self.target} and {self.anchor[0]} stays "
                                f"<= its t=0 value + {LIMITS['entangled_gap_m']*1000:g} mm (pieces not pulled apart; "
                                f"vertex-based, long primitive rods have vertices only at their ends)")
            return dict(entangled=gap <= self.initial_gap+LIMITS["entangled_gap_m"], nearest_gap_m=gap)
        if t == "lock_picking":
            self.description = f"disc angles (<= {LIMITS['lock_disc_deg']:g} deg change) and leading tab not inserted"
            return dict(disc_angles_deg=list(metrics.get("disc_angles_deg", [])),
                        leading_tab_inserted=bool(metrics.get("leading_tab_inserted")))
        if t == "fiber_bundling":
            self.description = "per-strand completed passage flags (Task metric strands_complete)"
            return dict(strands_complete=json.loads(json.dumps(metrics.get("strands_complete"), default=list)))
        return {}

    def unchanged(self, first, now):
        if self.task_id in {"horseshoe_ring", "hedgehog_in_cage", "interlocked_claws"}:
            key = {"horseshoe_ring": "linked", "hedgehog_in_cage": "inside", "interlocked_claws": "entangled"}[self.task_id]
            return bool(now[key] and first[key]), {k: v for k, v in now.items() if k != key}
        if self.task_id == "lock_picking":
            change = max((abs((a-b+180) % 360-180) for a, b in zip(now["disc_angles_deg"], first["disc_angles_deg"])), default=0.)
            return (change <= LIMITS["lock_disc_deg"] and now["leading_tab_inserted"] == first["leading_tab_inserted"]
                    and len(now["disc_angles_deg"]) == len(first["disc_angles_deg"])), dict(disc_change_deg=float(change))
        if self.task_id == "knot_untying":
            return (now["crossings"] == first["crossings"] and now["pattern"] == first["pattern"]
                    and now["planar_clear"] == first["planar_clear"]), {}
        return now == first, {}


class ReleaseSceneAudit:
    def __init__(self, env, folder, seconds, window_s=1.):
        self.env, self.folder = env, Path(folder)
        self.seconds, self.window_s = float(seconds), float(window_s)
        self.rows = (self.folder/"ticks.jsonl").open("x")
        self.samples, self.window_origin, self.first_values = [], None, None
        initial = env.tick_record()
        world = initial["world"]
        table = env._world.tabletop
        self.table_z = float(table.frames.table_surface_origin[2])
        self.table_xy = (np.asarray(table.robot_footprint.table_min_xy, float),
                         np.asarray(table.robot_footprint.table_max_xy, float))
        self.bodies = sorted(n for n in world["bodies"] if n not in SCENERY and not n.startswith(SCENERY_PREFIXES))
        self.soft = {**{n: "fem" for n in world["fem"]}, **{n: "particles" for n in world["particles"]}}
        self.initial_points = {n: np.asarray(world[k][n]["position_m"], float).copy() for n, k in self.soft.items()}
        self.initial_bodies = {n: pose(world["bodies"][n]) for n in self.bodies}
        self.invariants = TaskInvariants(env, initial)
        self.grasps = self._pair_grasps(initial) if env.config.task_id == "interlocked_claws" else {}
        self.grasp_origin = None
        self.sample(initial)

    def _pair_grasps(self, record):
        """Each hand holds the piece whose surface is nearest its TCP (body origins are not grasp points)."""
        vertices = self.env._task.placement_vertices
        def distance(name, tcp):
            p, r = pose(record["world"]["bodies"][name])
            return float(np.linalg.norm(r.apply(vertices[name])+p-tcp, axis=1).min())
        pairs = {}
        for side, arm in record["robot"].items():
            tcp = np.asarray(arm["tcp_position_world_m"], float)
            pairs[side] = min((n for n in self.bodies if n in vertices), key=lambda n: distance(n, tcp))
        return pairs

    def _grasp(self, record):
        out = {}
        for side, body in self.grasps.items():
            arm = record["robot"][side]
            bp, br = pose(record["world"]["bodies"][body])
            tp = np.asarray(arm["tcp_position_world_m"], float)
            tr = Rotation.from_quat(np.roll(np.asarray(arm["tcp_orientation_wxyz"], float), -1))
            out[side] = (br.inv().apply(tp-bp), br.inv()*tr)   # T_object_tcp
        return out

    def sample(self, record):
        world, result = record["world"], record["task"]["result"]
        time = float(world["sim_time_s"])
        late = time >= self.seconds-self.window_s-1e-9
        points = {n: np.asarray(world[k][n]["position_m"], float) for n, k in self.soft.items()}
        speeds = {n: np.linalg.norm(np.asarray(world[k][n]["velocity_m_s"], float), axis=1) for n, k in self.soft.items()}
        bodies = {n: pose(world["bodies"][n]) for n in self.bodies}
        grasp = self._grasp(record)
        if late and self.window_origin is None:
            self.window_origin = dict(points={n: p.copy() for n, p in points.items()}, bodies=dict(bodies), grasp=dict(grasp))
        xyz = np.concatenate([*points.values(), *[p[None] for p, _ in bodies.values()]]) if (points or bodies) else np.zeros((0, 3))
        inside = bool(((xyz[:, :2] >= self.table_xy[0]) & (xyz[:, :2] <= self.table_xy[1])).all())
        soft_z = min((float(p[:, 2].min()) for p in points.values()), default=None)
        ipc = world.get("ipc") or {}
        residuals = list((ipc.get("attachment_residual_m") or {}).values())
        volumes = [v["minimum"] for v in (ipc.get("volume_ratio") or {}).values()]
        values = self.invariants.values(record)
        if self.first_values is None:
            self.first_values = values
        same, detail = self.invariants.unchanged(self.first_values, values)
        row = dict(time_s=time, physics_step=int(world["physics_step"]),
            task_success=bool(result["task_success"]), terminated=bool(result["terminated"]), reason=result.get("reason"),
            rigid_penetration_m=float(np.max(world["contacts"].get("penetration", []), initial=0.)) if world.get("contacts") else 0.,
            native_valid=ipc.get("native_valid", True), attachment_residual_m=max(residuals, default=0.),
            minimum_volume_ratio=min(volumes, default=None), all_on_table_xy=inside,
            soft_table_clearance_m=None if soft_z is None else soft_z-self.table_z,
            lowest_body_above_table_m=min((float(p[2])-min(self.table_z, float(self.initial_bodies[n][0][2]))
                                           for n, (p, _) in bodies.items()), default=None),
            soft_speed_p95_m_s=max((float(np.percentile(s, 95)) for s in speeds.values()), default=0.),
            soft_speed_max_m_s=max((float(s.max()) for s in speeds.values()), default=0.),
            soft_displacement_max_m=max((float(np.linalg.norm(p-self.initial_points[n], axis=1).max()) for n, p in points.items()), default=0.),
            soft_displacement_p95_m=max((float(np.percentile(np.linalg.norm(p-self.initial_points[n], axis=1), 95)) for n, p in points.items()), default=0.),
            rigid_displacement_max_m=max((float(np.linalg.norm(p-self.initial_bodies[n][0])) for n, (p, _) in bodies.items()), default=0.),
            invariants_unchanged=bool(same), invariant_detail=detail, window=late)
        if late:
            o = self.window_origin
            row.update(
                rigid_window_drift_m=max((float(np.linalg.norm(p-o["bodies"][n][0])) for n, (p, _) in bodies.items()), default=0.),
                rigid_window_rotation_deg=max((float(np.degrees((o["bodies"][n][1].inv()*r).magnitude())) for n, (_, r) in bodies.items()), default=0.),
                soft_window_drift_p95_m=max((float(np.percentile(np.linalg.norm(p-o["points"][n], axis=1), 95)) for n, p in points.items()), default=0.))
        if grasp:
            if self.grasp_origin is None:
                self.grasp_origin = grasp
            g = {side: (float(np.linalg.norm(t-self.grasp_origin[side][0])),
                        float(np.degrees((self.grasp_origin[side][1].inv()*r).magnitude()))) for side, (t, r) in grasp.items()}
            row.update(grasp_translation_m=max(v[0] for v in g.values()), grasp_rotation_deg=max(v[1] for v in g.values()))
            if late:
                w = self.window_origin["grasp"]
                row.update(grasp_window_translation_m=max(float(np.linalg.norm(t-w[s][0])) for s, (t, _) in grasp.items()),
                           grasp_window_rotation_deg=max(float(np.degrees((w[s][1].inv()*r).magnitude())) for s, (_, r) in grasp.items()))
        self.samples.append(row)
        self.rows.write(json.dumps(row, default=float)+"\n")
        self.rows.flush()

    def finish(self):
        self.rows.close()
        s, late = self.samples, [r for r in self.samples if r["window"]]
        def peak(key, rows=s, fn=max):
            values = [r[key] for r in rows if r.get(key) is not None]
            return fn(values) if values else None
        checks = []
        def check(code, name, meaning, method, value, limit, passed, source):
            checks.append(dict(code=code, name=name, meaning=meaning, method=method, measured=value,
                               threshold=limit, passed=bool(passed), threshold_source=source))
        duration_ok = bool(s and s[-1]["time_s"] >= self.seconds-1e-9 and late
                           and late[-1]["time_s"]-late[0]["time_s"] >= self.window_s-1e-6)
        check("G0", "运行完整", "静置按计划跑满，并覆盖完整末窗", "最后一个采样时刻与末窗长度",
              dict(last_time_s=s[-1]["time_s"] if s else None, window_ticks=len(late)), f"{self.seconds:g} s / 末窗 {self.window_s:g} s",
              duration_ok, "计划设定")
        first_bad = next((r for r in s if r["task_success"] or r["terminated"]), None)
        check("G1", "起始既未成功也未失败", "不施加任何动作时，Task 不应报成功，也不应因失败终止",
              "逐 tick 读取 Task 结果的 task_success / terminated / reason",
              None if first_bad is None else dict(time_s=first_bad["time_s"], success=first_bad["task_success"], reason=first_bad["reason"]),
              "全程 success=False 且 terminated=False", first_bad is None, "Task 判据语义")
        pen = peak("rigid_penetration_m")
        check("G2a", "刚体接触穿透", "刚体之间（含机器人、桌面）没有明显互相穿入", "逐 tick 取刚体接触最大穿透深度",
              pen, LIMITS["rigid_penetration_m"], pen is None or pen <= LIMITS["rigid_penetration_m"], "沿用现行 1 mm")
        if any(k == "fem" for k in self.soft.values()):
            vol, res = peak("minimum_volume_ratio", fn=min), peak("attachment_residual_m")
            valid = all(r["native_valid"] for r in s)
            check("G2b", "FEM 体网格与连接", "绳子的四面体没有翻转，IPC 求解有效，绳端连接没有脱开",
                  "逐 tick 取最小体积比、IPC native_valid、最大绳端连接残差",
                  dict(minimum_volume_ratio=vol, native_valid_all=valid, max_attachment_residual_m=res),
                  dict(minimum_volume_ratio=LIMITS["minimum_volume_ratio"], attachment_residual_m=LIMITS["attachment_residual_m"]),
                  valid and (vol is None or vol >= LIMITS["minimum_volume_ratio"]) and res <= LIMITS["attachment_residual_m"],
                  "体积比 0.2 沿用 Slotted（翻转底线）；Orbits 的 0.5–1.5 因 hard 出生即 1.52 不采用；残差沿用 Orbits 1 mm")
        clear = peak("soft_table_clearance_m", fn=min)
        low = peak("lowest_body_above_table_m", fn=min)
        on_xy = all(r["all_on_table_xy"] for r in s)
        check("G2c", "留在桌面上", "所有任务物体留在桌面范围内；软体不穿桌；刚体没有掉下桌",
              "逐 tick：软体顶点与刚体位置的 XY 在桌面内；软体最低点减桌面高度；刚体原点高度减 min(桌面高度, 该刚体出生高度)（固定底座原点可在桌面以下）",
              dict(all_on_table_xy=on_xy, min_soft_clearance_m=clear, min_body_origin_height_m=low),
              dict(soft_penetration_m=LIMITS["table_penetration_m"], body_below_table_m=LIMITS["fall_below_table_m"]),
              on_xy and (clear is None or clear >= -LIMITS["table_penetration_m"]) and (low is None or low >= -LIMITS["fall_below_table_m"]),
              "穿桌 0.1 mm 沿用 Slotted/Orbits；刚体掉桌 5 mm 为粗门槛")
        if self.bodies:
            d, a = peak("rigid_window_drift_m", late), peak("rigid_window_rotation_deg", late)
            check("G3a", "刚体末窗无明显运动", f"最后 {self.window_s:g} s 内每个任务刚体的位置和朝向基本不变",
                  "末窗起点为基准，逐 tick 取所有任务刚体的最大位移与最大转角",
                  dict(drift_m=d, rotation_deg=a), dict(drift_m=LIMITS["rigid_window_drift_m"], rotation_deg=LIMITS["rigid_window_rotation_deg"]),
                  d is not None and d <= LIMITS["rigid_window_drift_m"] and a <= LIMITS["rigid_window_rotation_deg"],
                  f"发布门槛；现行严格值 {STRICT['rigid_window_drift_m']*1000:g} mm")
        if self.soft:
            d, v = peak("soft_window_drift_p95_m", late), peak("soft_speed_p95_m_s", late)
            check("G3b", "软体末窗无明显运动", f"最后 {self.window_s:g} s 内绳/布整体基本停住；忽略少数粒子的抖动",
                  "末窗起点为基准，逐 tick 取顶点净位移的第 95 百分位，取末窗内最大值（逐 tick 速度的第 95 百分位只作参考，"
                  "不参与判定：PBD 粒子抖动会让它在静止的布上也维持约 8–13 mm/s）",
                  dict(drift_p95_m=d, speed_p95_m_s_reference=v, speed_max_m_s_reference=peak("soft_speed_max_m_s", late)),
                  dict(drift_p95_m=LIMITS["soft_window_drift_p95_m"]),
                  d is not None and d <= LIMITS["soft_window_drift_p95_m"],
                  f"用户 09-29 要求忽略粒子级噪声，故只看净位移；现行严格值：最大速度 {STRICT['soft_max_speed_m_s']*1000:g} mm/s（Slotted）、{STRICT['orbits_soft_speed_m_s']*1000:g} mm/s（Orbits），漂移 {STRICT['soft_drift_m']*1000:g} mm")
        changed = next((r for r in s if not r["invariants_unchanged"]), None)
        if self.first_values:
            check("G4", "拓扑不变", "静置过程中任务的穿套/打结/受困关系不因重力或回弹而改变",
                  self.invariants.description,
                  dict(initial=self.first_values_json(), first_change=None if changed is None else dict(
                      time_s=changed["time_s"], detail=changed["invariant_detail"])),
                  "与 t=0 一致", changed is None, "任务定义")
        if self.grasps:
            gt, gr = peak("grasp_translation_m"), peak("grasp_rotation_deg")
            wt, wr = peak("grasp_window_translation_m", late), peak("grasp_window_rotation_deg", late)
            check("G5", "持件稳定（Claws）", "双手初态夹住的件相对夹爪没有持续滑移或转动",
                  "每 tick 计算件坐标系下 TCP 的位姿（T_object_tcp，取实时值），与 t=0 比较；另取末窗内的增量",
                  dict(max_translation_m=gt, max_rotation_deg=gr, window_translation_m=wt, window_rotation_deg=wr,
                       pairs=self.grasps),
                  {k: LIMITS[k] for k in ("grasp_translation_m", "grasp_rotation_deg", "grasp_window_translation_m", "grasp_window_rotation_deg")},
                  gt is not None and gt <= LIMITS["grasp_translation_m"] and gr <= LIMITS["grasp_rotation_deg"]
                  and wt <= LIMITS["grasp_window_translation_m"] and wr <= LIMITS["grasp_window_rotation_deg"],
                  f"用户 09-29 要求放宽；原门槛 {STRICT['grasp_rotation_deg']:g}° / {STRICT['grasp_translation_m']*1000:g} mm（feedback.py）")
        early = [r for r in s if r["time_s"] <= .5+1e-9]
        profile = [dict(time_s=r["time_s"], soft_displacement_max_m=r["soft_displacement_max_m"],
                        soft_displacement_p95_m=r["soft_displacement_p95_m"], soft_speed_p95_m_s=r["soft_speed_p95_m_s"],
                        rigid_displacement_max_m=r["rigid_displacement_max_m"])
                   for r in s if abs(r["time_s"]*10-round(r["time_s"]*10)) < 1e-6]
        return dict(passed=all(c["passed"] for c in checks), checks=checks, limits=LIMITS, strict_reference=STRICT,
                    task_bodies=self.bodies, soft_bodies=self.soft, observed_ticks=len(s),
                    spawn_motion=dict(first_0_5_s_soft_displacement_max_m=max((r["soft_displacement_max_m"] for r in early), default=None),
                                      first_0_5_s_rigid_displacement_max_m=max((r["rigid_displacement_max_m"] for r in early), default=None)),
                    motion_profile_every_0_1_s=profile,
                    scope="passive hold from reset, zero actions, every committed physics tick; no RGB; "
                          "not solver-substep coverage, CCD, grasp/robot solution or difficulty qualification")

    def first_values_json(self):
        return json.loads(json.dumps(self.first_values, default=lambda x: np.asarray(x).tolist()))
