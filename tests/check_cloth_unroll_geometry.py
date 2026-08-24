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
  - an over-pulled band passes both, which is a different execution rather than a
    failure, and `out_of_plane` and `on_bar` are what a reader looks at to see it;
  - the spiral's own arithmetic closes: the material the roll stores is exactly
    the difference between its length and its plan span, and the wound part is
    exactly what the pull has to pay out;
  - the layer spacing and the bar clearance are both at least a particle, which is
    what keeps PBD from opening the episode by resolving a collision (1.2's
    measured lesson, cloth against cloth; here it is also cloth against a rigid);
  - the strokes divide the travel evenly, stay in the plane, end inside the reach
    envelope 1.2 measured, and the `shove` and `overpull` motions really are the
    motions their names claim.

    python tests/check_cloth_unroll_geometry.py

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
TASK_CFG = REPO / "configs/task_configs/cloth_unroll_topogym_tabletop_v1.yaml"

#: How far along y the arm was MEASURED delivering a pull on `cloth_unpleat`
#: (2026-08-23: commanded end reached with an 8.6 mm residual). Not a limit the
#: robot config states -- it is an observation, and it is the only reach number
#: on this tabletop that has been measured rather than assumed, which is why the
#: stroke arithmetic is checked against it.
MEASURED_REACH_Y = 0.152


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
from topogym.planning.cloth_unroll_planner import stroke_waypoints  # noqa: E402

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
        self._centre = np.asarray(cloth["center"], dtype=float)

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
        point[self.material_axis] = self._centre[self.material_axis] + float(material)
        point[self.bar_axis] = self._centre[self.bar_axis]
        point[2] = self._table_z + float(height)
        return point

    def grasp_point(self) -> np.ndarray:
        end = self._marks["free_end_s"] - float(self._cfg["grasp"]["edge_inset"])
        return self._plan_point(end, float(self._cfg["cloth"]["z"]))

    def pull_direction(self) -> np.ndarray:
        direction = np.zeros(3)
        direction[self.material_axis] = 1.0
        return direction

    def rolled_length(self) -> float:
        return float(self._marks["rolled"])

    def pull_total(self) -> float:
        return self.rolled_length() * float(self._cfg["physical"]["pull_scale"])

    def stroke_count(self) -> int:
        return max(
            1,
            int(np.ceil(self.pull_total() / float(self._cfg["physical"]["stroke_m"]))),
        )

    def stroke_distance(self) -> float:
        return self.pull_total() / self.stroke_count()

    def final_grasp_point(self) -> np.ndarray:
        return self.grasp_point() + self.pull_direction() * self.pull_total()

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
    centre = np.asarray(cloth["center"], dtype=float)
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


def main(argv=None) -> int:
    cfg = yaml.safe_load(TASK_CFG.read_text(encoding="utf-8"))
    evaluator = ClothUnrollEvaluator.from_config(cfg)
    limits = evaluator.thresholds
    cloth, dispenser = cfg["cloth"], cfg["dispenser"]
    axis = 0 if str(cloth["material_axis"]).lower() == "x" else 1
    centre = np.asarray(cloth["center"], dtype=float)

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
    cases = {
        "unroll（正确）": band_nodes(profile_at(flat_polyline(cfg), arcs), cfg),
        # t=0 的建模形状，也是仿真的起始状态：卷筒还挂在梁上。
        "rolled（起始态／还卷着）": rest_nodes,
        "torn_off（整卷被扯下来）": band_nodes(
            profile_at(torn_off_polyline(cfg, profile), arcs), cfg
        ),
        "overpull（展平但整条带被拖走）": band_nodes(
            profile_at(flat_polyline(cfg, shift=0.05), arcs), cfg
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
            f"out_of_plane={state.out_of_plane * 1e3:5.2f}mm "
            f"terminal={state.is_terminal}"
        )

    good = states["unroll（正确）"]
    rolled = states["rolled（起始态／还卷着）"]
    torn = states["torn_off（整卷被扯下来）"]
    over = states["overpull（展平但整条带被拖走）"]

    check("铺平的布带两条门槛全过", good.is_terminal, good.summary())
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
        "完全展开之后梁上不剩布",
        good.on_bar == 0,
        f"on_bar={good.on_bar}",
    )
    check(
        "拉过头两条门槛也全过（它是另一种走法，不是失败）",
        over.is_terminal,
        f"recovered={over.recovered_frac:+.3f} on_bar={over.on_bar}",
    )
    # 离面厚度顶替 docx 的「累计转角」：重网格化不保顶点顺序，沿带长排序做不出来。
    check(
        "离面厚度分得开「摊平」与「还卷着」",
        rolled.out_of_plane > good.out_of_plane * 3.0,
        f"卷着 {rolled.out_of_plane * 1e3:.2f}mm vs 摊平 "
        f"{good.out_of_plane * 1e3:.2f}mm",
    )
    check(
        "累计转角的替代读数只记录不判定",
        limits.out_of_plane_max is None and "out_of_plane" not in good.gates,
        f"out_of_plane_max={limits.out_of_plane_max}，门槛={sorted(good.gates)}",
    )
    check(
        "on_bar 也只记录不判定（等实测再决定升不升格）",
        limits.on_bar_max is None and "on_bar" not in good.gates,
        f"on_bar_max={limits.on_bar_max}",
    )
    # 类别合同 C1 (task_taxonomy_zh.md 4.1)：结构指标与形态指标的合取，
    # 禁止单一位置阈值。
    check(
        "两条门槛一个结构（层数）一个形态（长度），是合取",
        sorted(good.gates) == ["recovered_frac", "single_layer_frac"],
        f"门槛={sorted(good.gates)}",
    )
    check(
        "band_shift 不在读数里（本场景没有「不该动的那半段布」）",
        "band_shift_mm" not in good.to_info(),
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

    print("\n== 轨迹：多次抓取 ==")
    layout = _StandInLayout(cfg)
    grasp = layout.grasp_point()
    strokes = layout.stroke_count()
    unroll_wp = stroke_waypoints(layout, motion="unroll")
    shove_wp = stroke_waypoints(layout, motion="shove")
    over_wp = stroke_waypoints(layout, motion="overpull", overpull_scale=1.6)

    # 总行程不是调出来的：梁按住不动的话，端头走的距离恰好等于卷筒收着的材料量。
    check(
        "总行程 = 卷筒收着的材料量（× pull_scale）",
        abs(layout.pull_total() - marks["rolled"] * float(cfg["physical"]["pull_scale"]))
        < 1e-12,
        f"{layout.pull_total() * 1e3:.1f}mm，卷料 {marks['rolled'] * 1e3:.1f}mm × "
        f"{float(cfg['physical']['pull_scale'])}",
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
        "一次抓取拉不完，确实需要多段",
        strokes > 1,
        f"{strokes} 段",
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
    check(
        "shove 往反方向走（同样多的位移，做错的动作）",
        float(shove_wp[-1].position[axis]) < grasp[axis] - 1e-9
        and abs(abs(float(shove_wp[-1].position[axis]) - grasp[axis]) - abs(travel))
        < 1e-9,
        f"shove {'xy'[axis]}={float(shove_wp[-1].position[axis]):+.4f} vs "
        f"起点 {grasp[axis]:+.4f}",
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
    # 可达性。这一条是本任务与 1.2 最实在的差别：行程被圈数锁死，够不着就只能改
    # 场景而不是改参数。比的是 1.2 **实测送到**的位置，不是作业区的名义边界。
    final = layout.final_grasp_point()
    check(
        "拉完之后夹爪仍在实测到位的区间内",
        axis == 1 and float(final[axis]) <= MEASURED_REACH_Y,
        f"末位 {'xy'[axis]}={float(final[axis]):+.4f} ≤ 实测 {MEASURED_REACH_Y:+.3f}",
    )
    # 展开后布带末端要落在作业区里。作业区 x[-0.23,+0.31] / y[-0.30,+0.30]。
    workspace = 0.31 if axis == 0 else 0.30
    band_end = centre[axis] + float(cloth["material_length"])
    check(
        "完全展开后布带末端仍在作业区内",
        band_end < workspace,
        f"末端 {'xy'[axis]}={band_end:+.4f} < {workspace}",
    )

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
