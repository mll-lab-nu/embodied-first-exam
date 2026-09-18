"""Offline gate for the cloth_fold judges (docx 1.1).

Runs the REAL evaluator against the REAL task config on synthetic cloth, so a
threshold edit that stops separating a good fold from a bad one is caught without
a GPU run (a full fold episode is a 4-minute scene build plus the motion).

What it proves:
  - a clean fold passes every gate, and the readings land where the measured run
    put them (two layers everywhere, outline on target, crease on the line);
  - the two wrong executions docx 1.1 names -- bunching the cloth up, and pushing
    it around without lifting -- fail, and fail on the gate that is supposed to
    catch them rather than by accident;
  - **the crease gate earns its place**: a fold that is geometrically perfect but
    put down 12 mm off still fails, while coverage and layer count both pass it.
    That case is why docx lists 折线位置误差 as a separate criterion, and it is
    the one a single area threshold cannot see;
  - the fold target is half the cloth's own outline, not a box around it;
  - the config's thresholds sit between the measured right and wrong answers, so
    each gate has room on both sides rather than clinging to one;
  - **the variation envelope** (2026-09-06): the yaml's five feasibility rows pass
    on the baseline, the derived sheet position restores it, the four corners are
    the four symmetric copies of one geometry, the two control motions are what
    they claim to be, all 96 corners of the envelope pass every row, and three
    deliberately bad layouts are rejected by the row that is there to catch them.

    python tests/check_cloth_fold_geometry.py

Needs numpy + PyYAML only (no hydra, no genesis): the evaluator is plain NumPy
over particle arrays, which is the point of keeping it independent of the scene.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]

# Loaded by path, not by `from topogym.verification... import`: every other
# verifier in that package imports its task module, which imports Genesis, so the
# package __init__ would drag the whole simulator in. This one is deliberately
# plain NumPy, and loading the file directly is what keeps this check runnable
# without a GPU environment.
_spec = importlib.util.spec_from_file_location(
    "cloth_fold_verifier", REPO / "topogym/verification/cloth_fold_verifier.py"
)
_verifier = importlib.util.module_from_spec(_spec)
# Registered before exec: `@dataclass` resolves string annotations through
# `sys.modules[cls.__module__]`, which is absent for a module loaded by path.
sys.modules[_spec.name] = _verifier
_spec.loader.exec_module(_verifier)
ClothFoldEvaluator = _verifier.ClothFoldEvaluator
fold_targets = _verifier.fold_targets
fold_target_cells = _verifier.fold_target_cells
occupied_cells = _verifier.occupied_cells

_tex_spec = importlib.util.spec_from_file_location(
    "topogym_textures", REPO / "topogym/world/textures.py"
)
textures = importlib.util.module_from_spec(_tex_spec)
sys.modules[_tex_spec.name] = textures
_tex_spec.loader.exec_module(textures)

# The layout rules and feasibility rows, numpy only; the task module that wraps
# them imports Genesis, so they are loaded by path like the verifier.
_geo_spec = importlib.util.spec_from_file_location(
    "topogym.tasks_legacy.deformation._cloth_fold_geometry",
    REPO / "topogym/tasks_legacy/deformation/_cloth_fold_geometry.py",
)
_geometry = importlib.util.module_from_spec(_geo_spec)
sys.modules[_geo_spec.name] = _geometry
_geo_spec.loader.exec_module(_geometry)


# `topogym.planning` is NumPy-only, so it imports normally -- the same route
# `check_rope_winding_geometry.py` takes.
sys.path.insert(0, str(REPO))
from topogym.planning.cloth_fold_planner import (  # noqa: E402
    FIXED_CORNER,
    FIXED_FRACTION,
    chord_error,
    execution_layout,
    fold_waypoints,
)


class _StandInLayout:
    """Just enough of `ClothFoldLayout` for the planner, without Genesis.

    Mirrors the real geometry from the same config, so a change to one and not
    the other shows up as this check disagreeing with the demo's own log line.
    """

    def __init__(self, cfg, table_z=0.0):
        self.task_cfg = _Node(cfg)
        self._cfg = cfg
        self._table_z = table_z

    def _offset(self):
        return _geometry.grasp_offset(self._cfg)

    @property
    def corner(self):
        return _geometry.corner_name(self._cfg)

    def with_corner(self, name):
        import copy

        cfg = copy.deepcopy(self._cfg)
        cfg["grasp"]["corner"] = str(name)
        return _StandInLayout(cfg, self._table_z)

    def with_fold_fraction(self, value):
        import copy

        cfg = copy.deepcopy(self._cfg)
        cfg["goal"]["fold_fraction"] = float(value)
        return _StandInLayout(cfg, self._table_z)

    def fold_fraction(self):
        return _geometry.fold_fraction(self._cfg)

    def cloth_centre(self):
        return _geometry.cloth_centre_task(self._cfg)

    def rest_z(self):
        return self._table_z + float(self._cfg["cloth"]["z"])

    def fold_point(self):
        return _geometry.fold_point_task(self._cfg)

    def fold_normal(self):
        return _geometry.fold_normal_task(self._cfg)

    def material_distance(self):
        return _geometry.material_distance(self._cfg)

    def fold_radius(self):
        return self.material_distance() * float(self._cfg["physical"]["fold_slack"])

    def fold_steps(self):
        arc = float(np.pi * self.fold_radius())
        return max(4, int(round(arc / float(self._cfg["physical"]["fold_step_m"]))))

    def grasp_point(self):
        return np.array([*(self.cloth_centre() + self._offset()), self.rest_z()])

    def fold_target(self):
        return np.array([*_geometry.fold_target_task(self._cfg), self.rest_z()])


class _Node(dict):
    """Attribute access, as OmegaConf gives the real layout."""

    def __init__(self, data):
        super().__init__({k: _Node(v) if isinstance(v, dict) else v for k, v in data.items()})

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _sheet_mesh_fn():
    """`cloth_sheet_mesh` lifted out of the task module by source.

    That module imports Genesis at the top, so it cannot be loaded here at all;
    the function itself needs only NumPy and pathlib. Lifting it keeps this check
    running against the REAL generator rather than a copy that could drift.
    """

    import ast

    source = (REPO / "topogym/tasks_legacy/deformation/cloth_fold.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cloth_sheet_mesh"]
    namespace = {"np": np, "Path": Path}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "cloth_fold.py", "exec"), namespace)
    return namespace["cloth_sheet_mesh"]


cloth_sheet_mesh = _sheet_mesh_fn()

TASK_CFG = REPO / "configs/task_configs/cloth_fold_topogym_tabletop_v1.yaml"

TABLE_Z = 0.0
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def rest_sheet(cfg) -> np.ndarray:
    """The cloth as Genesis lays it out: a flat grid one particle-radius up.

    65x65 rather than the config's 33x33 because Genesis subdivides the control
    mesh once -- that is the combination the spike measured as order-preserving,
    and vertex order is what makes the crease measurable at all.
    """

    size = np.asarray(cfg["cloth"]["size"], dtype=float)
    centre = _geometry.cloth_centre_task(cfg)
    side = 2 * int(cfg["cloth"]["mesh"]["cols"]) - 1
    xs = np.linspace(centre[0] - size[0] / 2, centre[0] + size[0] / 2, side)
    ys = np.linspace(centre[1] - size[1] / 2, centre[1] + size[1] / 2, side)
    grid_x, grid_y = np.meshgrid(xs, ys, indexing="ij")
    z = np.full(grid_x.size, TABLE_Z + float(cfg["cloth"]["z"]))
    return np.column_stack([grid_x.ravel(), grid_y.ravel(), z])


def folded(rest: np.ndarray, fold_point, normal, thickness: float) -> np.ndarray:
    """Mirror the lifted half across the fold line and lay it on top."""

    out = rest.copy()
    along = (rest[:, :2] - np.asarray(fold_point, dtype=float)) @ np.asarray(
        normal, dtype=float
    )
    lifted = along > 0.0
    out[lifted, :2] -= 2.0 * along[lifted, None] * np.asarray(normal, dtype=float)
    out[lifted, 2] += thickness
    return out


def crumpled(rest: np.ndarray, seed: int = 0) -> np.ndarray:
    """Gathered into a bunch: pulled in towards the middle, piled up, no order."""

    rng = np.random.default_rng(seed)
    centre = rest[:, :2].mean(axis=0)
    out = rest.copy()
    out[:, :2] = centre + (rest[:, :2] - centre) * 0.45
    out[:, 2] = TABLE_Z + rng.uniform(0.002, 0.030, size=len(rest))
    return out


def dragged(rest: np.ndarray, fold_point, normal, thickness: float) -> np.ndarray:
    """Pushed along without being lifted: the outline moves, the sheet wrinkles.

    Half the material ends up roughly where a fold would put it, but it stays in
    one layer and the surface buckles instead of creasing.
    """

    rng = np.random.default_rng(1)
    out = rest.copy()
    along = (rest[:, :2] - np.asarray(fold_point, dtype=float)) @ np.asarray(
        normal, dtype=float
    )
    pushed = along > 0.0
    out[pushed, :2] -= 1.1 * along[pushed, None] * np.asarray(normal, dtype=float)
    out[:, 2] = TABLE_Z + 0.002 + rng.uniform(0.0, 0.006, size=len(rest))
    return out


def lumped(nodes: np.ndarray, seed: int = 7) -> np.ndarray:
    """A fold that is right nearly everywhere, with one region badly wrong.

    The reason the mean particle distance cannot stand alone: this reads 2.6 mm
    on average, comfortably inside any threshold worth setting, while a twentieth
    of the cloth is 60 mm from where it belongs.
    """

    rng = np.random.default_rng(seed)
    out = nodes.copy()
    picked = rng.choice(len(out), size=int(0.05 * len(out)), replace=False)
    out[picked, :2] += rng.normal(0.0, 0.043, (len(picked), 2))
    return out


def _corner_cfgs(cfg):
    """Every vertex of the yaml's ``variation:`` box, as (label, cfg), not yet derived.

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
    """The sampler's derivation step (`cloth_fold.derive_task_cfg`), on a dict."""

    cfg["cloth"]["center_x"] = _geometry.center_x_from_frac(cfg, float(cfg["cloth"]["center_x_frac"]))


_LOWER_IS_TIGHTER = ("far_corner_reach", "apex_below_workspace_top", "slack_within_gate")


def _margin(row) -> float:
    name, measured, limit, _ = row
    return (limit - measured) if name in _LOWER_IS_TIGHTER else (measured - limit)


def envelope_section(cfg) -> None:
    import copy

    rows = _geometry.cloth_fold_checks(cfg)
    for name, measured, limit, ok in rows:
        print(f"  {name:28s} {measured:+.4f} / {limit:+.4f} {'ok' if ok else 'FAIL'}")
    check("基准 yaml 四行全过", all(ok for *_, ok in rows), ",".join(n for n, *_, ok in rows if not ok))
    # 四行，不是五行：原来的 attach_disc_has_cloth（半边长 − inset ≥ 附着盘半径）随
    # grasp.inset 一起在 2026-09-07 删掉，inset 没了它恒为 0.120 ≥ 0.018，是死行。
    check("四行齐全", [r[0] for r in rows] == [
        "far_corner_reach", "cloth_in_workspace", "apex_below_workspace_top",
        "slack_within_gate",
    ], str([r[0] for r in rows]))

    # The baseline sits at the top of the derived window: the far corner of the
    # shipped layout is 0.7398 from the base, 0.2 mm inside the 0.740 cap.
    base = copy.deepcopy(cfg)
    _derive(base)
    lo, hi = _geometry.center_x_bounds(cfg)
    check(
        "派生还原基准：center_x_frac 1.0 → 窗口顶端 0.0402（基准 0.040 差 0.2 mm）",
        abs(base["cloth"]["center_x"] - hi) < 1e-12 and abs(hi - 0.040) < 0.0005 and abs(lo - 0.010) < 1e-12,
        f"window [{lo:.4f}, {hi:.4f}] -> center_x={base['cloth']['center_x']:.4f}",
    )
    far = _geometry.far_corner_task(base)
    reach = float(np.linalg.norm(far - np.asarray(cfg["reach"]["base_xy"], dtype=float)))
    check(
        "窗口顶端就是远角落在可达盘上的位置（far_corner_reach 构造取等）",
        abs(reach - float(cfg["reach"]["max_hand_dist"])) < 1e-9,
        f"far corner ({far[0]:+.4f}, {far[1]:+.4f}) at {reach:.4f}",
    )

    # Four corners: one geometry, four symmetric copies.
    per_corner = {}
    for name in _geometry.CORNER_SIGNS:
        c = copy.deepcopy(cfg)
        c["grasp"]["corner"] = name
        per_corner[name] = c
    materials = {n: _geometry.material_distance(c) for n, c in per_corner.items()}
    check(
        "四个角的材料长相等（同一块布、同一折痕位置）",
        max(materials.values()) - min(materials.values()) < 1e-12,
        f"{materials['far_left'] * 1e3:.1f} mm",
    )
    centre = _geometry.cloth_centre_task(cfg)
    opposite = (("far_left", "near_right"), ("far_right", "near_left"))
    check(
        "对角两角互为抓取点 / 落点：一个角的落点就是对角的抓取点",
        all(
            np.allclose(_geometry.fold_target_task(per_corner[a]), _geometry.grasp_point_task(per_corner[b]))
            and np.allclose(_geometry.grasp_point_task(per_corner[a]) + _geometry.grasp_point_task(per_corner[b]), 2 * centre)
            for a, b in opposite
        ),
    )
    normals = {n: _StandInLayout(c).fold_normal() for n, c in per_corner.items()}
    check(
        "四个折向是四个对角线方向 (±1, ±1)/√2",
        all(np.allclose(np.abs(v), 1 / np.sqrt(2)) for v in normals.values())
        and all(np.sign(normals[n]).tolist() == list(_geometry.CORNER_SIGNS[n]) for n in normals),
        " ".join(f"{n}=({v[0]:+.2f},{v[1]:+.2f})" for n, v in normals.items()),
    )
    far_side = {n: _geometry.far_corner_task(c)[0] for n, c in per_corner.items()}
    check(
        "不管抓哪个角，远角都在 +x 侧同一个 x 上",
        max(far_side.values()) - min(far_side.values()) < 1e-12 and far_side["far_left"] > centre[0],
        f"x = {far_side['far_left']:+.4f}",
    )

    # The control mesh's diagonal is chosen per corner so the crease crosses
    # the diagonal edges (measured 2026-09-06: along them, the flap lands 30 mm
    # off). Both orientations must be the same vertex grid, or the judges lose
    # their vertex correspondence.
    import tempfile

    diag_ok = True
    for name, c in per_corner.items():
        diag = _geometry.mesh_diagonal(c)
        normal = np.asarray(_geometry.CORNER_SIGNS[name], dtype=float)
        crease_dir = np.array([-normal[1], normal[0]])
        diag_dir = np.array([1.0, 1.0]) if diag == "up" else np.array([-1.0, 1.0])
        diag_ok &= abs(float(crease_dir @ diag_dir)) < 1e-12
    check("四个角各自的网格对角线都与折痕垂直（折痕横穿对角线边）", diag_ok,
          " ".join(f"{n}={_geometry.mesh_diagonal(c)}" for n, c in per_corner.items()))
    with tempfile.TemporaryDirectory() as tmp:
        cols, rows = int(cfg["cloth"]["mesh"]["cols"]), int(cfg["cloth"]["mesh"]["rows"])
        verts = {}
        for diag in ("up", "down"):
            v, f = cloth_sheet_mesh(list(cfg["cloth"]["size"]), centre, TABLE_Z + float(cfg["cloth"]["z"]),
                                    cols, rows, Path(tmp) / f"{diag}.obj", diagonal=diag)
            verts[diag] = (v, f)
        check(
            "两种对角线方向的控制网格顶点完全相同、面数相同（判定器靠顶点顺序）",
            np.array_equal(verts["up"][0], verts["down"][0]) and verts["up"][1].shape == verts["down"][1].shape,
            f"{len(verts['up'][0])} vertices, {len(verts['up'][1])} faces each",
        )

    # Control motions.
    stand_in = _StandInLayout(cfg)
    drag = fold_waypoints(stand_in, motion="drag")
    fold = fold_waypoints(stand_in, motion="fold")
    check(
        "drag 走法：俯视路径与 fold 相同、全程贴桌面、没有一段标为抬起",
        all(abs(w.position[2] - stand_in.rest_z()) < 1e-12 for w in drag)
        and all(np.allclose(a.position[:2], b.position[:2]) for a, b in zip(drag, fold))
        and not any(w.lifted for w in drag)
        and sum(w.steps for w in drag) == sum(w.steps for w in fold),
    )
    for name in ("far_right", "near_left", "near_right"):
        exec_layout = execution_layout(_StandInLayout(per_corner[name]), "fixed_corner")
        check(
            f"fixed_corner 走法：指令 {name} 时仍按 {FIXED_CORNER} 规划，抓取点是基准的",
            exec_layout.corner == FIXED_CORNER
            and np.allclose(exec_layout.grasp_point()[:2], _geometry.grasp_point_task(cfg)),
        )
    # fixed_fold：无视指令的折痕位置，永远角对角折。抓的角不变（那是另一条轴的对照），
    # 变的是落点——指令说折一半时它仍把角送到对角角尖，差了整整半条对角线。
    for value in (0.9, 0.8):
        commanded = copy.deepcopy(cfg)
        commanded["goal"]["fold_fraction"] = value
        told = _StandInLayout(commanded)
        exec_layout = execution_layout(told, "fixed_fold")
        gap = float(np.linalg.norm(exec_layout.fold_target()[:2] - told.fold_target()[:2]))
        check(
            f"fixed_fold 走法：指令折 {value} 时仍按角对角规划，抓的角不变、落点差 {gap * 1e3:.0f} mm",
            exec_layout.fold_fraction() == FIXED_FRACTION
            and exec_layout.corner == told.corner
            and abs(gap - 2.0 * (1.0 - value) * _geometry.material_distance(cfg)) < 1e-12,
        )

    # Corners of the envelope.
    corners = _corner_cfgs(cfg)
    rejected, failed, tight = [], [], {}
    for label, c in corners:
        try:
            _derive(c)
        except ValueError as exc:
            rejected.append(f"{label}: {exc}")
            continue
        rows = _geometry.cloth_fold_checks(c)
        bad = [n for n, *_, ok in rows if not ok]
        if bad:
            failed.append(f"{label}: {bad}")
        for row in rows:
            m = _margin(row)
            if row[0] not in tight or m < tight[row[0]][0]:
                tight[row[0]] = (m, label)
    check("角点数 = 4 角 × 3 折痕档 × 2^3 连续轴 = 96", len(corners) == 96, str(len(corners)))
    check("96 个角点派生区间都非空", not rejected, "; ".join(rejected[:3]))
    check("96 个角点四行全过", not failed, "; ".join(failed[:3]))
    for name, (m, label) in tight.items():
        print(f"  最紧 {name:28s} 余量 {m:+.4f}  @ {label}")
    check(
        "布前后位置的派生把可达行压到 0 而不是负数",
        tight["far_corner_reach"][0] >= -1e-9 and tight["far_corner_reach"][0] < 1e-6,
        f"{tight['far_corner_reach'][0]:+.6f}",
    )
    windows = []
    for _label, c in corners:
        lo, hi = _geometry.center_x_bounds(c)
        windows.append(hi - lo)
    check(
        "96 个角点的 center_x 窗口都 ≥ 0.020（连续轴抖动下限）",
        min(windows) >= 0.020 - 1e-9,
        f"窗口宽 [{min(windows):.4f}, {max(windows):.4f}]",
    )

    # Negative examples: what the rows are for.
    loose = copy.deepcopy(cfg)
    loose["physical"]["fold_slack"] = 0.93
    _derive(loose)
    rows = {r[0]: r for r in _geometry.cloth_fold_checks(loose)}
    check(
        "负例：松紧 0.93 让手停在离对角 11.9 mm，超过 7.5 mm 的平均误差门，被 slack_within_gate 拒",
        not rows["slack_within_gate"][3] and abs(rows["slack_within_gate"][1] - 0.0119) < 0.0002,
        f"{rows['slack_within_gate'][1] * 1e3:.1f} mm > {rows['slack_within_gate'][2] * 1e3:.1f}",
    )
    outer = copy.deepcopy(cfg)
    outer["cloth"]["center_y"] = 0.030
    outer["cloth"]["center_x"] = 0.070
    lo, hi = _geometry.center_x_bounds(outer)
    rows = {r[0]: r for r in _geometry.cloth_fold_checks(outer)}
    check(
        "负例：布最靠外 (0.070, +0.030) 抓远左角，远角离底座 0.775 被可达行拒；派生窗口顶端低于 0.070",
        not rows["far_corner_reach"][3] and hi < 0.070 - 1e-9 and abs(rows["far_corner_reach"][1] - 0.775) < 0.001,
        f"reach {rows['far_corner_reach'][1]:.4f} > {rows['far_corner_reach'][2]:.4f}；窗口 [{lo:.4f}, {hi:.4f}]",
    )
    deep = copy.deepcopy(cfg)
    deep["goal"]["fold_fraction"] = 0.6
    raised = ""
    try:
        _geometry.fold_fraction(deep)
    except ValueError as exc:
        raised = str(exc)
    check(
        "负例：折痕位置 0.6 没有对应的指令措辞，被 fold_fraction 拒（画面无线索，只能由句子说清）",
        "EXTENT_WORDS" in raised or "must be one of" in raised,
        raised[:80],
    )

    # 折痕位置越短，动的材料越少：材料长、弧半径、步数、最高点全部单调下降，而
    # 落点从对角角尖一路走回布中心。这四条是这条轴的定义，钉住它们。
    short = copy.deepcopy(cfg)
    walked = []
    for value in (1.0, 0.9, 0.8):
        short["goal"]["fold_fraction"] = value
        _derive(short)
        walked.append(
            (
                _geometry.material_distance(short),
                _geometry.fold_radius(short),
                _geometry.apex_height(short),
                _geometry.fold_target_task(short),
                _geometry.fold_point_task(short),
            )
        )
    centre = _geometry.cloth_centre_task(short)
    check(
        "折痕位置 1.0 / 0.9 / 0.8：材料长、弧半径、最高点逐档下降",
        all(a[i] > b[i] for a, b in zip(walked, walked[1:]) for i in (0, 1, 2)),
        " ".join(f"{w[0] * 1e3:.1f}mm" for w in walked),
    )
    # 镜像公式 落点 = 中心 + (1 − 2f)·offset 的两个整齐取值，钉住它：
    # f = 1.0 落在对角角尖（离中心一整个 L），f = 0.75 落在中心与对角角尖的正中间。
    check(
        "折痕位置 1.0 落点是对角角尖，0.8 落点离中心 0.6 倍 L",
        abs(float(np.linalg.norm(walked[0][3] - centre)) - walked[0][0]) < 1e-12
        and abs(float(np.linalg.norm(walked[2][3] - centre)) - 0.6 * walked[0][0]) < 1e-9,
        f"离中心 {float(np.linalg.norm(walked[0][3] - centre)) * 1e3:.1f} / "
        f"{float(np.linalg.norm(walked[2][3] - centre)) * 1e3:.1f} mm",
    )


def main(argv=None) -> int:
    cfg = yaml.safe_load(TASK_CFG.read_text(encoding="utf-8"))
    evaluator = ClothFoldEvaluator.from_config(cfg)
    limits = evaluator.thresholds

    rest = rest_sheet(cfg)
    centre = _geometry.cloth_centre_task(cfg)
    # docx 1.1: grasp the middle of the right edge and take it to the far side,
    # so the fold line is the cloth's centre line and the normal points +x.
    fold_point = centre
    normal = np.array([1.0, 0.0])
    thickness = float(cfg["cloth"]["particle_size"])
    cell = evaluator.cell

    print(f"config: {TASK_CFG.relative_to(REPO)}")
    print(
        f"cloth {cfg['cloth']['size']} particles={len(rest)} cell_mm={cell * 1e3:.1f} "
        f"fold_line x={fold_point[0]:+.3f}"
    )

    print("\n目标 footprint 是布自己轮廓的一半，不是外接矩形")
    target = fold_target_cells(rest, fold_point, normal, cell)
    whole = occupied_cells(rest, cell)
    ratio = len(target) / len(whole)
    check(
        "target is half the rest outline",
        0.45 <= ratio <= 0.55,
        f"{len(target)}/{len(whole)} cells = {ratio:.3f}",
    )

    cases = {
        "perfect": folded(rest, fold_point, normal, thickness),
        "unfolded": rest.copy(),
        "crumpled": crumpled(rest),
        "dragged": dragged(rest, fold_point, normal, thickness),
        # Geometrically a clean fold, but the whole sheet ended up 12 mm off.
        "slid": folded(rest, fold_point, normal, thickness) + np.array([0.012, 0.0, 0.0]),
        # 95% of the sheet perfect, 5% balled up. The case that decides whether
        # the companion to the mean is the right shape of measure.
        "lumped": lumped(folded(rest, fold_point, normal, thickness)),
    }
    states = {}
    print("\n六种终态的读数")
    for name, nodes in cases.items():
        state = evaluator.classify(
            rest, nodes, table_z=TABLE_Z, fold_point=fold_point, fold_normal=normal
        )
        states[name] = state
        print(f"  {name:9s} {state.summary()}")

    print("\n判定")
    check("a clean fold passes", states["perfect"].is_terminal)
    for name in ("unfolded", "crumpled", "dragged", "slid", "lumped"):
        check(f"{name} is rejected", not states[name].is_terminal)

    print("\n每种错法是被该管它的那一条拦住的")
    check(
        "crumpling is caught by the layer count as well as by distance",
        not states["crumpled"].gates["two_layer_frac"],
        f"two_layer_frac={states['crumpled'].two_layer_frac:.3f} "
        f"< {limits.two_layer_frac_min}",
    )
    check(
        "dragging is caught by the layer count as well as by distance",
        not states["dragged"].gates["two_layer_frac"],
        f"two_layer_frac={states['dragged'].two_layer_frac:.3f}",
    )
    # Putting the targets in world coordinates is what makes this work: the
    # pairwise form SoftGym uses is blind to a bodily shift and needs a separate
    # displacement penalty to see it.
    slid = states["slid"]
    check(
        "a fold put down in the wrong place is caught by distance alone",
        not slid.gates["particle_error_mean"]
        and slid.gates["two_layer_frac"]
        and slid.gates["particle_off_target_frac"],
        f"mean={slid.particle_error_mean * 1e3:.1f}mm over the "
        f"{limits.particle_error_mean_max * 1e3:.1f}mm limit, while "
        f"two_layer_frac={slid.two_layer_frac:.3f} and "
        f"off_target_frac={slid.particle_off_target_frac:.3f} both pass",
    )
    # The demoted readings still say WHICH failure it was, which is why they are
    # still computed.
    check(
        "the demoted readings still identify the failure mode",
        states["crumpled"].max_layers > 3
        and slid.crease_offset > 0.01
        and states["unfolded"].fold_iou < 0.55,
        f"crumpled stacks {states['crumpled'].max_layers} deep; "
        f"slid's crease is {slid.crease_offset * 1e3:.1f}mm off; "
        f"unfolded covers the wrong outline (IoU {states['unfolded'].fold_iou:.3f})",
    )

    print("\n读数落在该落的地方")
    good = states["perfect"]
    check(
        "a clean fold puts two layers over essentially all of its footprint",
        good.two_layer_frac >= 0.95,
        f"two_layer_frac={good.two_layer_frac:.3f}",
    )
    check(
        "a clean fold lands on the target outline",
        good.fold_iou >= 0.95,
        f"fold_iou={good.fold_iou:.3f}",
    )
    check(
        "a clean fold's crease sits on the fold line and is straight",
        good.crease_offset < 1e-4 and good.crease_straightness < 1e-4,
        f"offset={good.crease_offset * 1e3:.3f}mm "
        f"straightness={good.crease_straightness * 1e3:.3f}mm",
    )
    check(
        "the half that stays put is measured as not having moved",
        good.anchor_shift < 1e-6,
        f"anchor_shift={good.anchor_shift * 1e3:.3f}mm",
    )
    check(
        "the displaced fold's crease offset reads the displacement",
        abs(slid.crease_offset - 0.012) < 1e-4,
        f"{slid.crease_offset * 1e3:.2f}mm for a 12.00mm shift",
    )

    print("\n没有一条判据是多余的")
    # Not "every gate rejects every wrong answer" -- they are a conjunction
    # precisely because each one sees a different failure. `dragged` puts the
    # outline almost exactly on target (fold_iou 0.94) and is caught only by the
    # layer count; `slid` stacks two clean layers and is caught only by the
    # crease. What has to hold is that no gate is dead weight.
    wrong = ("unfolded", "crumpled", "dragged", "slid", "lumped")
    for gate in good.gates:
        decisive = [name for name in wrong if not states[name].gates[gate]]
        check(
            f"{gate} is the deciding judge for at least one wrong answer",
            bool(decisive),
            f"catches {', '.join(decisive) if decisive else 'nothing'}",
        )
    for name in wrong:
        rejecting = [g for g, ok in states[name].gates.items() if not ok]
        check(
            f"{name} is rejected on a stated criterion",
            bool(rejecting),
            f"fails {', '.join(rejecting)}",
        )

    print("\n层数是真的在数层，不是「有没有断层」")
    # The reading that makes bunching separable at all: a fold is two layers deep
    # everywhere, a pile is many. Counting "is there a gap" instead would score
    # the pile as two-layered, which is docx 1.1's first named shortcut.
    check(
        "a fold is exactly two deep, a pile is deeper",
        good.max_layers == 2 and states["crumpled"].max_layers > 3,
        f"perfect={good.max_layers} crumpled={states['crumpled'].max_layers} "
        f"unfolded={states['unfolded'].max_layers}",
    )
    check(
        "a flat sheet is one deep",
        states["unfolded"].max_layers == 1,
    )
    check(
        "bunching shows up as cells stacked more than two deep",
        states["crumpled"].over_layer_cells > 0.8 * states["crumpled"].covered_cells
        and good.over_layer_cells == 0,
        f"crumpled {states['crumpled'].over_layer_cells}/"
        f"{states['crumpled'].covered_cells} cells, perfect {good.over_layer_cells}",
    )

    print("\n手走的弧线是由材料定死的，不是选出来的")
    layout = _StandInLayout(cfg)
    points = np.array([w.position for w in fold_waypoints(layout)])
    centre, normal = layout.fold_point(), layout.fold_normal()
    radius = layout.fold_radius()
    # Every waypoint the same length of material from the fold line: that is what
    # "the corner can only travel on a circle" means, and both ways of getting it
    # wrong were measured in 2026-08-19 (over-reach stretches the sheet, under-
    # reach lets it sag and be towed).
    along = (points[:, :2] - centre) @ normal
    spans = np.linalg.norm(np.column_stack([along, points[:, 2] - layout.rest_z()]), axis=1)
    check(
        "every waypoint is the same distance from the fold line",
        float(np.abs(spans - radius).max()) < 1e-9,
        f"radius {radius * 1e3:.1f}mm, worst deviation "
        f"{float(np.abs(spans - radius).max()) * 1e6:.3f}um",
    )
    # It stops short by exactly the slack held back from taut, not by some
    # tolerance that happens to fit -- so this stays true if the sheet or the
    # grasp point changes.
    gap = float(np.linalg.norm(points[-1][:2] - layout.fold_target()[:2]))
    expected = layout.material_distance() * (1.0 - float(cfg["physical"]["fold_slack"]))
    check(
        "the arc ends on the opposite corner, short by exactly the slack",
        abs(gap - expected) < 1e-9,
        f"{gap * 1e3:.2f}mm short, and {float(cfg['physical']['fold_slack']):.2f} slack "
        f"on {layout.material_distance() * 1e3:.1f}mm of material predicts "
        f"{expected * 1e3:.2f}mm",
    )
    check(
        "it goes over the top, not around the side",
        float(points[:, 2].max() - layout.rest_z()) > 0.9 * radius,
        f"apex {float(points[:, 2].max() - layout.rest_z()) * 1e3:.1f}mm of a "
        f"{radius * 1e3:.1f}mm radius",
    )
    # The primitive drives straight lines between waypoints, so the segments have
    # to be short enough that the chords hug the circle.
    error = chord_error(layout)
    check(
        "straight segments stay within a particle of the arc",
        error < float(cfg["cloth"]["particle_size"]),
        f"worst chord error {error * 1e3:.2f}mm vs a "
        f"{float(cfg['cloth']['particle_size']) * 1e3:.1f}mm particle",
    )
    total = sum(int(w.steps) for w in fold_waypoints(layout))
    check(
        "the segments add up to the calibrated speed",
        abs(np.pi * radius / total - float(cfg["physical"]["fold_step_m"])) < 2e-4,
        f"{total} steps over {np.pi * radius * 1e3:.0f}mm = "
        f"{np.pi * radius / total * 1e3:.2f}mm a step, asked for "
        f"{float(cfg['physical']['fold_step_m']) * 1e3:.2f}",
    )

    print("\n布面有 UV，贴图才有地方可贴")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / "sheet.obj"
        cols, rows = int(cfg["cloth"]["mesh"]["cols"]), int(cfg["cloth"]["mesh"]["rows"])
        verts, _faces = cloth_sheet_mesh(
            list(cfg["cloth"]["size"]), centre, TABLE_Z + float(cfg["cloth"]["z"]),
            cols, rows, obj,
        )
        lines = obj.read_text(encoding="utf-8").splitlines()
        v_lines = [l for l in lines if l.startswith("v ")]
        vt_lines = [l for l in lines if l.startswith("vt ")]
        f_lines = [l for l in lines if l.startswith("f ")]
        # Genesis' rasterizer keeps diffuse colour and texture and nothing else,
        # so a missing UV is a missing surface -- there is no second channel.
        check(
            "every vertex carries a texture coordinate",
            len(vt_lines) == len(v_lines) == cols * rows,
            f"{len(v_lines)} vertices, {len(vt_lines)} uvs",
        )
        uv = np.array([[float(x) for x in l.split()[1:3]] for l in vt_lines])
        check(
            "the uvs cover the sheet exactly once, no tiling",
            float(uv.min()) == 0.0 and float(uv.max()) == 1.0,
            f"u,v in [{uv.min():.3f}, {uv.max():.3f}] -- one image covers it, so "
            f"nothing depends on how the sampler wraps",
        )
        check(
            "faces reference the uvs",
            all("/" in token for line in f_lines for token in line.split()[1:]),
            f"{len(f_lines)} faces in v/vt form",
        )

    print("\n织纹是画出来的，不是纯色")
    if True:
        tex_cfg = cfg["cloth"]["texture"]
        kwargs = dict(
            color=cfg["cloth"]["color"],
            size_m=cfg["cloth"]["size"],
            thread_pitch_m=float(tex_cfg["thread_pitch"]),
            pixels_per_thread=int(tex_cfg["pixels_per_thread"]),
            thread_shading=float(tex_cfg["thread_shading"]),
            weft_tint=float(tex_cfg["weft_tint"]),
            fibre_noise=float(tex_cfg["fibre_noise"]),
            cloud_noise=float(tex_cfg["cloud_noise"]),
            seed=int(tex_cfg["seed"]),
        )
        first = textures.fabric_weave(**kwargs)
        again = textures.fabric_weave(**kwargs)
        check(
            "the same parameters give the same image, byte for byte",
            first.tobytes() == again.tobytes(),
            "so a run is reproducible from config alone",
        )
        # The renderer asserts exactly this dtype before it will use the image.
        check(
            "the image is uint8",
            first.dtype == np.uint8,
            f"{first.dtype} -- genesis asserts uint8 in surface_uvs_to_trimesh_visual",
        )
        pixels = first.astype(float) / 255.0
        threads = int(round(float(cfg["cloth"]["size"][0]) / float(tex_cfg["thread_pitch"])))
        check(
            "the weave is at the physical scale the config asks for",
            pixels.shape[0] == threads * int(tex_cfg["pixels_per_thread"]),
            f"{threads} threads across {cfg['cloth']['size'][0] * 1e3:.0f}mm, "
            f"{pixels.shape[0]}px image",
        )
        # A flat colour reads 0 here, and a flat colour is what made the cloth
        # look like a slab of clay.
        spread = float(pixels.mean(axis=2).std())
        check(
            "the surface is not one flat colour",
            spread > 0.02,
            f"brightness spread {spread:.3f} across the sheet",
        )

    print("\n四个角的颜色：指令里那个词，就是画面上那个角涂的颜色")
    if True:
        import copy

        tex_cfg = cfg["cloth"]["texture"]
        palette = cfg["cloth"]["palette"]
        paint = cfg["cloth"]["corner_paint"]
        painted = {name: str(value) for name, value in paint.items()}
        check(
            "四个角涂四种不同的颜色",
            len(set(painted.values())) == 4,
            f"{painted} —— 两个角同色的话，「红色那个角」就指向两处",
        )
        check(
            "涂的每种颜色都在调色板里",
            all(value in palette for value in painted.values()),
            f"palette={sorted(palette)}",
        )
        image = textures.fabric_weave(
            color=cfg["cloth"]["color"],
            size_m=cfg["cloth"]["size"],
            pattern=str(tex_cfg["pattern"]),
            accent_color=tex_cfg["accent_color"],
            stripe_pitch_m=float(tex_cfg["stripe_pitch"]),
            corner_colors=_geometry.corner_colour_grid(cfg),
            corner_size_m=float(tex_cfg["corner_size"]),
            thread_pitch_m=float(tex_cfg["thread_pitch"]),
            pixels_per_thread=int(tex_cfg["pixels_per_thread"]),
            thread_shading=float(tex_cfg["thread_shading"]),
            weft_tint=float(tex_cfg["weft_tint"]),
            fibre_noise=float(tex_cfg["fibre_noise"]),
            cloud_noise=float(tex_cfg["cloud_noise"]),
            seed=int(tex_cfg["seed"]),
        )
        height, width = image.shape[0], image.shape[1]
        # 一步走完整条链：grasp.corner -> 角尖的 uv -> 贴图像素 -> 颜色 -> 指令里的词。
        # uv 落到哪个像素按渲染链的规则算：v 是从图像下缘往上读的
        # （trimesh 的 uv_to_color：y = (1 - v) * (height - 1)），这一条只有渲染截图
        # 能最终确认，见 docs/develop/tasks/cloth_fold_zh.md。
        for name, (sign_x, sign_y) in _geometry.CORNER_SIGNS.items():
            view = copy.deepcopy(cfg)
            view["grasp"]["corner"] = name
            word = _geometry.corner_colour_name(view)
            # 往色块里侧挪四分之一块，采样点不落在接缝上。
            inset = 0.25 * float(tex_cfg["corner_size"]) / float(cfg["cloth"]["size"][0])
            u = 0.5 * (sign_x + 1.0) - (inset if sign_x > 0 else -inset)
            v = 0.5 * (sign_y + 1.0) - (inset if sign_y > 0 else -inset)
            column = int(round(u * (width - 1)))
            row = int(round((1.0 - v) * (height - 1)))
            sampled = image[row, column].astype(float) / 255.0
            wanted = np.asarray([float(c) for c in palette[word]], dtype=float)
            # 织纹的明暗是逐像素的一个标量倍数，方向不变，所以比方向不比亮度。
            cosine = float(
                sampled @ wanted
                / (float(np.linalg.norm(sampled)) * float(np.linalg.norm(wanted)) + 1e-12)
            )
            check(
                f"抓 {name} 时指令说 {word}，布上那个角就涂着 {word}",
                cosine > 0.99,
                f"uv=({u:.3f}, {v:.3f}) -> 像素 {np.round(sampled, 3).tolist()}，"
                f"调色板 {np.round(wanted, 3).tolist()}，方向余弦 {cosine:.4f}",
            )
        # 反过来：随便换一个排列，指令里的词必须跟着换。
        view = copy.deepcopy(cfg)
        rotated = {
            "far_left": painted["far_right"],
            "far_right": painted["near_right"],
            "near_left": painted["far_left"],
            "near_right": painted["near_left"],
        }
        view["cloth"]["corner_paint"] = rotated
        check(
            "换一个颜色排列，同一个角的指令词跟着换",
            _geometry.corner_colour_name(view) != _geometry.corner_colour_name(cfg),
            f"{cfg['grasp']['corner']}：{_geometry.corner_colour_name(cfg)} -> "
            f"{_geometry.corner_colour_name(view)}",
        )

    print("\n== 变体包络（variation 块）==")
    envelope_section(cfg)

    print()
    if failures:
        print(f"== 失败 {len(failures)} 项 ==")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("== 通过：主判据与结构判据合起来挡住全部五种错法 ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
