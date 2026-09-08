"""Offline gate for the cloth_unroll judges (docx 1.3).

Runs the REAL evaluator against the REAL task config on synthetic cloth, so a
threshold edit that stops separating a real unroll from the wrong ones is caught
without a GPU run.

What it proves:
  - a band paid out flat passes both gates;
  - the roll as built fails, which is the floor the task starts from;
  - **the roll torn whole off the bar fails**, and `on_bar` is what tells it from
    a roll that simply never turned. That failure is this scene's own -- 1.2 had
    no fixture to be torn off -- and it is the reason `on_bar` is recorded at all;
  - **an over-pulled band fails the third gate** (`over_pull`, 2026-09-06): its
    free end has been towed past where a flat band ends, while the two material
    gates pass all the better -- which is why a position gate is needed at all;
  - the spiral's own arithmetic closes: the material the roll stores is exactly
    the difference between its length and its plan span, and the wound part is
    exactly what the pull has to pay out;
  - the layer spacing and the bar clearance are both at least a particle, which is
    what keeps PBD from opening the episode by resolving a collision (1.2's
    measured lesson, cloth against cloth; here it is also cloth against a rigid);
  - the shipped config pulls in ONE continuous stroke, and cutting the travel into
    more strokes leaves the hand's endpoint unchanged -- the arithmetic that says
    splitting never bought reach, which is why the split was removed;
  - the hand finishes where a band running straight from the glued tail on the
    spool reaches the table with `pull_slack` to spare, and that position
    depends on the dispenser, the material length and the grasp inset ALONE --
    the roll's pitch and turn count cancel. Which is the whole list of levers
    when the finish is out of reach;
  - the stroke stays in the plane, and the `shove` and `overpull` motions really
    are the motions their names claim.

    python tests/check_cloth_unroll_geometry.py

Needs numpy + PyYAML only (no hydra, no genesis): the evaluator is plain NumPy
over particle arrays, which is the point of keeping it independent of the scene.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
TASK_CFG = REPO / "configs/task_configs/cloth_unroll_topogym_tabletop_v1.yaml"

#: How far along y the arm has been MEASURED delivering a pull. Not a limit the
#: robot config states -- an observation, and the only reach number on this
#: tabletop that has been measured rather than assumed.
#:
#: 0.152 until 2026-08-24, which was simply where `cloth_unpleat` stopped rather
#: than where the arm ran out. `cloth_unroll` then commanded +0.181 and the hand
#: delivered +0.175 (y gap 6.0 mm), with the gap growing smoothly from 3.4 mm at
#: the start of the pull -- no sign of a wall. Recorded at the commanded value,
#: since that is what the planner is checked against.
MEASURED_REACH_Y = 0.181


# Stand-in packages, so a module can be loaded by path and still resolve the
# `topogym.*` imports it makes in production. Same device and same reason as in
# `check_cloth_unpleat_geometry.py`: the packages' own `__init__` files pull in
# Genesis by way of the task modules, and this check must run without a GPU.
for _package in ("topogym", "topogym.verification", "topogym.tasks", "topogym.tasks.deformation"):
    if _package not in sys.modules:
        _stub = types.ModuleType(_package)
        _stub.__path__ = [str(REPO / _package.replace(".", "/"))]
        sys.modules[_package] = _stub


def _load(name: str, relative: str):
    """Load a module by path, registered under its real dotted name."""

    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_load(
    "topogym.verification.cloth_fold_verifier",
    "topogym/verification/cloth_fold_verifier.py",
)
_load(
    "topogym.verification.cloth_unpleat_verifier",
    "topogym/verification/cloth_unpleat_verifier.py",
)
_verifier = _load(
    "topogym.verification.cloth_unroll_verifier",
    "topogym/verification/cloth_unroll_verifier.py",
)
_mesh = _load(
    "topogym.tasks.deformation.cloth_profile_mesh",
    "topogym/tasks/deformation/cloth_profile_mesh.py",
)

ClothUnrollEvaluator = _verifier.ClothUnrollEvaluator

# `topogym.planning` is NumPy-only, so it imports normally.
sys.path.insert(0, str(REPO))
from topogym.planning.cloth_unroll_planner import (  # noqa: E402
    SHOVE_BAR_CLEARANCE,
    stroke_waypoints,
)

# The envelope rules and the ten feasibility rows, numpy only (the module the
# randomizer's derive / validate hooks and the Layout forward to).
_geometry = _load(
    "topogym.tasks.deformation._cloth_unroll_geometry",
    "topogym/tasks/deformation/_cloth_unroll_geometry.py",
)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


class _Node(dict):
    """Attribute access, as OmegaConf gives the real layout."""

    def __init__(self, data):
        super().__init__(
            {k: _Node(v) if isinstance(v, dict) else v for k, v in data.items()}
        )

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def spiral_of(cfg) -> np.ndarray:
    """The band's profile, built exactly as the real layout builds it."""

    cloth, dispenser = cfg["cloth"], cfg["dispenser"]
    return _mesh.spiral_profile(
        material_length=float(cloth["material_length"]),
        bar_radius=float(dispenser["bar_radius"]),
        clearance=float(cloth["roll"]["clearance"]),
        pitch=float(cloth["roll"]["pitch"]),
        turns=float(cloth["roll"]["turns"]),
        bar_height=float(dispenser["bar_height"]),
        rest_z=float(cloth["z"]),
        spacing=float(cloth["mesh"]["spacing"]),
    )


class _StandInLayout:
    """Just enough of `ClothUnrollLayout` for the planner, without Genesis.

    Reads the same config and the same profile generator the real layout does, so
    a change to one and not the other shows up as this check disagreeing with the
    demo's own log line.
    """

    def __init__(self, cfg, table_z: float = 0.0):
        self.task_cfg = _Node(cfg)
        self._cfg = cfg
        self._table_z = float(table_z)
        cloth = cfg["cloth"]
        self.material_axis = 0 if str(cloth["material_axis"]).lower() == "x" else 1
        self.bar_axis = 1 - self.material_axis
        self._profile = spiral_of(cfg)
        self._marks = _mesh.spiral_landmarks(
            self._profile,
            bar_height=float(cfg["dispenser"]["bar_height"]),
            rest_z=float(cloth["z"]),
        )
        self._centre = np.asarray([cloth["center_x"], cloth["center_y"]], dtype=float)
        self._sign = -1.0 if int(cloth.get("pull_side", 1)) < 0 else 1.0

    @property
    def table_z(self) -> float:
        return self._table_z

    def landmarks(self) -> dict:
        return self._marks

    def bar_centre(self) -> np.ndarray:
        return self._centre.copy()

    def bar_height(self) -> float:
        return self._table_z + float(self._cfg["dispenser"]["bar_height"])

    def rest_z(self) -> float:
        return self._table_z + float(self._cfg["cloth"]["z"])

    def _plan_point(self, material: float, height: float) -> np.ndarray:
        point = np.zeros(3)
        point[self.material_axis] = self._centre[self.material_axis] + self._sign * float(material)
        point[self.bar_axis] = self._centre[self.bar_axis]
        point[2] = self._table_z + float(height)
        return point

    def grasp_point(self) -> np.ndarray:
        end = self._marks["free_end_s"] - float(self._cfg["grasp"]["edge_inset"])
        return self._plan_point(end, float(self._cfg["cloth"]["z"]))

    def pull_direction(self) -> np.ndarray:
        direction = np.zeros(3)
        direction[self.material_axis] = self._sign
        return direction

    def rolled_length(self) -> float:
        return float(self._marks["rolled"])

    def pull_total(self) -> float:
        end = self.final_grasp_point()
        return float(self._sign * (end[self.material_axis] - self.grasp_point()[self.material_axis]))

    def stroke_count(self) -> int:
        return max(
            1,
            int(np.ceil(self.pull_total() / float(self._cfg["physical"]["stroke_m"]))),
        )

    def stroke_distance(self) -> float:
        return self.pull_total() / self.stroke_count()

    def final_grasp_point(self) -> np.ndarray:
        # The spool's taut end: from the glued tail's end, a straight band of
        # length L - pull_slack reaches the table this far along.
        offset = _geometry.tail_radius(self._cfg) + _geometry.taut_reach(
            self._cfg, _geometry.spool_cfg(self._cfg)["pull_slack"]
        )
        return self._plan_point(offset, float(self._cfg["cloth"]["z"]))

    def stroke_steps(self) -> int:
        return max(
            4,
            int(round(self.stroke_distance() / float(self._cfg["physical"]["pull_step_m"]))),
        )


# ------------------------------------------------------------- synthetic cloth
# Second copy of these three helpers, `check_cloth_unpleat_geometry.py` being the
# first. Left as a copy rather than shared: they are twelve lines of arithmetic
# each and pulling them into a module would make both checks depend on a third
# file whose only job is to be imported by two tests.


def arc_of(points) -> np.ndarray:
    """Cumulative arc length at each sample of a polyline."""

    points = np.asarray(points, dtype=float)
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(steps)])


def profile_at(polyline, arcs) -> np.ndarray:
    """Where each material point sits once the band takes shape ``polyline``.

    This is what keeps the synthetic cases index-aligned with the rest state:
    every case is the SAME particles in another configuration, which is what the
    evaluator is written for.
    """

    polyline = np.asarray(polyline, dtype=float)
    edges = arc_of(polyline)
    out = []
    for value in np.asarray(arcs, dtype=float):
        index = int(np.clip(np.searchsorted(edges, value) - 1, 0, len(polyline) - 2))
        span = max(edges[index + 1] - edges[index], 1e-12)
        fraction = np.clip((value - edges[index]) / span, 0.0, 1.0)
        out.append(polyline[index] + (polyline[index + 1] - polyline[index]) * fraction)
    return np.asarray(out, dtype=float)


def band_nodes(section, cfg, *, table_z: float = 0.0) -> np.ndarray:
    """Particles for a band whose cross-section samples are ``section``.

    Sampled at the particle size rather than the control spacing, because the
    judges bin onto an 8 mm grid and a 7.5 mm control mesh would leave gaps in it.
    """

    cloth = cfg["cloth"]
    step = float(cloth["particle_size"])
    width = float(cloth["width"])
    offsets = np.arange(-0.5 * width, 0.5 * width + 1e-9, step)
    centre = np.asarray([cloth["center_x"], cloth["center_y"]], dtype=float)
    material = 0 if str(cloth["material_axis"]).lower() == "x" else 1
    across = 1 - material
    section = np.asarray(section, dtype=float)
    out = np.zeros((len(offsets) * len(section), 3))
    index = 0
    for offset in offsets:
        for point in section:
            out[index, material] = centre[material] + point[0]
            out[index, across] = centre[across] + offset
            out[index, 2] = table_z + point[1]
            index += 1
    return out


def flat_polyline(cfg, *, shift: float = 0.0) -> np.ndarray:
    """The band after a successful unroll: one straight run, full length.

    Anchored under the bar rather than centred, because that is where the band
    reaches the table -- the pay-out grows it forward from there. ``shift`` tows
    the whole thing forward, which is the over-pull.
    """

    rest = float(cfg["cloth"]["z"])
    start = shift
    return np.array(
        [[start, rest], [start + float(cfg["cloth"]["material_length"]), rest]]
    )


def anchor_arc_of(cfg) -> float:
    return _geometry.spool_cfg(cfg)["anchor_arc"]


def spool_end_polyline(cfg, profile) -> np.ndarray:
    """The band once the spool has paid the roll out and the hand has let go.

    The inner ``anchor_arc`` of the profile is turned about the bar's axis so
    its outer end sits at the exit direction (what `Spool` does by the end of
    the pull); from there the band hangs straight down to the table and lies
    flat to the free end (the relaxed shape the judge's `over_pull` is zero at).
    """

    prof = np.asarray(profile, dtype=float)
    bar_h = float(cfg["dispenser"]["bar_height"])
    rest = float(cfg["cloth"]["z"])
    anchor = _geometry.spool_cfg(cfg)["anchor_arc"]
    arcs, angles = _geometry.spiral_angles(prof, bar_h)
    theta = -float(np.interp(anchor, arcs, angles))
    keep = prof[: int(np.searchsorted(arcs, anchor)) + 1]
    rel = keep - np.array([0.0, bar_h])
    c, s_ = np.cos(theta), np.sin(theta)
    turned = np.stack([c * rel[:, 0] - s_ * rel[:, 1], s_ * rel[:, 0] + c * rel[:, 1]], axis=1) + np.array([0.0, bar_h])
    r_t = _geometry.tail_radius(cfg)
    flat = _geometry.taut_length(cfg) - _geometry.hang_height(cfg)
    tail = np.array([[r_t, bar_h]])
    foot = np.array([[r_t, rest]])
    free = np.array([[r_t + flat + float(cfg["grasp"]["edge_inset"]), rest]])
    return np.vstack([turned, tail, foot, free])


def torn_polyline(cfg, profile, *, over: float) -> np.ndarray:
    """The glue has let go: nothing on the bar, the whole band flat on the table, pulled ``over`` past taut."""

    rest = float(cfg["cloth"]["z"])
    r_t = _geometry.tail_radius(cfg)
    front = _geometry.relaxed_front_offset(cfg) + float(over)
    return np.array([[front - float(cfg["cloth"]["material_length"]), rest], [front, rest]])


def torn_off_polyline(cfg, profile, *, shift: float = 0.090) -> np.ndarray:
    """The roll dragged whole off the bar and left lying on the table.

    Still a roll -- the same shape, still stacked -- just no longer on the bar
    and no longer where it was. The failure this scene has and `cloth_unpleat`
    did not, and the one `on_bar` exists to name.
    """

    moved = np.asarray(profile, dtype=float).copy()
    moved[:, 0] += float(shift)
    moved[:, 1] += float(cfg["cloth"]["z"]) - float(moved[:, 1].min())
    return moved


def _corner_cfgs(cfg):
    """Every vertex of the yaml's ``variation:`` box, underived, as (label, cfg).

    Built by hand from the block rather than through `layout_randomization` so
    this gate stays numpy + PyYAML: `uniform` axes at both ends, `choice` axes at
    every value, full product; then the same derivation the sampler runs.
    """

    import copy
    import itertools

    axes = []
    for entry in cfg["variation"]:
        if entry["kind"] == "uniform":
            axes.append((entry["path"], [float(entry["lo"]), float(entry["hi"])]))
        elif entry["kind"] == "choice":
            axes.append((entry["path"], list(entry["values"])))
    out = []
    for combo in itertools.product(*(values for _, values in axes)):
        c = copy.deepcopy(cfg)
        labels = []
        for (path, _), value in zip(axes, combo):
            node = c
            *parents, leaf = path.split(".")
            for part in parents:
                node = node[part]
            node[leaf] = value
            labels.append(f"{path.split('.')[-1]}={value}")
        out.append((",".join(labels), c))
    return out


def _derive(cfg) -> None:
    """The sampler's derivation step (`cloth_unroll.derive_task_cfg`), on a dict."""

    cfg["cloth"]["roll"]["pitch"] = _geometry.pitch_from_frac(cfg, float(cfg["cloth"]["roll"]["pitch_frac"]))
    leaf = _geometry.along_leaf(cfg)
    cfg["cloth"][leaf] = _geometry.center_along_from_frac(cfg, float(cfg["cloth"][f"{leaf}_frac"]))
    cfg["grasp"]["max_start_spread_ratio"] = _geometry.start_spread_limit(cfg)


_LOWER_IS_TIGHTER = ("hand_reach", "pull_within_stroke", "start_still_stored")


def _margin(row) -> float:
    name, measured, limit, _ = row
    return (limit - measured) if name in _LOWER_IS_TIGHTER else (measured - limit)


def _start_state(cfg):
    """The real evaluator on the band as built (before any settle), for the start guard."""

    profile = spiral_of(cfg)
    section = _mesh.resample_polyline(profile, float(cfg["cloth"]["particle_size"]))
    nodes = band_nodes(section, cfg)
    centre = np.asarray([cfg["cloth"]["center_x"], cfg["cloth"]["center_y"]], dtype=float)
    return ClothUnrollEvaluator.from_config(cfg).classify(
        nodes, nodes, table_z=0.0, bar_centre=centre, bar_height=float(cfg["dispenser"]["bar_height"])
    )


def envelope_section(cfg) -> None:
    import copy

    rows = _geometry.cloth_unroll_checks(cfg)
    for name, measured, limit, ok in rows:
        print(f"  {name:28s} {measured:+.4f} / {limit:+.4f} {'ok' if ok else 'FAIL'}")
    check("基准 yaml 十行全过", all(ok for *_, ok in rows), ",".join(n for n, *_, ok in rows if not ok))
    check("十行齐全", [r[0] for r in rows] == [
        "flat_run_fits_grasp", "grasp_clears_drape", "grasp_clears_dispenser", "roll_clears_table",
        "posts_above_roll", "layers_spaced", "band_in_workspace", "hand_reach", "pull_within_stroke",
        "start_still_stored",
    ], str([r[0] for r in rows]))

    base = copy.deepcopy(cfg)
    _derive(base)
    design_spread = _geometry.design_spread_ratio(cfg)
    check(
        "派生还原基准：pitch_frac 0 → 0.014，center_y_frac 0.5 → −0.100，守卫 = 设计铺展比 + 0.11 ≈ 0.50",
        abs(base["cloth"]["roll"]["pitch"] - 0.014) < 1e-9
        and abs(base["cloth"]["center_y"] + 0.100) < 1e-9
        and abs(base["grasp"]["max_start_spread_ratio"] - (design_spread + 0.11)) < 1e-9
        and abs(base["grasp"]["max_start_spread_ratio"] - 0.50) < 0.005,
        f"pitch={base['cloth']['roll']['pitch']:.4f} center_y={base['cloth']['center_y']:+.4f} "
        f"spread_max={base['grasp']['max_start_spread_ratio']:.4f}（设计 {design_spread:.3f}）",
    )
    lo, hi = _geometry.pitch_bounds(cfg)
    check(
        "基准 1.5 圈下层距窗口被平铺段封顶在 0.018 以下（1.5 圈 + 层距 0.018 没有平铺段）",
        abs(lo - 0.014) < 1e-9 and 0.016 < hi < 0.018 - 1e-9,
        f"[{lo:.4f}, {hi:.4f}]",
    )
    lo, hi = _geometry.center_along_bounds(cfg)
    check("基准下支架纵向位置区间是 −0.100 ± 0.030（可达与工作区不封顶）", abs(lo + 0.130) < 1e-9 and abs(hi + 0.070) < 1e-9, f"[{lo:+.4f}, {hi:+.4f}]")

    # Mirror layout: same rows, negated grasp and pull end, planner pulls -y.
    mirror = copy.deepcopy(cfg)
    mirror["cloth"]["pull_side"] = -1
    _derive(mirror)
    plus_rows, minus_rows = _geometry.cloth_unroll_checks(base), _geometry.cloth_unroll_checks(mirror)
    check(
        "镜像布局（pull_side −1）十行读数与 +1 逐行相等",
        all(abs(a[1] - b[1]) < 1e-12 and abs(a[2] - b[2]) < 1e-12 for a, b in zip(plus_rows, minus_rows)),
    )
    gp, gm = _geometry.grasp_point_task(base), _geometry.grasp_point_task(mirror)
    ep, em = _geometry.pull_end_task(base), _geometry.pull_end_task(mirror)
    check(
        "镜像布局的支架、抓取点与拉动终点是 +1 的 y 取反",
        abs(mirror["cloth"]["center_y"] + base["cloth"]["center_y"]) < 1e-12
        and abs(gp[0] - gm[0]) < 1e-12 and abs(gp[1] + gm[1]) < 1e-12 and abs(ep[1] + em[1]) < 1e-12,
        f"+1 grasp y {gp[1]:+.4f} end y {ep[1]:+.4f}; −1 grasp y {gm[1]:+.4f} end y {em[1]:+.4f}",
    )
    stand_in = _StandInLayout(mirror)
    check(
        "镜像布局的规划器沿 −y 拉，shove 朝横梁推",
        float(stroke_waypoints(stand_in, motion="unroll")[-1].position[1]) < stand_in.grasp_point()[1]
        and float(stroke_waypoints(stand_in, motion="shove")[-1].position[1]) > stand_in.grasp_point()[1],
    )

    # Corners.
    corners = _corner_cfgs(cfg)
    rejected, failed, tight = [], [], {}
    fewest_cells, guard_margin = None, None
    for label, c in corners:
        try:
            _derive(c)
        except ValueError as exc:
            rejected.append(f"{label}: {exc}")
            continue
        rows = _geometry.cloth_unroll_checks(c)
        bad = [n for n, *_, ok in rows if not ok]
        if bad:
            failed.append(f"{label}: {bad}")
        for row in rows:
            m = _margin(row)
            if row[0] not in tight or m < tight[row[0]][0]:
                tight[row[0]] = (m, label)
        # The demo's start guard on the band as built: the derived spread limit
        # sits `START_SPREAD_SLACK` above the design, and the layer count the
        # guard also asks for stays far above its floor at every corner.
        state = _start_state(c)
        cells = int(state.over_layer_cells)
        if fewest_cells is None or cells < fewest_cells[0]:
            fewest_cells = (cells, label)
        gm = float(c["grasp"]["max_start_spread_ratio"]) - float(state.spread_ratio)
        if guard_margin is None or gm < guard_margin[0]:
            guard_margin = (gm, label)
    check("角点数 = 2 × 3 × 2^4 = 96", len(corners) == 96, str(len(corners)))
    check("96 个角点派生区间都非空", not rejected, "; ".join(rejected[:3]))
    check("96 个角点十行全过", not failed, "; ".join(failed[:3]))
    for name, (m, label) in tight.items():
        print(f"  最紧 {name:28s} 余量 {m:+.4f}  @ {label}")
    check(
        "层距与纵向位置的派生把最紧的行压到 0 而不是负数",
        min(tight[n][0] for n in ("grasp_clears_dispenser", "roll_clears_table", "flat_run_fits_grasp", "hand_reach")) >= -1e-9,
    )
    check(
        f"96 个角点的出生三层格数都 ≥ 守卫 {int(cfg['grasp']['min_start_three_layer_cells'])}",
        fewest_cells[0] >= int(cfg["grasp"]["min_start_three_layer_cells"]),
        f"最少 {fewest_cells[0]} @ {fewest_cells[1]}",
    )
    check(
        "96 个角点的派生守卫都在出生铺展比之上 0.11（真实判定器读的出生态）",
        abs(guard_margin[0] - _geometry.START_SPREAD_SLACK) < 0.02,
        f"最小余量 {guard_margin[0]:+.3f} @ {guard_margin[1]}",
    )

    # Negative examples: what the rows are for.
    many = copy.deepcopy(cfg)
    many["cloth"]["roll"]["turns"] = 1.75
    try:
        _geometry.pitch_bounds(many)
        many_ok, detail = False, "窗口非空"
    except ValueError as exc:
        many_ok, detail = True, str(exc)[:90]
    check("负例：1.75 圈在 0.280 m 材料下任何层距都没有平铺段，派生窗口为空（圈数只到 1.5 的原因）", many_ok, detail)

    high = copy.deepcopy(cfg)
    high["dispenser"]["bar_height"] = 0.053
    high["cloth"]["roll"]["pitch_frac"] = 1.0
    _derive(high)
    top = high["cloth"]["roll"]["pitch"]
    loose = copy.deepcopy(high)
    loose["cloth"]["roll"]["pitch"] = 0.016
    rows = {r[0]: r for r in _geometry.cloth_unroll_checks(loose)}
    check(
        "负例：1.5 圈 + 杆高 0.053 时层距 0.016 让抓取点离梁心 < 57 mm，派生窗口上端低于 0.016",
        not rows["grasp_clears_dispenser"][3] and top < 0.016,
        f"grasp_clears_dispenser {rows['grasp_clears_dispenser'][1] * 1e3:.1f} mm < 57；窗口上端 {top:.4f}",
    )

    # With the spool's taut end point the farthest pull end sits about 0.63
    # from the base and the reach row never caps the window; the row is
    # exercised with a longer band (0.40 m), which pushes the end out.
    far = copy.deepcopy(cfg)
    far["cloth"]["center_x"] = 0.050
    far["dispenser"]["bar_height"] = 0.053
    far["cloth"]["center_y_frac"] = 1.0
    far["cloth"]["material_length"] = 0.40
    _derive(far)
    lo, hi = _geometry.center_along_bounds(far)
    far["cloth"]["center_y"] = -0.070
    rows = {r[0]: r for r in _geometry.cloth_unroll_checks(far)}
    check(
        "负例：布长 0.40 m 时支架最靠外的纵向 −0.070 被可达行拒，派生窗口上端低于 −0.070",
        not rows["hand_reach"][3] and hi < -0.070 - 1e-9,
        f"hand_reach {rows['hand_reach'][1]:.4f} > {rows['hand_reach'][2]:.4f}；窗口 [{lo:+.4f}, {hi:+.4f}]",
    )

    one = copy.deepcopy(cfg)
    one["cloth"]["roll"]["turns"] = 1.0
    fixed_guard = {r[0]: r for r in _geometry.cloth_unroll_checks(one)}
    _derive(one)
    derived_guard = {r[0]: r for r in _geometry.cloth_unroll_checks(one)}
    check(
        "负例：1 圈的卷设计铺展比 > 固定守卫 0.50（会被 demo 当 material_already_released 中止），派生守卫放行",
        not fixed_guard["start_still_stored"][3] and derived_guard["start_still_stored"][3],
        f"设计铺展比 {fixed_guard['start_still_stored'][1]:.3f}；固定 0.50 / 派生 {derived_guard['start_still_stored'][2]:.3f}",
    )


def spool_section(cfg) -> None:
    """The spool's bound set, glued tail, turn angle and taut geometry on the synthetic band, no Genesis.

    Same particles `band_nodes` gives the judges (particle-size sampling of the
    profile, every row across the width), mapped onto the profile by arc length
    the way `Spool` does it at birth.
    """

    import copy

    block = cfg["cloth"]["spool"]
    check("转轴默认开启", bool(block["enabled"]), str(block))
    lead, anchor = float(block["lead"]), float(block["anchor_arc"])
    loose = copy.deepcopy(cfg)
    loose["cloth"]["roll"]["turns"] = 1.0
    loose["cloth"]["roll"]["pitch"] = 0.018
    loose["dispenser"]["bar_height"] = 0.037
    for label, c in (("基准 1.5 圈", cfg), ("角点 c002（1 圈、层距 0.018、杆高 0.037）", loose)):
        cloth, dispenser = c["cloth"], c["dispenser"]
        step = float(cloth["particle_size"])
        bar_h = float(dispenser["bar_height"])
        profile = spiral_of(c)
        marks = _mesh.spiral_landmarks(profile, bar_height=bar_h, rest_z=float(cloth["z"]))
        section = _mesh.resample_polyline(profile, step)
        arcs = arc_of(section)
        rows = len(np.arange(-0.5 * float(cloth["width"]), 0.5 * float(cloth["width"]) + 1e-9, step))
        nodes = band_nodes(section, c)
        material = 0 if str(cloth["material_axis"]).lower() == "x" else 1
        centre = np.asarray([cloth["center_x"], cloth["center_y"]], dtype=float)
        mz = np.stack([nodes[:, material] - centre[material], nodes[:, 2]], axis=1)
        held, remaining, glued = _geometry.spool_plan(mz, profile, marks, lead, anchor)
        rolled = float(marks["rolled"])

        expect_cols = int(np.count_nonzero((arcs <= rolled + 1e-9) & (rolled - arcs > lead)))
        check(
            f"{label}：记账集合 held = 卷上离出口 > lead 的材料（{expect_cols} 列 × {rows} 行）",
            abs(held.size - expect_cols * rows) <= rows,
            f"held {held.size}，卷料 {rolled * 1e3:.1f} mm，lead {lead * 1e3:.0f} mm",
        )
        expect_glued = int(np.count_nonzero(arcs <= anchor + 1e-9))
        inner = np.arange(rows) * len(section)
        check(
            f"{label}：粘住的尾端 = 内端起 anchor_arc 的材料（{expect_glued} 列），含内端；这是唯一真正钉到辊上的一组",
            abs(int(glued.sum()) - expect_glued * rows) <= rows and bool(np.all(np.isin(inner, held[glued]))),
            f"粘住 {int(glued.sum())}",
        )
        radial = np.hypot(mz[held, 0], mz[held, 1] - bar_h)
        check(
            f"{label}：记账集合都落在杆上的卷里，垂落段与平铺段一个不计",
            bool(np.all(radial <= float(marks["roll_radius"]) + step))
            and bool(np.all(mz[held, 1] > float(cloth["z"]) + step)),
            f"离杆轴最远 {radial.max() * 1e3:.1f} mm（卷半径 {float(marks['roll_radius']) * 1e3:.1f}）",
        )
        # Release order along the pull: nested sets, nothing at d = 0, everything
        # but the glued tail by d = rolled - anchor_arc, the glued tail never.
        prev = np.zeros(held.size, dtype=bool)
        nested = True
        for d in np.arange(0.0, rolled + 0.005, 0.005):
            now = (remaining <= d + lead) & ~glued
            nested = nested and bool(np.all(now | ~prev))
            prev = now
        none_at_start = not np.any(remaining <= lead)
        free_by_end = bool(np.all(((remaining <= (rolled - anchor) + lead + 1e-9) | glued)))
        check(
            f"{label}：释放集合随放出长度单调增大，d = 0 不放、d = 卷料 − anchor_arc 时除尾端外全放，尾端永不放",
            nested and none_at_start and free_by_end,
        )
        # The turn: the unwrapped angle falls with arc, the spool's angle is
        # monotone in the pay-out and stops at the glued tail; turning the
        # synthetic front particle by that angle puts it at the exit direction.
        s_arcs, s_angles = _geometry.spiral_angles(profile, bar_h)
        check(
            f"{label}：绕杆展开角随弧长单调下降，从 2π × 圈数到出口的 0",
            bool(np.all(np.diff(s_angles) <= 1e-9)) and abs(s_angles[0] - 2.0 * np.pi * float(cloth["roll"]["turns"])) < 0.05
            and abs(s_angles[-1]) < 1e-9,
            f"内端 {np.degrees(s_angles[0]):.0f}°",
        )
        ds = np.arange(0.0, rolled + 0.02, 0.005)
        thetas = np.array([_geometry.spool_angle(c, d) for d in ds])
        stop = rolled - anchor
        check(
            f"{label}：辊的转角随放出长度单调，放出 卷料 − anchor_arc 之后不再转",
            bool(np.all(np.diff(thetas) <= 1e-9)) and float(np.ptp(thetas[ds >= stop])) < 1e-9 and thetas[0] == 0.0,
            f"总转角 {np.degrees(thetas[-1]):+.0f}°",
        )
        worst = 0.0
        for d in np.arange(0.01, stop, 0.02):
            front_arc = rolled - d
            m0 = float(np.interp(front_arc, s_arcs, profile[: len(s_arcs), 0]))
            z0 = float(np.interp(front_arc, s_arcs, profile[: len(s_arcs), 1]))
            th = _geometry.spool_angle(c, d)
            rel = np.array([m0, z0 - bar_h])
            turned = np.array([np.cos(th) * rel[0] - np.sin(th) * rel[1], np.sin(th) * rel[0] + np.cos(th) * rel[1]])
            worst = max(worst, abs(float(np.arctan2(turned[1], turned[0]))))
        check(
            f"{label}：按转角转过之后，剥离前沿的粒子落在出口方向（角度差 < 3°）",
            worst < np.radians(3.0),
            f"最大偏差 {np.degrees(worst):.2f}°",
        )
        mirrored = nodes.copy()
        mirrored[:, material] = centre[material] - (nodes[:, material] - centre[material])
        mz_m = np.stack([-(mirrored[:, material] - centre[material]), mirrored[:, 2]], axis=1)
        held_m, remaining_m, glued_m = _geometry.spool_plan(mz_m, profile, marks, lead, anchor)
        check(
            f"{label}：镜像布局（pull_side −1）用带符号的偏移投影后得到同一批粒子",
            np.array_equal(held, held_m) and np.allclose(remaining, remaining_m) and np.array_equal(glued, glued_m),
        )
        # Taut geometry: the oracle's end point leaves `pull_slack` of band; the
        # tear rule fires `tear_allowance` past taut.
        slack = float(block["pull_slack"])
        tear = float(block["tear_allowance"])
        r_t = _geometry.tail_radius(c)
        hang = _geometry.hang_height(c)
        L = _geometry.taut_length(c)
        end_reach = _geometry.taut_reach(c, slack)
        dist_end = float(np.hypot(end_reach, hang))
        check(
            f"{label}：oracle 终点处尾端到抓取点的直线距离 = L − pull_slack；再走 pull_slack + tear_allowance 到扯断",
            abs(dist_end - (L - slack)) < 1e-9
            and abs(float(np.hypot(_geometry.taut_reach(c, -tear), hang)) - (L + tear)) < 1e-9
            and r_t > float(dispenser["bar_radius"]),
            f"L {L * 1e3:.1f} mm，垂落高 {hang * 1e3:.1f}，终点离轴 {(r_t + end_reach) * 1e3:.1f} mm",
        )


def main(argv=None) -> int:
    cfg = yaml.safe_load(TASK_CFG.read_text(encoding="utf-8"))
    evaluator = ClothUnrollEvaluator.from_config(cfg)
    limits = evaluator.thresholds
    cloth, dispenser = cfg["cloth"], cfg["dispenser"]
    axis = 0 if str(cloth["material_axis"]).lower() == "x" else 1
    centre = np.asarray([cloth["center_x"], cloth["center_y"]], dtype=float)

    profile = spiral_of(cfg)
    marks = _mesh.spiral_landmarks(
        profile,
        bar_height=float(dispenser["bar_height"]),
        rest_z=float(cloth["z"]),
    )

    print("\n== 卷筒几何：材料守恒 ==")
    check(
        "剖面长度等于配置的材料全长",
        abs(marks["material_length"] - float(cloth["material_length"])) < 1e-6,
        f"{marks['material_length'] * 1e3:.2f}mm",
    )
    check(
        "收在卷筒里的材料 = 全长 − 俯视跨度",
        abs(marks["stored"] - (marks["material_length"] - marks["plan_span"])) < 1e-12,
        f"stored={marks['stored'] * 1e3:.1f}mm span={marks['plan_span'] * 1e3:.1f}mm",
    )
    # 卷料 = 螺旋段弧长减去垂落段。行程等于它，不多不少 —— 这是把行程变成守恒量
    # 而不是调出来的数的那一步。
    drape = float(dispenser["bar_height"]) - float(cloth["z"])
    check(
        "卷料 + 垂落 + 平铺 = 材料全长",
        abs(
            marks["rolled"] + drape + marks["flat_run"] - marks["material_length"]
        ) < 1e-6,
        f"卷 {marks['rolled'] * 1e3:.1f} + 垂 {drape * 1e3:.1f} + "
        f"铺 {marks['flat_run'] * 1e3:.1f} = {marks['material_length'] * 1e3:.1f}mm",
    )
    inner = float(dispenser["bar_radius"]) + float(cloth["roll"]["clearance"])
    check(
        "最内圈与梁面之间留得下一个粒子",
        float(cloth["roll"]["clearance"]) >= float(cloth["particle_size"]),
        f"净空 {float(cloth['roll']['clearance']) * 1e3:.1f}mm ≥ 粒径 "
        f"{float(cloth['particle_size']) * 1e3:.1f}mm（内圈半径 {inner * 1e3:.1f}mm）",
    )
    check(
        "层与层之间留得下一个粒子",
        float(cloth["roll"]["pitch"]) >= float(cloth["particle_size"]),
        f"层距 {float(cloth['roll']['pitch']) * 1e3:.1f}mm ≥ 粒径 "
        f"{float(cloth['particle_size']) * 1e3:.1f}mm",
    )
    check(
        "卷筒底不压在桌面上",
        float(dispenser["bar_height"]) - marks["roll_radius"] > float(cloth["z"]),
        f"卷底离桌 "
        f"{(float(dispenser['bar_height']) - marks['roll_radius'] - float(cloth['z'])) * 1e3:.1f}mm"
        f"（外径 {2 * marks['roll_radius'] * 1e3:.1f}mm）",
    )
    check(
        "立柱高过卷筒顶",
        float(dispenser["post_height"])
        > float(dispenser["bar_height"]) + marks["roll_radius"],
        f"柱高 {float(dispenser['post_height']) * 1e3:.0f}mm > 卷顶 "
        f"{(float(dispenser['bar_height']) + marks['roll_radius']) * 1e3:.0f}mm",
    )
    check(
        "梁比布宽，两侧都挡得住",
        float(dispenser["span"]) > float(cloth["width"]),
        f"梁长 {float(dispenser['span']) * 1e3:.0f}mm > 布宽 "
        f"{float(cloth['width']) * 1e3:.0f}mm",
    )
    # 布从卷筒侧面切向离开，切线接近竖直 —— 从底部离开就要多一道折痕。
    tangent = profile[1] - profile[0]
    exit_index = int(np.argmin(np.abs(profile[:, 0] - marks["exit_s"])))
    leave = profile[exit_index] - profile[max(exit_index - 1, 0)]
    leave = leave / max(float(np.linalg.norm(leave)), 1e-12)
    check(
        "布在卷筒侧面切向离开，切线接近竖直",
        abs(leave[1]) > 0.9 and marks["exit_s"] > 0.0,
        f"离开切线 ({leave[0]:+.3f},{leave[1]:+.3f})，出口在材料侧 "
        f"{marks['exit_s'] * 1e3:+.1f}mm",
    )
    del tangent

    print("\n== 抓取护栏 ==")
    # 附着盘在俯视图上是个圆（`attach_z_band` 关着，没有高度窗口），所以条件是
    # **盘半径 + 余量 < 抓取点到最近的非平铺材料的距离**。最近的非平铺材料是垂落段，
    # 它在俯视图上就落在卷筒外缘 exit_s 处。
    #
    # 余量取 2 个粒子，与 `on_bar` 判定半径同一约定：静置之后自由端会移一点，
    # 平铺段短了一个粒子也不该让盘够到垂落段。
    #
    # 1.2 那边用的是「2 倍盘半径」，那是一个没有推导的余量；这里按实际几何写，
    # 因为本任务的平铺段只有 43mm，2 倍盘半径会把一个其实成立的配置判掉。
    grasp_s = marks["free_end_s"] - float(cfg["grasp"]["edge_inset"])
    clear = grasp_s - marks["exit_s"]
    need = float(cfg["grasp"]["attach_radius"]) + 2.0 * float(cloth["particle_size"])
    check(
        "抓取点离垂落段足够远，附着盘只碰得到平铺的那一层",
        clear > need,
        f"离垂落段 {clear * 1e3:.1f}mm > 盘半径 + 2 粒径 {need * 1e3:.1f}mm",
    )
    check(
        "高度窗口已关闭（端头只有一层，不需要它）",
        cfg["grasp"]["attach_z_band"] is None,
        f"attach_z_band={cfg['grasp']['attach_z_band']}",
    )
    check(
        "整个附着盘落在布上（抓取点离边缘够远）",
        float(cfg["grasp"]["edge_inset"]) >= float(cloth["particle_size"]) * 2.0,
        f"内缩 {float(cfg['grasp']['edge_inset']) * 1e3:.1f}mm ≥ 2 倍粒径 "
        f"{float(cloth['particle_size']) * 2.0 * 1e3:.1f}mm",
    )

    print("\n== 判据：四种末态 ==")
    # One set of material points, four configurations of it. `arcs` is where each
    # point sits along the material, which is the only thing that does not change.
    section = _mesh.resample_polyline(profile, float(cloth["particle_size"]))
    arcs = arc_of(section)
    rest_nodes = band_nodes(section, cfg)
    bar_kw = {"bar_centre": centre, "bar_height": float(dispenser["bar_height"])}
    slack = _geometry.spool_cfg(cfg)["pull_slack"]
    cases = {
        # The spool version's correct end: the glued tail still on the bar, the
        # band straight from it to the table with `pull_slack` to spare.
        "unroll（正确）": band_nodes(profile_at(spool_end_polyline(cfg, profile), arcs), cfg),
        # t=0 的建模形状，也是仿真的起始状态：卷筒还挂在梁上。
        "rolled（起始态／还卷着）": rest_nodes,
        "torn_off（整卷被扯下来）": band_nodes(
            profile_at(torn_off_polyline(cfg, profile), arcs), cfg
        ),
        # The glue let go: pulled 100 mm past taut, nothing left on the bar.
        "overpull（拉过头，尾端被扯断）": band_nodes(
            profile_at(torn_polyline(cfg, profile, over=0.10), arcs), cfg
        ),
    }
    states = {}
    for label, nodes in cases.items():
        state = evaluator.classify(rest_nodes, nodes, table_z=0.0, **bar_kw)
        states[label] = state
        print(
            f"  {label:28s} single={state.single_layer_frac:.3f} "
            f"recovered={state.recovered_frac:+.3f} "
            f"on_bar={state.on_bar:5d} "
            f"over_pull={state.over_pull * 1e3:+6.1f}mm "
            f"tail_gap={state.tail_gap * 1e3:+6.1f}mm "
            f"out_of_plane={state.out_of_plane * 1e3:5.2f}mm "
            f"terminal={state.is_terminal}"
        )

    good = states["unroll（正确）"]
    rolled = states["rolled（起始态／还卷着）"]
    torn = states["torn_off（整卷被扯下来）"]
    over = states["overpull（拉过头，尾端被扯断）"]

    check("拉刚好的布带三条门槛全过（尾端还在辊上、其余铺平）", good.is_terminal, good.summary())
    check(
        "起始态（还卷着）不算完成",
        not rolled.is_terminal,
        f"gates={[k for k, v in rolled.gates.items() if not v]}",
    )
    check(
        "起始态被层数与材料守恒一起挡住",
        not rolled.gates["single_layer_frac"] and not rolled.gates["recovered_frac"],
        f"single={rolled.single_layer_frac:.3f} < {limits.single_layer_frac_min} 且 "
        f"recovered={rolled.recovered_frac:+.3f} < {limits.recovered_frac_min}",
    )
    # 本场景独有的失败：整卷被从梁上扯下来。它和「卷筒没转」在两条门槛上读数相近，
    # 分得开它们的是 on_bar —— 这就是这个读数存在的理由。
    check(
        "整卷被扯下来不算完成",
        not torn.is_terminal,
        f"gates={[k for k, v in torn.gates.items() if not v]}",
    )
    check(
        "on_bar 分得开「被扯下来」与「卷筒没转」",
        torn.on_bar == 0 and rolled.on_bar > 0,
        f"扯下来 {torn.on_bar} / 还在梁上 {rolled.on_bar}",
    )
    check(
        "完全展开之后辊上只剩粘住的尾端，数目过 on_bar_min",
        limits.on_bar_min is not None and good.on_bar >= limits.on_bar_min,
        f"on_bar={good.on_bar} ≥ {limits.on_bar_min}",
    )
    # 2026-09-06 起拉过头是失败：两条材料门它过得更好，拦下它的是尾端被扯离辊
    # （on_bar_min）与前端越过绷直位（over_pull）。
    check(
        "拉过头（扯断）被 tail_on_bar 与 over_pull 两条门拦下，两条材料门仍过（它多做了，不是没做）",
        not over.is_terminal
        and over.gates["single_layer_frac"]
        and over.gates["recovered_frac"]
        and not over.gates["tail_on_bar"]
        and not over.gates["over_pull"],
        f"recovered={over.recovered_frac:+.3f} on_bar={over.on_bar} over_pull={over.over_pull * 1e3:+.1f}mm > "
        f"{limits.over_pull_max * 1e3:.0f}mm",
    )
    check(
        "松手后的布带前端停在放松位，over_pull ≈ 0 在门内，回收比 ≈ 1；后端距离只记录",
        good.gates["over_pull"] and abs(good.over_pull) < 0.008 and abs(good.recovered_frac - 1.0) < 0.05
        and "tail_gap" not in good.gates,
        f"over_pull={good.over_pull * 1e3:+.1f}mm ≤ {limits.over_pull_max * 1e3:.0f}mm，"
        f"recovered={good.recovered_frac:.3f}，tail_gap={good.tail_gap * 1e3:+.1f}mm",
    )
    # 离面厚度顶替 docx 的「累计转角」：重网格化不保顶点顺序，沿带长排序做不出来。
    # 转轴版的正确末态有一段从辊上竖直垂下的布，离面厚度读数与卷着相近，所以只记录；
    # 分得开的是「全在桌上」（扯断后）与「还卷着」。
    check(
        "离面厚度分得开「全在桌上」与「还卷着」（转轴版正确末态挂着一段，只记录）",
        rolled.out_of_plane > over.out_of_plane * 3.0 and "out_of_plane" not in good.gates,
        f"卷着 {rolled.out_of_plane * 1e3:.2f}mm vs 全在桌上 {over.out_of_plane * 1e3:.2f}mm，"
        f"正确末态 {good.out_of_plane * 1e3:.2f}mm",
    )
    check(
        "累计转角的替代读数只记录不判定",
        limits.out_of_plane_max is None and "out_of_plane" not in good.gates,
        f"out_of_plane_max={limits.out_of_plane_max}，门槛={sorted(good.gates)}",
    )
    check(
        "on_bar 的上限只记录，下限（尾端还在辊上）判定",
        limits.on_bar_max is None and "on_bar" not in good.gates and "tail_on_bar" in good.gates,
        f"on_bar_max={limits.on_bar_max} on_bar_min={limits.on_bar_min}",
    )
    # 类别合同 C1 (task_taxonomy_zh.md 4.1)：结构指标与形态指标的合取，
    # 禁止单一位置阈值。
    check(
        "四条门槛：结构（层数）、形态（长度）、位置（前端越过绷直位）、尾端还在辊上，是合取",
        sorted(good.gates) == ["over_pull", "recovered_frac", "single_layer_frac", "tail_on_bar"],
        f"门槛={sorted(good.gates)}",
    )
    check(
        "band_shift 不在读数里（本场景没有「不该动的那半段布」），over_pull 与 tail_gap 在",
        "band_shift_mm" not in good.to_info() and "over_pull_mm" in good.to_info()
        and "tail_gap_mm" in good.to_info(),
        f"readings={sorted(k for k in good.to_info() if k.endswith('_mm'))}",
    )

    print("\n== 阈值两侧的余量 ==")
    for name, value_good, value_bad, limit in (
        (
            "single_layer_frac",
            good.single_layer_frac,
            rolled.single_layer_frac,
            limits.single_layer_frac_min,
        ),
        (
            "recovered_frac",
            good.recovered_frac,
            rolled.recovered_frac,
            limits.recovered_frac_min,
        ),
    ):
        check(
            f"{name} 的阈值卡在正确与起始态之间",
            value_good >= limit > value_bad,
            f"正确 {value_good:.3f} / 阈值 {limit:.3f} / 起始 {value_bad:.3f}",
        )
    # 起始护栏必须放行真实的起始态，否则 demo 第一步就停在自己的护栏上。
    start_spread = rolled.spread_ratio
    check(
        "起始护栏放行真实起始态（材料还收着）",
        start_spread <= float(cfg["grasp"]["max_start_spread_ratio"]),
        f"起始铺展比 {start_spread:.3f} ≤ "
        f"{float(cfg['grasp']['max_start_spread_ratio'])}",
    )
    check(
        "起始护栏放行真实起始态（层数还在）",
        rolled.over_layer_cells >= int(cfg["grasp"]["min_start_three_layer_cells"]),
        f"多层格 {rolled.over_layer_cells} ≥ "
        f"{int(cfg['grasp']['min_start_three_layer_cells'])}",
    )

    check(
        "over_pull 的门卡在拉刚好与拉过头之间",
        good.over_pull <= limits.over_pull_max < over.over_pull,
        f"刚好 {good.over_pull * 1e3:+.1f} / 门 {limits.over_pull_max * 1e3:.0f} / "
        f"过拉 {over.over_pull * 1e3:+.1f} mm",
    )

    print("\n== 轨迹 ==")
    layout = _StandInLayout(cfg)
    grasp = layout.grasp_point()
    strokes = layout.stroke_count()
    unroll_wp = stroke_waypoints(layout, motion="unroll")
    shove_wp = stroke_waypoints(layout, motion="shove")
    over_wp = stroke_waypoints(layout, motion="overpull", overpull_scale=1.6)

    # 总行程不是调出来的：终点是「尾端粘在辊上、布绷直减 pull_slack」的几何位置
    # （2026-09-06 转轴起）。它比卷料长：剥完卷料之后垂落段还要铺平。
    slack = _geometry.spool_cfg(cfg)["pull_slack"]
    predicted_travel = (
        _geometry.tail_radius(cfg) + _geometry.taut_reach(cfg, slack)
        - (marks["free_end_s"] - float(cfg["grasp"]["edge_inset"]))
    )
    check(
        "总行程 = 绷直终点 − 抓取点，比卷料长（垂落段也要铺平）",
        abs(layout.pull_total() - predicted_travel) < 1e-9 and layout.pull_total() > marks["rolled"] - anchor_arc_of(cfg),
        f"{layout.pull_total() * 1e3:.1f}mm；卷料 {marks['rolled'] * 1e3:.1f}mm，粘住 {anchor_arc_of(cfg) * 1e3:.0f}mm",
    )
    check(
        "铺平位移 = 卷料 + 垂落 − (卷筒半径 − 内端偏置)",
        abs(
            marks["flat_travel"]
            - (
                marks["rolled"]
                + (float(dispenser["bar_height"]) - float(cloth["z"]))
                - (marks["exit_s"] - marks["inner_s"])
            )
        ) < 1e-9,
        f"{marks['rolled'] * 1e3:.1f} + "
        f"{(float(dispenser['bar_height']) - float(cloth['z'])) * 1e3:.1f} − "
        f"{(marks['exit_s'] - marks['inner_s']) * 1e3:.1f} = "
        f"{marks['flat_travel'] * 1e3:.1f}mm",
    )
    check(
        "行程按段数均分，不是「几段满行程 + 一段零头」",
        abs(strokes * layout.stroke_distance() - layout.pull_total()) < 1e-12,
        f"{strokes} 段 × {layout.stroke_distance() * 1e3:.1f}mm = "
        f"{layout.pull_total() * 1e3:.1f}mm",
    )
    check(
        "每段不超过配置的单段上限",
        layout.stroke_distance() <= float(cfg["physical"]["stroke_m"]) + 1e-12,
        f"每段 {layout.stroke_distance() * 1e3:.1f}mm ≤ 上限 "
        f"{float(cfg['physical']['stroke_m']) * 1e3:.1f}mm",
    )
    check(
        "出厂配置一次连续拉完，不分段",
        strokes == 1,
        f"{strokes} 段 × {layout.stroke_distance() * 1e3:.1f}mm",
    )
    # 分段与否终点相同 —— 这正是 2026-08-24 取消分段的那条算术：手停在
    # 「起点 + **总**行程」，切成几段都一样，所以分段从来没有换来可达性，
    # 只换来两次「松手 → 退开 → 回来 → 重新抓」。钉住它，免得再有人拿可达性
    # 当理由把行程切碎。
    split_cfg = copy.deepcopy(cfg)
    split_cfg["physical"]["stroke_m"] = 0.040
    split = _StandInLayout(split_cfg)
    check(
        "切成多段之后手的终点不变（分段换不来可达性）",
        split.stroke_count() > 1
        and abs(
            float(split.final_grasp_point()[axis]) - float(layout.final_grasp_point()[axis])
        ) < 1e-12,
        f"{split.stroke_count()} 段与 {strokes} 段都停在 "
        f"{'xy'[axis]}={float(layout.final_grasp_point()[axis]):+.4f}",
    )
    # 单段行程等于一次抓取的位移，起点是**实测的**自由端。
    travel = float(unroll_wp[-1].position[axis]) - grasp[axis]
    check(
        "一段拉动的位移 = 单段行程",
        abs(travel - layout.stroke_distance()) < 1e-9,
        f"{travel * 1e3:.2f}mm",
    )
    off_plane = max(abs(float(w.position[2]) - grasp[2]) for w in unroll_wp)
    sideways = max(
        abs(float(w.position[1 - axis]) - grasp[1 - axis]) for w in unroll_wp
    )
    check(
        "全程贴着桌面、不侧偏（旋转全部由卷筒绕梁吸收，手腕不动）",
        off_plane < 1e-9 and sideways < 1e-9,
        f"离面 {off_plane * 1e3:.3f}mm，侧偏 {sideways * 1e3:.3f}mm",
    )
    # 原契约是「位移与 unroll 相同、方向相反」，2026-08-25 实测证明它在本场景里
    # 做不到：夹爪推不过夹具，命令送到 y=-0.228 时手停在 -0.053，arm_pos_err 177mm，
    # 布被碾成 11 层并沉入桌面 536 粒子·帧——三种走法里唯一发生穿模的一个。
    # 现契约改为「反方向、走满可用余量、且不撞夹具」。代价是 shove 与 unroll 的位移
    # 不再相等，判据因此可以靠位移把两者分开——这一条在标定门槛时要记着。
    bar_axis_pos = float(layout.bar_centre()[axis])
    room = abs(grasp[axis] - bar_axis_pos) - SHOVE_BAR_CLEARANCE
    reached = float(shove_wp[-1].position[axis])
    check(
        "shove 往反方向走，走满可用余量且停在夹具之外",
        reached < grasp[axis] - 1e-9
        and abs(abs(reached - grasp[axis]) - room) < 1e-9
        and abs(reached - bar_axis_pos) >= SHOVE_BAR_CLEARANCE - 1e-9,
        f"shove {'xy'[axis]}={reached:+.4f}，走了 {abs(reached - grasp[axis]) * 1e3:.1f}mm"
        f"（余量 {room * 1e3:.1f}mm），距梁心 {abs(reached - bar_axis_pos) * 1e3:.1f}mm "
        f">= {SHOVE_BAR_CLEARANCE * 1e3:.1f}mm",
    )
    check(
        "overpull 越过「料已放完」那个点继续走",
        float(over_wp[-1].position[axis]) > float(unroll_wp[-1].position[axis]) + 0.005,
        f"overpull {'xy'[axis]}={float(over_wp[-1].position[axis]):+.4f} vs "
        f"unroll {'xy'[axis]}={float(unroll_wp[-1].position[axis]):+.4f}",
    )
    steps = layout.stroke_steps()
    check(
        "步数由标定速度算出来，不是写死的",
        abs(layout.stroke_distance() / steps - float(cfg["physical"]["pull_step_m"]))
        < 0.1 * float(cfg["physical"]["pull_step_m"]),
        f"每段 {layout.stroke_distance() * 1e3:.1f}mm / {steps} 步 = "
        f"{layout.stroke_distance() / steps * 1e3:.2f}mm/步",
    )
    # 可达性。**手的终点由支架位置、杆高、材料全长、内缩量决定**，圈数与层距只通过
    # 尾端离轴的距离（几毫米）进来：
    #     末位 = 夹具位置 + tail_radius + √((材料全长 − anchor_arc − edge_inset − pull_slack)² − 垂落高²)
    # 所以够不着的时候能动的是这几个，先钉住这条恒等式，免得下次又去调圈数。
    final = layout.final_grasp_point()
    length = float(cloth["material_length"]) - anchor_arc_of(cfg) - float(cfg["grasp"]["edge_inset"]) - slack
    hang = float(dispenser["bar_height"]) - float(cloth["z"])
    predicted = centre[axis] + _geometry.tail_radius(cfg) + float(np.sqrt(length * length - hang * hang))
    check(
        "末位 = 夹具位置 + tail_radius + √((L − pull_slack)² − 垂落高²)",
        abs(float(final[axis]) - predicted) < 1e-9,
        f"{centre[axis]:+.4f} + {_geometry.tail_radius(cfg) * 1e3:.1f}mm + √({length * 1e3:.1f}² − {hang * 1e3:.1f}²) "
        f"= {predicted:+.4f}",
    )
    more_turns = copy.deepcopy(cfg)
    more_turns["cloth"]["roll"]["turns"] = 1.0
    check(
        "圈数从 1.5 改到 1.0，末位只随尾端离轴距离动几毫米（起点动了 70 mm 以上）",
        abs(float(_StandInLayout(more_turns).final_grasp_point()[axis]) - float(final[axis])) < 0.006
        and abs(float(_StandInLayout(more_turns).grasp_point()[axis]) - float(layout.grasp_point()[axis])) > 0.07,
        f"末位差 {(float(_StandInLayout(more_turns).final_grasp_point()[axis]) - float(final[axis])) * 1e3:+.1f}mm，"
        f"起点差 {(float(_StandInLayout(more_turns).grasp_point()[axis]) - float(layout.grasp_point()[axis])) * 1e3:+.1f}mm",
    )
    # 与 1.2 **实测送到**的位置比。这一条现在是提示不是门槛：出厂取值就在实测区间之外，
    # 而唯一能解决这个未知的办法是跑一次读 arm_pos_err_mm —— 让离线闸口把那次跑挡在
    # 门外，就把「还没测」变成了「不许测」。
    gap = float(final[axis]) - MEASURED_REACH_Y
    print(
        f"  [note] 末位 {'xy'[axis]}={float(final[axis]):+.4f}，"
        f"实测送到过 {MEASURED_REACH_Y:+.3f}，"
        + (
            f"**超出 {gap * 1e3:.1f}mm，未经实测**：跑一次看 arm_pos_err_mm 与末态跨度"
            if gap > 0
            else f"余量 {-gap * 1e3:.1f}mm"
        )
        + "（这个数是实测送到的最远处，不是机械臂的极限）"
    )
    # 展开后布带末端要落在作业区里。作业区 x[-0.23,+0.31] / y[-0.30,+0.30]。
    workspace = 0.31 if axis == 0 else 0.30
    band_end = centre[axis] + float(cloth["material_length"])
    check(
        "完全展开后布带末端仍在作业区内",
        band_end < workspace,
        f"末端 {'xy'[axis]}={band_end:+.4f} < {workspace}",
    )

    print("\n== 变体包络（variation 块）==")
    envelope_section(cfg)

    print("\n== 转轴（cloth.spool）==")
    spool_section(cfg)

    print()
    if failures:
        print(f"== 失败 {len(failures)} 项 ==")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("== 通过：两条门槛挡住还卷着与被扯下来，on_bar 把两者分开 ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
