"""Does Genesis' runtime weld constraint do what docx 4.4 needs?

DIAGNOSTIC TOOL, not a task. `docs/develop/tasks/rigid_first_track_zh.md` §4.3
gives docx 4.4 (`linkbar_merge_components`) two requirements that both rest on
one API the repo has never used:

- **The latch.** "到位后由固定约束锁定" -- the connecting beam, once its end pin is
  inside a socket, is held there by a constraint rather than by contact. The
  existing `primitives/connector_latch.py` writes a pose every step instead, which
  cannot transmit a pull from one body to another.
- **The lift test.** §4.4 of `../framework/task_taxonomy_zh.md` names 提起测试 as
  this task's physical recheck. It only means anything if the latch is a real
  constraint: a kinematically pinned handle would follow the pin whatever the
  rest of the scene did.

`genesis.engine.solvers.rigid.rigid_solver.RigidSolver` has
`add_weld_constraint(link1_idx, link2_idx)`, `delete_weld_constraint(...)` and
`get_weld_constraints()` (1.2.1, `rigid_solver.py:3205-3213`). Nothing under
`topogym/` calls any of them, so four facts are unmeasured, and each one is a
different part of 4.4:

1. `get_weld_constraints()` reads the live constraint set back -- the verifier's
   union-find runs on exactly this, so the edge has to be legible after the fact.
2. A weld to a link that never moves holds (beam welded to socket A2, which sits
   on the world-fixed component A).
3. A weld between two movable links transmits a pull (beam welded to socket B1 on
   component B: pull B up, the beam's hinge refuses to go up, B stays down).
4. `delete_weld_constraint` really releases -- both the proof that the weld was
   what held the body, and how the inspect demo gets from one seated phase to the
   next inside one build.

The tabletop preset is used as-is (dt=0.01, substeps=4): a constraint's behaviour
under a different solver configuration would not size 4.4's lift test. The robot
is left out (`include_robot=False`); it takes no part and slows every step.

    python -m tests.weld_constraint_spike run.verbose=true
    python -m tests.weld_constraint_spike run.test=pair run.viewer=true run.keep_open=true
    python -m tests.weld_constraint_spike -m run.lift_force_scale=1.5,2.0,3.0

Prints one `weld_constraint_spike <test> ... ok=<bool>` line per test and a final
`weld_constraint_spike verdict ok=<bool>` line. Exits non-zero when any test
fails, so `bash_scripts` can gate on it.
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.world import StandardTabletopSceneBuilder, materials

GRAVITY = 9.81


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def body_pos(entity) -> np.ndarray:
    return _as_numpy(entity.get_pos()).reshape(-1, 3)[0].astype(float)


def place(entity, world_xyz) -> None:
    """Put a body back where a test wants it, carrying no motion over."""

    entity.set_pos(tuple(float(v) for v in world_xyz), zero_velocity=True)
    entity.zero_all_dofs_velocity()


def weld_pairs(scene) -> set[tuple[int, int]]:
    """The live weld set as unordered link-index pairs.

    This is the reading the 4.4 verifier's union-find will run on, so the spike
    parses it the same way the verifier will have to: the arrays come back padded
    with -1 up to the widest environment, and the pair order is whatever the
    solver stored, so entries are normalised and the padding dropped.
    """

    info = scene.rigid_solver.get_weld_constraints(as_tensor=True, to_torch=False)
    link_a = np.asarray(info["link_a"]).reshape(-1)
    link_b = np.asarray(info["link_b"]).reshape(-1)
    pairs = set()
    for a, b in zip(link_a, link_b):
        a, b = int(a), int(b)
        if a < 0 or b < 0:
            continue
        pairs.add((min(a, b), max(a, b)))
    return pairs


def lift(scene, cfg, *, pulled_link: int, force: float, watch: dict) -> dict[str, float]:
    """Pull one link straight up for a while; report how far each watched body rose.

    External forces are cleared every step (`RigidSolver.clear_external_force`),
    so the pull is re-applied each step rather than set once.
    """

    steps = int(cfg.run.lift_steps)
    start = {name: body_pos(entity)[2] for name, entity in watch.items()}
    pull = np.array([[0.0, 0.0, float(force)]], dtype=float)
    for step in range(1, steps + 1):
        scene.rigid_solver.apply_links_external_force(pull, links_idx=[int(pulled_link)])
        scene.step()
        if cfg.run.verbose and step % max(1, int(cfg.run.sample_every)) == 0:
            heights = " ".join(
                f"{name}={body_pos(entity)[2] - start[name]:+.4f}" for name, entity in watch.items()
            )
            print(f"[lift step={step:3d}] {heights}", flush=True)
    return {name: float(body_pos(entity)[2] - start[name]) for name, entity in watch.items()}


# --------------------------------------------------------------------------- tests


def run_readback(cfg, scene, bodies, home, verbose: bool) -> bool:
    """Can the constraint set be read back, and does deleting remove the edge?

    The union-find verifier has no other way to learn that a latch fired, so a
    weld that holds but cannot be read would still be unusable.
    """

    link_a = int(bodies["box_a"].base_link.idx)
    link_b = int(bodies["box_b"].base_link.idx)
    want = (min(link_a, link_b), max(link_a, link_b))

    before = weld_pairs(scene)
    scene.rigid_solver.add_weld_constraint(link_a, link_b)
    after_add = weld_pairs(scene)
    scene.rigid_solver.delete_weld_constraint(link_a, link_b)
    after_delete = weld_pairs(scene)

    added = want in after_add
    removed = want not in after_delete
    clean = not before
    ok = bool(added and removed and clean)
    print(
        f"weld_constraint_spike readback link_a={link_a} link_b={link_b} "
        f"pairs_before={sorted(before)} pairs_after_add={sorted(after_add)} "
        f"pairs_after_delete={sorted(after_delete)} "
        f"added={added} removed={removed} ok={ok}",
        flush=True,
    )
    return ok


def run_static(cfg, scene, bodies, home, verbose: bool) -> bool:
    """Weld to a world-fixed link: does the pull go nowhere?

    This is 4.4's wrong-socket case -- the beam latched into A2, which sits on the
    fixed component A. It is also the cheapest proof that the constraint bears
    load at all.
    """

    force = float(cfg.run.lift_force_scale) * float(cfg.run.box_mass) * GRAVITY
    anchor_link = int(bodies["anchor"].base_link.idx)
    box_link = int(bodies["box_a"].base_link.idx)

    scene.rigid_solver.add_weld_constraint(box_link, anchor_link)
    welded = lift(
        scene, cfg,
        pulled_link=box_link,
        force=force,
        watch={"box_a": bodies["box_a"], "control": bodies["control"]},
    )
    scene.rigid_solver.delete_weld_constraint(box_link, anchor_link)

    place(bodies["box_a"], home["box_a"])
    free = lift(
        scene, cfg,
        pulled_link=box_link,
        force=force,
        watch={"box_a": bodies["box_a"]},
    )

    held = welded["box_a"] <= float(cfg.run.max_held_lift)
    released = free["box_a"] >= float(cfg.run.min_free_lift)
    quiet = abs(welded["control"]) <= float(cfg.run.max_held_lift)
    ok = bool(held and released and quiet)
    print(
        f"weld_constraint_spike static force={force:.3f}N "
        f"welded_lift={welded['box_a']:+.4f}m free_lift={free['box_a']:+.4f}m "
        f"untouched_control={welded['control']:+.4f}m "
        f"held={held} released_after_delete={released} ok={ok}",
        flush=True,
    )
    return ok


def run_pair(cfg, scene, bodies, home, verbose: bool) -> bool:
    """Weld two movable bodies: does a pull on one carry the other?

    This is 4.4's lift test in miniature. There the pull is on component B and the
    thing that refuses to rise is the beam's hinge; here both bodies are free, so
    the readable signal is that they move together instead of apart.
    """

    force = float(cfg.run.lift_force_scale) * float(cfg.run.box_mass) * GRAVITY
    link_a = int(bodies["box_a"].base_link.idx)
    link_b = int(bodies["box_b"].base_link.idx)

    scene.rigid_solver.add_weld_constraint(link_a, link_b)
    risen = lift(
        scene, cfg,
        pulled_link=link_a,
        force=force,
        watch={"box_a": bodies["box_a"], "box_b": bodies["box_b"], "control": bodies["control"]},
    )
    scene.rigid_solver.delete_weld_constraint(link_a, link_b)

    # Half the applied force now carries twice the mass, so the pair rises less
    # than one box would. The test is that the partner came ALONG, not how high.
    carried = risen["box_b"] >= float(cfg.run.min_carried_lift)
    together = abs(risen["box_a"] - risen["box_b"]) <= float(cfg.run.max_pair_spread)
    quiet = abs(risen["control"]) <= float(cfg.run.max_held_lift)
    ok = bool(carried and together and quiet)
    print(
        f"weld_constraint_spike pair force={force:.3f}N "
        f"pulled_lift={risen['box_a']:+.4f}m partner_lift={risen['box_b']:+.4f}m "
        f"spread={abs(risen['box_a'] - risen['box_b']):.4f}m "
        f"untouched_control={risen['control']:+.4f}m "
        f"carried={carried} moved_together={together} ok={ok}",
        flush=True,
    )
    return ok


TESTS = {"readback": run_readback, "static": run_static, "pair": run_pair}


@hydra.main(version_base="1.3", config_path="../configs", config_name="weld_constraint_spike")
def main(cfg: DictConfig) -> None:
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"weld_constraint_spike_config -> {resolved}", flush=True)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))

    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control)
    tabletop = builder.create(show_viewer=show_viewer, include_robot=False)
    scene = tabletop.scene
    origin = np.asarray(tabletop.frames.task_origin, dtype=float)

    edge = float(cfg.run.box_edge)
    rho = float(cfg.run.box_mass) / (edge ** 3)
    stations = {
        "anchor": (0.00, -0.18),
        "box_a": (0.00, -0.06),
        "box_b": (0.00, 0.06),
        "control": (0.00, 0.18),
    }
    colors = {
        "anchor": [0.35, 0.36, 0.38],
        "box_a": [0.85, 0.35, 0.15],
        "box_b": [0.20, 0.45, 0.85],
        "control": [0.55, 0.56, 0.58],
    }
    bodies: dict = {}
    home: dict = {}
    for name, (x, y) in stations.items():
        center = origin + np.array([x, y, 0.5 * edge])
        home[name] = center
        bodies[name] = scene.add_entity(
            gs.morphs.Box(
                pos=tuple(float(v) for v in center),
                size=(edge, edge, edge),
                fixed=(name == "anchor"),
            ),
            material=gs.materials.Rigid(rho=rho, friction=float(cfg.run.box_friction)),
            surface=materials.plastic("object", colors[name]),
            name=name,
        )
        tabletop.manifest.add(name, bodies[name])
    builder.finalize(tabletop)

    selected = str(cfg.run.test)
    names = list(TESTS) if selected == "all" else [selected]
    unknown = [name for name in names if name not in TESTS]
    if unknown:
        raise SystemExit(f"Unknown run.test={selected!r}; expected one of {list(TESTS)} or 'all'.")

    print(
        f"weld_constraint_spike setup edge={edge:.4f} mass={float(cfg.run.box_mass):.4f}kg "
        f"rho={rho:.1f} dt={float(cfg.env.sim.dt):.4f} substeps={int(cfg.env.sim.substeps)} "
        f"lift_steps={int(cfg.run.lift_steps)} force_scale={float(cfg.run.lift_force_scale):.2f} "
        f"tests={names}",
        flush=True,
    )

    # Let everything come to rest before the first weld: a constraint added while
    # a body is still settling would freeze that settling error into the weld.
    scene.step()
    for _ in range(int(cfg.run.settle_steps)):
        scene.step()

    verdicts = {}
    for name in names:
        for body_name, entity in bodies.items():
            if body_name != "anchor":
                place(entity, home[body_name])
        for _ in range(int(cfg.run.settle_steps)):
            scene.step()
        verdicts[name] = TESTS[name](cfg, scene, bodies, home, bool(cfg.run.verbose))

    ok = all(verdicts.values())
    print(
        f"weld_constraint_spike verdict "
        + " ".join(f"{name}={result}" for name, result in verdicts.items())
        + f" ok={ok}",
        flush=True,
    )

    while cfg.run.keep_open and show_viewer:
        scene.step()

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
