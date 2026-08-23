"""Offline gate for the cloth_unpleat judges (docx 1.2).

Runs the REAL evaluator against the REAL task config on synthetic cloth, so a
threshold edit that stops separating a good unfold from a bad one is caught
without a GPU run.

What it proves:
  - a band spread flat passes every gate;
  - the pleat as built fails, which is the floor the task starts from;
  - **the shortcut docx 1.2 names fails on the gates that are supposed to catch
    it.** Pressing the pleat flat is meant to PASS the height gate and be
    rejected by the layer count and the length -- if it ever fails on height
    instead, the three-way conjunction has stopped meaning what docx asked for;
  - an over-pulled band passes all three, and `band_shift` is what tells it
    apart. That is recorded rather than gated on purpose, and this check exists
    so the fact stays visible;
  - the profile's own arithmetic closes: the material the pleat stores is exactly
    the difference between its length and its plan span, which is what makes the
    spread ratio a conservation law rather than a tuned number;
  - the planner's chords hug the arc, and its `press` and `overpull` motions
    really are the motions their names claim.

    python tests/check_cloth_unpleat_geometry.py

Needs numpy + PyYAML only (no hydra, no genesis): the evaluator is plain NumPy
over particle arrays, which is the point of keeping it independent of the scene.
"""

from __future__ import annotations

import importlib.util
import sys
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

ClothUnpleatEvaluator = _verifier.ClothUnpleatEvaluator
band_shift = _verifier.band_shift

# `topogym.planning` is NumPy-only, so it imports normally.
sys.path.insert(0, str(REPO))
from topogym.planning.cloth_unpleat_planner import (  # noqa: E402
    chord_error,
    drag_waypoints,
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
        self._corners = _mesh.pleat_profile(
            material_length=float(cloth["material_length"]),
            pleat_width=float(cloth["pleat"]["width"]),
            crest_height=float(cloth["pleat"]["crest_height"]),
            rest_z=float(cloth["z"]),
        )
        self._marks = _mesh.pleat_landmarks(self._corners)
        self._centre = np.asarray(cloth["center"], dtype=float)

    @property
    def table_z(self) -> float:
        return self._table_z

    def landmarks(self) -> dict:
        return self._marks

    def rest_z(self) -> float:
        return self._table_z + float(self._cfg["cloth"]["z"])

    def crest_point(self) -> np.ndarray:
        return np.array(
            [
                self._centre[0] + self._marks["crest_x"],
                self._centre[1],
                self._table_z + self._marks["crest_z"],
            ]
        )

    def crease_point(self) -> np.ndarray:
        return np.array(
            [self._centre[0] + self._marks["crease_x"], self._centre[1], self.rest_z()]
        )

    def arm_length(self) -> float:
        return float(self._marks["arm_length"])

    def arc_radius(self) -> float:
        return self.arm_length() * float(self._cfg["physical"]["arc_slack"])

    def start_radius(self) -> float:
        crest, crease = self.crest_point(), self.crease_point()
        return float(np.hypot(crest[0] - crease[0], crest[2] - crease[2]))

    def start_angle(self) -> float:
        crest, crease = self.crest_point(), self.crease_point()
        return float(np.arctan2(crest[2] - crease[2], crest[0] - crease[0]))

    def arc_length(self) -> float:
        return float(
            0.5 * (self.start_radius() + self.arc_radius()) * abs(self.start_angle())
        )

    def drag_steps(self) -> int:
        return max(
            4,
            int(round(self.arc_length() / float(self._cfg["physical"]["drag_step_m"]))),
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
    ys = np.arange(-0.5 * width, 0.5 * width + 1e-9, step)
    centre = np.asarray(cloth["center"], dtype=float)
    return np.array(
        [
            [centre[0] + point[0], centre[1] + y, table_z + point[1]]
            for y in ys
            for point in np.asarray(section, dtype=float)
        ]
    )


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
        "顶缘绕下折痕的半径就是那条折臂的长度",
        abs(
            marks["arm_length"]
            - np.hypot(float(cloth["pleat"]["width"]), float(cloth["pleat"]["crest_height"]))
        ) < 1e-12,
        f"{marks['arm_length'] * 1e3:.2f}mm",
    )
    # How far the crest is above the material directly beneath it at birth. Closer
    # than a particle and PBD opens the episode by resolving a collision instead
    # of by holding still.
    clearance = min(
        abs(corners[2][1] - corners[1][1]),
        abs(corners[2][1] - corners[0][1]),
    )
    check(
        "顶缘与其正下方材料的高差不小于一个粒子",
        clearance >= float(cloth["particle_size"]),
        f"{clearance * 1e3:.1f}mm vs particle {float(cloth['particle_size']) * 1e3:.1f}mm",
    )
    # The window the gripper attaches through has to stay clear of that flat run
    # even after the crest sags to the collapse threshold, which is why the layout
    # caps it against the crest's height rather than using the config value flat.
    kept = float(cfg["grasp"]["min_crest_kept"])
    floor = kept * float(cloth["pleat"]["crest_height"]) * (1.0 - 0.45)
    check(
        "顶缘沉到 min_crest_kept 时抓取窗口底部仍高于平铺段",
        floor > float(cloth["particle_size"]) / 2.0,
        f"窗口底 {floor * 1e3:.2f}mm > 半个粒子 "
        f"{float(cloth['particle_size']) / 2.0 * 1e3:.1f}mm",
    )

    print("\n== 判据：三种末态 ==")
    # One set of material points, four configurations of it. `arcs` is where each
    # point sits along the material, which is the only thing that does not change.
    section = _mesh.resample_polyline(corners, float(cloth["particle_size"]))
    arcs = arc_of(section)
    rest_nodes = band_nodes(section, cfg)
    cases = {
        "unfold（正确）": band_nodes(profile_at(flat_polyline(cfg, corners), arcs), cfg),
        "press（压塌，docx 点名的捷径）": band_nodes(
            profile_at(pressed_polyline(cfg, corners), arcs), cfg
        ),
        "nothing（褶皱原样立着）": rest_nodes,
        "overpull（展平但整条带被拖走）": band_nodes(
            profile_at(flat_polyline(cfg, corners, shift=0.08), arcs), cfg
        ),
    }
    states = {}
    for label, nodes in cases.items():
        state = evaluator.classify(rest_nodes, nodes, table_z=0.0)
        states[label] = state
        print(
            f"  {label:34s} peak={state.peak_above_table * 1e3:6.2f}mm "
            f"single={state.single_layer_frac:.3f} "
            f"spread={state.spread_ratio:.3f} "
            f"shift={state.band_shift * 1e3:6.2f}mm "
            f"terminal={state.is_terminal}"
        )

    check(
        "铺平的布带三条判据全过",
        states["unfold（正确）"].is_terminal,
        states["unfold（正确）"].summary(),
    )
    check(
        "褶皱原样立着不算完成",
        not states["nothing（褶皱原样立着）"].is_terminal,
        f"gates={[k for k, v in states['nothing（褶皱原样立着）'].gates.items() if not v]}",
    )

    pressed = states["press（压塌，docx 点名的捷径）"]
    check(
        "压塌不算完成",
        not pressed.is_terminal,
        f"gates={[k for k, v in pressed.gates.items() if not v]}",
    )
    # The load-bearing one. docx 1.2 asks for a judge under which pressing and
    # unfolding are strictly separable, and names WHICH readings do the work.
    check(
        "压塌通过高度这一条（所以它不是靠高度被挡住的）",
        pressed.gates["max_height"],
        f"peak={pressed.peak_above_table * 1e3:.2f}mm ≤ {limits.max_height_m * 1e3:.1f}mm",
    )
    check(
        "压塌被层数与长度守恒一起挡住",
        not pressed.gates["single_layer_frac"] and not pressed.gates["spread_ratio"],
        f"single={pressed.single_layer_frac:.3f} < {limits.single_layer_frac_min} 且 "
        f"spread={pressed.spread_ratio:.3f} < {limits.spread_ratio_min}",
    )

    over = states["overpull（展平但整条带被拖走）"]
    check(
        "拉过头三条判据也全过（它是另一种走法，不是失败）",
        over.is_terminal,
        f"spread={over.spread_ratio:.3f}",
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
            "spread_ratio",
            good.spread_ratio,
            worst.spread_ratio,
            limits.spread_ratio_min,
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

    print("\n== 轨迹 ==")
    layout = _StandInLayout(cfg)
    error = chord_error(layout)
    check(
        "分段直线与弧线的最大偏差远小于一个粒子",
        error < 0.25 * float(cloth["particle_size"]),
        f"{error * 1e3:.3f}mm vs particle {float(cloth['particle_size']) * 1e3:.1f}mm",
    )
    unfold_wp = drag_waypoints(layout, motion="unfold")
    crease = layout.crease_point()
    ends_flat = abs(float(unfold_wp[-1].position[2]) - layout.rest_z()) < 1e-6
    check(
        "unfold 的终点落在桌面高度上",
        ends_flat,
        f"z={float(unfold_wp[-1].position[2]) * 1e3:.2f}mm",
    )
    radii = [
        float(
            np.hypot(
                float(w.position[0]) - crease[0],
                float(w.position[2]) - layout.rest_z(),
            )
        )
        for w in unfold_wp
    ]
    # The invariant is not "constant radius" any more: the sweep opens the radius
    # out from where the crest actually is to the taut value, because an authored
    # pleat sags before the arm reaches it. What must never happen is the hand
    # commanding further from the crease than the arm of cloth reaches.
    arm = layout.arm_length()
    check(
        "unfold 全程不超出那条折臂的材料长度（不会把布拽直）",
        max(radii) <= arm + 1e-9,
        f"最远 {max(radii) * 1e3:.2f}mm ≤ 折臂 {arm * 1e3:.2f}mm",
    )
    check(
        "半径从顶缘当前位置单调开到绷紧值",
        all(b >= a - 1e-12 for a, b in zip(radii, radii[1:]))
        or all(b <= a + 1e-12 for a, b in zip(radii, radii[1:])),
        f"{radii[0] * 1e3:.2f}mm → {radii[-1] * 1e3:.2f}mm "
        f"(taut {layout.arc_radius() * 1e3:.2f}mm)",
    )
    press_wp = drag_waypoints(layout, motion="press")
    crest = layout.crest_point()
    check(
        "press 只往下走、x 不动",
        all(abs(float(w.position[0]) - crest[0]) < 1e-12 for w in press_wp)
        and float(press_wp[-1].position[2]) < float(press_wp[0].position[2]),
        f"x={crest[0]:+.4f} z {float(press_wp[0].position[2]) * 1e3:.1f}"
        f"→{float(press_wp[-1].position[2]) * 1e3:.1f}mm",
    )
    over_wp = drag_waypoints(layout, motion="overpull", overpull_scale=1.6)
    check(
        "overpull 越过平铺位置继续走",
        float(over_wp[-1].position[0]) > float(unfold_wp[-1].position[0]) + 0.005,
        f"overpull x={float(over_wp[-1].position[0]):+.4f} vs "
        f"unfold x={float(unfold_wp[-1].position[0]):+.4f}",
    )
    steps = layout.drag_steps()
    check(
        "步数由标定速度算出来，不是写死的",
        abs(layout.arc_length() / steps - float(cfg["physical"]["drag_step_m"]))
        < 0.1 * float(cfg["physical"]["drag_step_m"]),
        f"arc={layout.arc_length() * 1e3:.1f}mm / {steps} 步 = "
        f"{layout.arc_length() / steps * 1e3:.2f}mm/步",
    )

    print()
    if failures:
        print(f"== 失败 {len(failures)} 项 ==")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("== 通过：三条判据合起来把压塌与原样立着都挡在外面 ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
