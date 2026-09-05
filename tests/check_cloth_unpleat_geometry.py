"""Offline gate for the cloth_unpleat judges (docx 1.2).

Runs the REAL evaluator against the REAL task config on synthetic cloth, so a
threshold edit that stops separating a good unfold from a bad one is caught
without a GPU run.

What it proves:
  - a band spread flat passes every gate;
  - the pleat as built fails, which is the floor the task starts from;
  - **the shortcut docx 1.2 names fails on the gates that are supposed to catch
    it.** Pressing the pleat flat is rejected by the layer count and the length,
    which is also the real starting state: the pleat lies down within 25 steps
    and no material parameter prevents it (measured 2026-08-23), so the height
    criterion is recorded rather than gated and this check pins that down;
  - an over-pulled band passes all three, and `band_shift` is what tells it
    apart. That is recorded rather than gated on purpose, and this check exists
    so the fact stays visible;
  - the profile's own arithmetic closes: the material the pleat stores is exactly
    the difference between its length and its plan span, which is what makes the
    spread ratio a conservation law rather than a tuned number;
  - the pull travels exactly the material the pleat stores, stays in the plane
    (friction on the far half is the anchor, and lifting removes it), and its
    `shove` and `overpull` motions really are the motions their names claim;
  - **the variation envelope (2026-09-05)**: the seven feasibility rows of
    `_cloth_unpleat_geometry.cloth_unpleat_checks` pass on the shipped yaml, the
    two derivations reproduce the shipped `edge_inset` and `center_y`, every
    corner of the yaml's `variation:` block (three pleat widths x two pull sides
    x two ends of five continuous axes = 192) passes all seven rows, the mirror
    layout reads the same rows and puts the grasp and the pull's end at the
    negated coordinate, and three infeasible layouts are rejected.

    python tests/check_cloth_unpleat_geometry.py

Needs numpy + PyYAML only (no hydra, no genesis): the evaluator is plain NumPy
over particle arrays, which is the point of keeping it independent of the scene.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
TASK_CFG = REPO / "configs/task_configs/cloth_unpleat_topogym_tabletop_v1.yaml"


# Stand-in packages, so a module can be loaded by path and still resolve the
# `topogym.*` imports it makes in production. Giving each stub the real directory
# as its `__path__` lets submodules import normally while the packages' own
# `__init__` files -- which pull in Genesis by way of the task modules -- never
# run. `check_cloth_fold_geometry.py` gets away without this only because its
# verifier imports nothing from the repo at all.
for _package in ("topogym", "topogym.verification", "topogym.tasks", "topogym.tasks.deformation"):
    if _package not in sys.modules:
        _stub = types.ModuleType(_package)
        _stub.__path__ = [str(REPO / _package.replace(".", "/"))]
        sys.modules[_package] = _stub


def _load(name: str, relative: str):
    """Load a module by path, registered under its real dotted name.

    Registered in `sys.modules` before exec for two reasons: `@dataclass`
    resolves string annotations through it, and the modules import each other by
    dotted name.
    """

    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_load(
    "topogym.verification.cloth_fold_verifier",
    "topogym/verification/cloth_fold_verifier.py",
)
_verifier = _load(
    "topogym.verification.cloth_unpleat_verifier",
    "topogym/verification/cloth_unpleat_verifier.py",
)
_mesh = _load(
    "topogym.tasks.deformation.cloth_profile_mesh",
    "topogym/tasks/deformation/cloth_profile_mesh.py",
)
_geometry = _load(
    "topogym.tasks.deformation._cloth_unpleat_geometry",
    "topogym/tasks/deformation/_cloth_unpleat_geometry.py",
)

ClothUnpleatEvaluator = _verifier.ClothUnpleatEvaluator
band_shift = _verifier.band_shift

# `topogym.planning` is NumPy-only, so it imports normally.
sys.path.insert(0, str(REPO))
from topogym.planning.cloth_unpleat_planner import pull_waypoints  # noqa: E402

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


class _StandInLayout:
    """Just enough of `ClothUnpleatLayout` for the planner, without Genesis.

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
        self.sweep_axis = 1 - self.material_axis
        self._corners = _mesh.pleat_profile(
            material_length=float(cloth["material_length"]),
            pleat_width=float(cloth["pleat"]["width"]),
            crest_height=float(cloth["pleat"]["crest_height"]),
            rest_z=float(cloth["z"]),
        )
        self._marks = _mesh.pleat_landmarks(self._corners)
        self._centre = np.array([float(cloth["center_x"]), float(cloth["center_y"])])
        self.pull_sign = _geometry.pull_sign(cfg)

    @property
    def table_z(self) -> float:
        return self._table_z

    def landmarks(self) -> dict:
        return self._marks

    def rest_z(self) -> float:
        return self._table_z + float(self._cfg["cloth"]["z"])

    def _plan_point(self, material: float, height: float) -> np.ndarray:
        point = np.zeros(3)
        point[self.material_axis] = self._centre[self.material_axis] + float(material)
        point[self.sweep_axis] = self._centre[self.sweep_axis]
        point[2] = self._table_z + float(height)
        return point

    def design_grasp_point(self) -> np.ndarray:
        end = 0.5 * self._marks["plan_span"] - float(self._cfg["grasp"]["edge_inset"])
        return self._plan_point(self.pull_sign * end, float(self._cfg["cloth"]["z"]))

    def grasp_point(self) -> np.ndarray:
        return self.design_grasp_point()

    def pull_direction(self) -> np.ndarray:
        direction = np.zeros(3)
        direction[self.material_axis] = self.pull_sign
        return direction

    def pull_distance(self) -> float:
        return float(self._marks["stored"]) * float(self._cfg["physical"]["pull_scale"])

    def pull_steps(self) -> int:
        return max(
            4,
            int(round(self.pull_distance() / float(self._cfg["physical"]["pull_step_m"]))),
        )


def arc_of(points) -> np.ndarray:
    """Cumulative arc length at each sample of a polyline."""

    points = np.asarray(points, dtype=float)
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(steps)])


def profile_at(polyline, arcs) -> np.ndarray:
    """Where each material point sits once the band takes shape ``polyline``.

    This is what keeps the synthetic cases index-aligned with the rest state:
    every case is the SAME particles in another configuration, which is what the
    evaluator is written for. Building each case by resampling its own polyline
    instead would hand the judge two unrelated point sets and quietly break the
    material-tracking readings.
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
    judges bin onto an 8 mm grid and a 7.5 mm control mesh would leave gaps in it
    -- the layer count would then read empty cells as uncovered and flatter the
    single-layer fraction.
    """

    cloth = cfg["cloth"]
    step = float(cloth["particle_size"])
    width = float(cloth["width"])
    offsets = np.arange(-0.5 * width, 0.5 * width + 1e-9, step)
    centre = np.array([float(cloth["center_x"]), float(cloth["center_y"])])
    material = 0 if str(cloth["material_axis"]).lower() == "x" else 1
    sweep = 1 - material
    section = np.asarray(section, dtype=float)
    out = np.zeros((len(offsets) * len(section), 3))
    index = 0
    for offset in offsets:
        for point in section:
            out[index, material] = centre[material] + point[0]
            out[index, sweep] = centre[sweep] + offset
            out[index, 2] = table_z + point[1]
            index += 1
    return out


def flat_polyline(cfg, corners, *, shift: float = 0.0) -> np.ndarray:
    """The band after a successful unfold: one straight run, full length.

    Anchored at the pleated band's own far end rather than centred, because that
    end is the part table friction holds still -- the unfold grows the band
    forward from it. ``shift`` tows the whole thing, which is the over-pull.
    """

    rest = float(cfg["cloth"]["z"])
    start = float(corners[0][0]) + shift
    return np.array(
        [[start, rest], [start + float(cfg["cloth"]["material_length"]), rest]]
    )


def pressed_polyline(cfg, corners) -> np.ndarray:
    """The pleat pushed flat: three layers stacked, plan span barely changed.

    docx 1.2's shortcut. The two arms keep the lengths they had -- pressing a
    pleat does not consume material -- they just lie down, one layer above the
    other. The tail then comes back to the table over its own length.
    """

    rest = float(cfg["cloth"]["z"])
    gap = float(cfg["cloth"]["particle_size"])
    arc = arc_of(corners)
    arm_up = float(arc[2] - arc[1])
    arm_down = float(arc[3] - arc[2])
    tail = float(arc[4] - arc[3])
    back_x = -arm_up
    forward_x = back_x + arm_down
    # The tail is the same length it was; lying down over a two-particle drop
    # costs it a little of its horizontal reach.
    tail_x = float(np.sqrt(max(tail**2 - (2.0 * gap) ** 2, 0.0)))
    return np.array(
        [
            [float(corners[0][0]), rest],
            [0.0, rest],
            [back_x, rest + gap],
            [forward_x, rest + 2.0 * gap],
            [forward_x + tail_x, rest],
        ]
    )


def _corner_cfgs(cfg):
    """Every vertex of the yaml's ``variation:`` box, derived, as (label, cfg).

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
    """The sampler's derivation step (`cloth_unpleat.derive_task_cfg`), on a dict."""

    cfg["grasp"]["edge_inset"] = _geometry.edge_inset_from_frac(cfg, float(cfg["grasp"]["edge_inset_frac"]))
    leaf = _geometry.along_leaf(cfg)
    cfg["cloth"][leaf] = _geometry.center_along_from_frac(cfg, float(cfg["cloth"][f"{leaf}_frac"]))


_LOWER_IS_TIGHTER = ("hand_reach", "pull_within_stroke", "start_still_stored")


def _margin(row) -> float:
    name, measured, limit, _ = row
    return (limit - measured) if name in _LOWER_IS_TIGHTER else (measured - limit)


def envelope_section(cfg) -> None:
    import copy

    rows = _geometry.cloth_unpleat_checks(cfg)
    for name, measured, limit, ok in rows:
        print(f"  {name:28s} {measured:+.4f} / {limit:+.4f} {'ok' if ok else 'FAIL'}")
    check("基准 yaml 七行全过", all(ok for *_, ok in rows), ",".join(n for n, *_, ok in rows if not ok))
    check("七行齐全", [r[0] for r in rows] == [
        "pleat_fits_band", "crest_above_underlayer", "grasp_clears_three_layers",
        "band_in_workspace", "hand_reach", "pull_within_stroke", "start_still_stored",
    ], str([r[0] for r in rows]))

    base = copy.deepcopy(cfg)
    _derive(base)
    check(
        "派生还原基准：edge_inset_frac 0.4 → 0.012，center_y_frac 0.5 → 0.000",
        abs(base["grasp"]["edge_inset"] - 0.012) < 1e-9 and abs(base["cloth"]["center_y"]) < 1e-9,
        f"inset={base['grasp']['edge_inset']:.4f} center_y={base['cloth']['center_y']:+.4f}",
    )
    lo, hi = _geometry.edge_inset_bounds(cfg)
    check("基准褶几何下内缩量区间是 [0.008, 0.018]（净空不封顶）", abs(lo - 0.008) < 1e-9 and abs(hi - 0.018) < 1e-9, f"[{lo:.4f}, {hi:.4f}]")
    lo, hi = _geometry.center_along_bounds(cfg)
    check("基准下纵向位置区间是 ±0.030（可达与工作区不封顶）", abs(lo + 0.030) < 1e-9 and abs(hi - 0.030) < 1e-9, f"[{lo:+.4f}, {hi:+.4f}]")

    # Mirror layout: same rows, negated grasp and pull end.
    mirror = copy.deepcopy(cfg)
    mirror["cloth"]["pull_side"] = -1
    _derive(mirror)
    plus_rows, minus_rows = _geometry.cloth_unpleat_checks(base), _geometry.cloth_unpleat_checks(mirror)
    check(
        "镜像布局（pull_side −1）七行读数与 +1 逐行相等",
        all(abs(a[1] - b[1]) < 1e-12 and abs(a[2] - b[2]) < 1e-12 for a, b in zip(plus_rows, minus_rows)),
    )
    gp, gm = _geometry.grasp_point_task(base), _geometry.grasp_point_task(mirror)
    ep, em = _geometry.pull_end_task(base), _geometry.pull_end_task(mirror)
    check(
        "镜像布局的抓取点与拉动终点是 +1 的 y 取反",
        abs(gp[0] - gm[0]) < 1e-12 and abs(gp[1] + gm[1]) < 1e-12 and abs(ep[1] + em[1]) < 1e-12,
        f"+1 grasp y {gp[1]:+.4f} end y {ep[1]:+.4f}; −1 grasp y {gm[1]:+.4f} end y {em[1]:+.4f}",
    )
    stand_in = _StandInLayout(mirror)
    check(
        "镜像布局的规划器沿 −y 拉",
        float(pull_waypoints(stand_in, motion="unfold")[-1].position[1]) < stand_in.grasp_point()[1],
    )

    # Corners.
    corners = _corner_cfgs(cfg)
    rejected, failed, tight = [], [], {}
    for label, c in corners:
        try:
            _derive(c)
        except ValueError as exc:
            rejected.append(f"{label}: {exc}")
            continue
        rows = _geometry.cloth_unpleat_checks(c)
        bad = [n for n, *_, ok in rows if not ok]
        if bad:
            failed.append(f"{label}: {bad}")
        for row in rows:
            m = _margin(row)
            if row[0] not in tight or m < tight[row[0]][0]:
                tight[row[0]] = (m, label)
    check(f"角点数 = 3 × 2 × 2^5 = 192", len(corners) == 192, str(len(corners)))
    check("192 个角点派生区间都非空", not rejected, "; ".join(rejected[:3]))
    check("192 个角点七行全过", not failed, "; ".join(failed[:3]))
    for name, (m, label) in tight.items():
        print(f"  最紧 {name:28s} 余量 {m:+.4f}  @ {label}")
    check(
        "内缩量与纵向位置的派生把两条最紧的行压到 0 而不是负数",
        tight["grasp_clears_three_layers"][0] >= -1e-9 and tight["hand_reach"][0] >= -1e-9,
    )

    # Negative examples: what the rows are for.
    wide = copy.deepcopy(cfg)
    wide["cloth"]["pleat"]["width"] = 0.040
    wide["cloth"]["pleat"]["crest_height"] = 0.028
    wide["grasp"]["edge_inset_frac"] = 1.0
    try:
        _derive(wide)
        wide_ok = _geometry.edge_inset_bounds(wide)[1] < 0.018 - 1e-9
        detail = f"inset window top {_geometry.edge_inset_bounds(wide)[1]:.4f} < 0.018"
    except ValueError as exc:
        wide_ok, detail = True, str(exc)[:80]
    check("负例：褶宽 0.040 + 顶缘 0.028 把内缩量窗口压到 0.018 以下（0.035 是上限的原因）", wide_ok, detail)

    far = copy.deepcopy(cfg)
    far["cloth"]["pleat"]["width"] = 0.035
    far["cloth"]["pleat"]["crest_height"] = 0.028
    far["physical"]["pull_scale"] = 1.12
    far["cloth"]["center_x"] = 0.070
    far["grasp"]["edge_inset_frac"] = 0.0
    _derive(far)
    lo, hi = _geometry.center_along_bounds(far)
    far["cloth"]["center_y"] = 0.030
    rows = {r[0]: r for r in _geometry.cloth_unpleat_checks(far)}
    check(
        "负例：最长行程 + 布带最靠外时纵向 +0.030 被可达行拒，派生窗口上端低于 +0.030",
        not rows["hand_reach"][3] and hi < 0.030 - 1e-9,
        f"hand_reach {rows['hand_reach'][1]:.4f} > {rows['hand_reach'][2]:.4f}；窗口 [{lo:+.4f}, {hi:+.4f}]",
    )

    low = copy.deepcopy(cfg)
    low["cloth"]["pleat"]["crest_height"] = 0.003
    _derive(low)
    rows = {r[0]: r for r in _geometry.cloth_unpleat_checks(low)}
    check("负例：顶缘 3 mm 低于一个粒子，被 crest_above_underlayer 拒", not rows["crest_above_underlayer"][3])


def main(argv=None) -> int:
    cfg = yaml.safe_load(TASK_CFG.read_text(encoding="utf-8"))
    evaluator = ClothUnpleatEvaluator.from_config(cfg)
    limits = evaluator.thresholds
    cloth = cfg["cloth"]

    corners = _mesh.pleat_profile(
        material_length=float(cloth["material_length"]),
        pleat_width=float(cloth["pleat"]["width"]),
        crest_height=float(cloth["pleat"]["crest_height"]),
        rest_z=float(cloth["z"]),
    )
    marks = _mesh.pleat_landmarks(corners)

    print("\n== 褶皱几何：材料守恒 ==")
    check(
        "剖面长度等于配置的材料全长",
        abs(marks["material_length"] - float(cloth["material_length"])) < 1e-9,
        f"{marks['material_length'] * 1e3:.2f}mm",
    )
    check(
        "收在褶皱里的材料 = 全长 − 俯视跨度",
        abs(
            marks["stored"] - (marks["material_length"] - marks["plan_span"])
        ) < 1e-12,
        f"stored={marks['stored'] * 1e3:.1f}mm span={marks['plan_span'] * 1e3:.1f}mm",
    )
    check(
        "上折臂的材料长度 = sqrt(宽² + 高²)",
        abs(
            marks["arm_length"]
            - np.hypot(float(cloth["pleat"]["width"]), float(cloth["pleat"]["crest_height"]))
        ) < 1e-12,
        f"{marks['arm_length'] * 1e3:.2f}mm",
    )
    # The crest-height and three-layer-clearance rows moved into
    # `cloth_unpleat_checks` on 2026-09-05 (`crest_above_underlayer`,
    # `grasp_clears_three_layers`); the envelope section below runs them on the
    # shipped yaml and on every corner.
    check(
        "高度窗口已关闭（端头只有一层，不需要它）",
        cfg["grasp"]["attach_z_band"] is None,
        f"attach_z_band={cfg['grasp']['attach_z_band']}",
    )

    print("\n== 判据：三种末态 ==")
    # One set of material points, four configurations of it. `arcs` is where each
    # point sits along the material, which is the only thing that does not change.
    section = _mesh.resample_polyline(corners, float(cloth["particle_size"]))
    arcs = arc_of(section)
    rest_nodes = band_nodes(section, cfg)
    cases = {
        "unfold（正确）": band_nodes(profile_at(flat_polyline(cfg, corners), arcs), cfg),
        # 这一档同时是两样东西：docx 点名的捷径，以及**真实的起始状态**。
        # 实测褶皱放手 25 步内就躺平成这个三层叠合的形状（2026-08-23）。
        "press（压塌／也就是真实起始态）": band_nodes(
            profile_at(pressed_polyline(cfg, corners), arcs), cfg
        ),
        # t=0 的建模形状。仿真里它只存在 25 步，留着是为了确认判据对它也不放行。
        "nothing（t=0 建模形状）": rest_nodes,
        "overpull（展平但整条带被拖走）": band_nodes(
            profile_at(flat_polyline(cfg, corners, shift=0.08), arcs), cfg
        ),
    }
    states = {}
    for label, nodes in cases.items():
        state = evaluator.classify(rest_nodes, nodes, table_z=0.0)
        states[label] = state
        print(
            f"  {label:30s} peak={state.peak_above_table * 1e3:6.2f}mm "
            f"single={state.single_layer_frac:.3f} "
            f"recovered={state.recovered_frac:+.3f} "
            f"shift={state.band_shift * 1e3:6.2f}mm "
            f"terminal={state.is_terminal}"
        )

    check(
        "铺平的布带两条门槛全过",
        states["unfold（正确）"].is_terminal,
        states["unfold（正确）"].summary(),
    )
    check(
        "t=0 的建模形状不算完成",
        not states["nothing（t=0 建模形状）"].is_terminal,
        f"gates={[k for k, v in states['nothing（t=0 建模形状）'].gates.items() if not v]}",
    )

    pressed = states["press（压塌／也就是真实起始态）"]
    check(
        "压塌不算完成",
        not pressed.is_terminal,
        f"gates={[k for k, v in pressed.gates.items() if not v]}",
    )
    # The load-bearing one. docx 1.2 asks for a judge under which a pleat that is
    # still holding its material and one that has given it back are strictly
    # separable, and names WHICH readings do that work.
    check(
        "压塌被层数与材料守恒一起挡住",
        not pressed.gates["single_layer_frac"] and not pressed.gates["recovered_frac"],
        f"single={pressed.single_layer_frac:.3f} < {limits.single_layer_frac_min} 且 "
        f"recovered={pressed.recovered_frac:+.3f} < {limits.recovered_frac_min}",
    )
    # 高度这条判据 2026-08-23 降为诊断量：这块布立不住（bending_compliance 是死
    # 参数），褶皱放手 25 步内躺平，起始状态本身就已经通过任何一条合理的高度门槛。
    # 一条永远满足的判据看起来像标准却不起作用，比没有更糟。
    check(
        "高度不在门槛里，只记录",
        limits.max_height_m is None and "max_height" not in pressed.gates,
        f"max_height_m={limits.max_height_m}，门槛={sorted(pressed.gates)}",
    )
    check(
        "高度读数仍然出现在 to_info 里（降级不等于删掉）",
        "peak_above_table_mm" in pressed.to_info(),
        f"peak_above_table_mm={pressed.to_info()['peak_above_table_mm']:.2f}",
    )
    # 类别合同 C1 (task_taxonomy_zh.md 4.1) 要求结构指标与形态指标的合取，
    # 禁止单一位置阈值。降为两条之后这一点仍然成立，所以要钉住。
    check(
        "两条门槛一个结构（层数）一个形态（长度），仍是合取",
        sorted(pressed.gates) == ["recovered_frac", "single_layer_frac"],
        f"门槛={sorted(pressed.gates)}",
    )

    over = states["overpull（展平但整条带被拖走）"]
    check(
        "拉过头两条门槛也全过（它是另一种走法，不是失败）",
        over.is_terminal,
        f"recovered={over.recovered_frac:+.3f}",
    )
    check(
        "band_shift 是唯一分得出拉过头的读数",
        over.band_shift > states["unfold（正确）"].band_shift + 0.02,
        f"overpull {over.band_shift * 1e3:.1f}mm vs "
        f"unfold {states['unfold（正确）'].band_shift * 1e3:.1f}mm",
    )

    print("\n== 阈值两侧的余量 ==")
    good, worst = states["unfold（正确）"], pressed
    for name, value_good, value_bad, limit, direction in (
        (
            "single_layer_frac",
            good.single_layer_frac,
            worst.single_layer_frac,
            limits.single_layer_frac_min,
            "min",
        ),
        (
            "recovered_frac",
            good.recovered_frac,
            worst.recovered_frac,
            limits.recovered_frac_min,
            "min",
        ),
    ):
        ok = (
            value_good >= limit > value_bad
            if direction == "min"
            else value_good <= limit < value_bad
        )
        check(
            f"{name} 的阈值卡在正确与压塌之间",
            ok,
            f"正确 {value_good:.3f} / 阈值 {limit:.3f} / 压塌 {value_bad:.3f}",
        )

    print("\n== 条纹与折痕 ==")
    # docx 1.2 的画面要读出「收在褶皱里的材料被放出来」。折痕沿布带的宽度方向走，
    # 所以条纹必须沿材料方向排、被折痕横着切断；平行的话褶皱只是把两条之间的材料
    # 藏起来，展开前后几乎看不出差别。这一条钉住的是**两个必须同时成立的约定**：
    # 网格把宽度放在 v 轴，贴图沿 v 分带。
    with tempfile.TemporaryDirectory() as tmp:
        mesh_path = Path(tmp) / "band.obj"
        section = _mesh.resample_polyline(corners, float(cloth["mesh"]["spacing"]))
        _vertices, _faces, cols, rows = _mesh.sweep_profile_mesh(
            section,
            width=float(cloth["width"]),
            spacing=float(cloth["mesh"]["spacing"]),
            centre=np.array([float(cloth["center_x"]), float(cloth["center_y"])]),
            table_z=0.0,
            path=mesh_path,
            material_axis=0 if str(cloth["material_axis"]).lower() == "x" else 1,
        )
        uvs = np.array(
            [
                [float(v) for v in line.split()[1:3]]
                for line in mesh_path.read_text(encoding="utf-8").splitlines()
                if line.startswith("vt ")
            ]
        )
    grid = uvs.reshape(rows, cols, 2)
    check(
        "贴图的条带轴（v）落在布带的宽度上",
        float(np.abs(np.diff(grid[..., 1], axis=1)).max()) < 1e-9
        and float(np.abs(np.diff(grid[..., 1], axis=0)).min()) > 0.0,
        f"v 沿材料方向恒定、沿宽度从 {grid[0, 0, 1]:.2f} 到 {grid[-1, 0, 1]:.2f}",
    )
    check(
        "u 跟着材料走（褶皱处贴图不会挤成一团）",
        float(np.abs(np.diff(grid[..., 0], axis=0)).max()) < 1e-9
        and float(np.diff(grid[0, :, 0]).min()) > 0.0,
        f"u 沿宽度恒定、沿材料从 {grid[0, 0, 0]:.2f} 到 {grid[0, -1, 0]:.2f}",
    )
    # 贴图那一侧：fabric_weave 按 size_m[1] 分带，所以宽度必须排第二。
    size_m = _mesh.texture_size_m(
        float(cloth["material_length"]), float(cloth["width"])
    )
    check(
        "texture_size_m 把宽度放在第二位（与 v 轴对齐）",
        abs(size_m[1] - float(cloth["width"])) < 1e-12,
        f"size_m={size_m}",
    )
    stripes = float(cloth["width"]) / float(cloth["texture"]["stripe_pitch"])
    check(
        "被折痕切断的条纹不止两三条",
        stripes >= 5.0,
        f"宽 {float(cloth['width']) * 1e3:.0f}mm / 间距 "
        f"{float(cloth['texture']['stripe_pitch']) * 1e3:.0f}mm = {stripes:.0f} 条",
    )

    print("\n== 轨迹 ==")
    layout = _StandInLayout(cfg)
    axis = layout.material_axis
    grasp = layout.grasp_point()
    unfold_wp = pull_waypoints(layout, motion="unfold")
    shove_wp = pull_waypoints(layout, motion="shove")
    over_wp = pull_waypoints(layout, motion="overpull", overpull_scale=1.6)

    # 行程不是调出来的：另一端不动的话，端头走的距离恰好等于褶皱收着的材料量。
    travel = float(unfold_wp[-1].position[axis]) - grasp[axis]
    expected = marks["stored"] * float(cfg["physical"]["pull_scale"])
    check(
        "拉的距离 = 褶皱收着的材料量（× pull_scale）",
        abs(travel - expected) < 1e-9,
        f"{travel * 1e3:.2f}mm，收料 {marks['stored'] * 1e3:.1f}mm × "
        f"{float(cfg['physical']['pull_scale'])}",
    )
    # 整个动作在平面内：靠的是桌面摩擦按住另一端，抬起来就没有摩擦了。
    off_plane = max(
        abs(float(w.position[2]) - grasp[2]) for w in unfold_wp
    )
    sideways = max(
        abs(float(w.position[1 - axis]) - grasp[1 - axis]) for w in unfold_wp
    )
    check(
        "全程贴着桌面、不侧偏（摩擦才按得住另一端）",
        off_plane < 1e-9 and sideways < 1e-9,
        f"离面 {off_plane * 1e3:.3f}mm，侧偏 {sideways * 1e3:.3f}mm",
    )
    check(
        "shove 往反方向走（同样多的位移，做错的动作）",
        float(shove_wp[-1].position[axis]) < grasp[axis] - 1e-9
        and abs(
            abs(float(shove_wp[-1].position[axis]) - grasp[axis]) - abs(travel)
        ) < 1e-9,
        f"shove {'xy'[axis]}={float(shove_wp[-1].position[axis]):+.4f} vs "
        f"起点 {grasp[axis]:+.4f}",
    )
    check(
        "overpull 越过「料已放完」那个点继续走",
        float(over_wp[-1].position[axis]) > float(unfold_wp[-1].position[axis]) + 0.005,
        f"overpull {'xy'[axis]}={float(over_wp[-1].position[axis]):+.4f} vs "
        f"unfold {'xy'[axis]}={float(unfold_wp[-1].position[axis]):+.4f}",
    )
    steps = layout.pull_steps()
    check(
        "步数由标定速度算出来，不是写死的",
        abs(layout.pull_distance() / steps - float(cfg["physical"]["pull_step_m"]))
        < 0.1 * float(cfg["physical"]["pull_step_m"]),
        f"行程 {layout.pull_distance() * 1e3:.1f}mm / {steps} 步 = "
        f"{layout.pull_distance() / steps * 1e3:.2f}mm/步",
    )
    # 抓取点必须整个附着盘都落在布上，否则一半悬空、抓到的粒子两侧不等。
    edge = 0.5 * marks["plan_span"]
    inset = float(cfg["grasp"]["edge_inset"])
    check(
        "整个附着盘落在布上（抓取点离边缘够远）",
        inset >= float(cloth["particle_size"]) * 2.0,
        f"内缩 {inset * 1e3:.1f}mm ≥ 2 倍粒径 "
        f"{float(cloth['particle_size']) * 2.0 * 1e3:.1f}mm",
    )
    check(
        "抓的是端头附近，不是布带中段",
        edge - inset > 0.4 * marks["plan_span"],
        f"抓在 {'xy'[axis]}={grasp[axis]:+.4f}，端头在 "
        f"{float(layout._centre[axis] + edge):+.4f}",
    )
    # 拉完之后端头要还够得着。作业区 x[-0.23,+0.31] / y[-0.30,+0.30]。
    limit = 0.31 if axis == 0 else 0.30
    check(
        "拉到底之后仍在作业区内",
        float(over_wp[-1].position[axis]) < limit,
        f"overpull 终点 {float(over_wp[-1].position[axis]):+.4f} < {limit}",
    )

    print("\n== 变体包络（variation 块）==")
    envelope_section(cfg)

    print()
    if failures:
        print(f"== 失败 {len(failures)} 项 ==")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("== 通过：两条门槛（层数 + 材料守恒）把压塌与建模形状都挡在外面 ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
