# Hamburger assembly (Sharpa Wave or Wuji Hand 2.2)

This task assembles six recognizable layers: bottom bun, beef patty, cheese, tomato, lettuce and sesame top bun.
The bottom bun starts on a serving plate. The other five ingredients start separately on visible preparation supports.
All ingredients have free joints. Only the six wrist motors and the selected hand's manufacturer finger motors are
actuated: 22 for the default Sharpa Wave (28-wide rows), 20 for Wuji Hand 2.2 (26-wide rows).

## Hands

`Session(hand="sharpa"|"wuji")`, or `DEXHAND_HAND` when the argument is omitted, selects the hand
(`artifacts/ready-10-2026-10-14/HAND_INTERFACE.md`; shared code `scripts/dexhand/shared/hands.py`). Wuji Hand 2.2 is
mounted by `hands.replace_wave_hands` in place of the Wave body under the unchanged wrist stage: same wrist joints,
ranges, gains and start targets; vendor finger joints, actuators and contact geometry unchanged. Per-hand start
targets are `initial_targets` in `task.json` (Sharpa keeps the accepted pose; Wuji fingers start at 0).
`save_trajectory` writes `actions`, `hand` and `task`; `replay.py` rebuilds the scene with the archive's hand and
rejects a width that does not match it. Both hands have a successful trajectory: the Sharpa witness
(`solution/privileged.npz`, `solution/standard.npz`) and a Wuji one (`solution/wuji/trajectory.npz`, below).

## Wuji reference solution

`solution/wuji/trajectory.npz` (5,847 x 26 rows, `hand` = `wuji`, sha256 `1e30c0db...`) assembles the whole stack
with the Wuji Hand 2.2: success at control 5,847 (the last row; the released-stack condition held for controls
5,748-5,847), 6/6 layers aligned, largest center error 7.5 mm (cheese; limit 12 mm), peak bend 0.024 rad, no
fail-fast event. Rows are wrist-stage and finger position targets only; no object pose, weld or force is written.
The generator packages the file as `solution/wuji/` of both task directories, and the oracle uses it when the run
selects the Wuji hand. Authoring code (never copied into a task): `tools/wuji_demo.py` ports `demo.py` to Wuji
(least-squares pinch IK over the wrist stage, thumb and index joints; side pinch between the thumb and index
fingertips; middle, ring and pinky curled away; the Sharpa controller's gravity feed-forward), `tools/wuji_layers.py`
ran a greedy per-layer search (each variant a deterministic continuation of the accepted prefix: timing, placement
gap, grip squeeze, transport duration, lift height; the thin cheese and lettuce needed a firmer squeeze and a slower
carry), and `tools/wuji_gen.py` replays the accepted parameters without search and writes the identical archive:

```bash
PYTHONPATH=tasks/dexhand-assemble-hamburger-i00-privileged/environment \
  python3 scripts/dexhand/families/assemble_hamburger/tools/wuji_gen.py --out $OUT/wuji.npz   # about 70 s
```

Evidence (2026-10-14): `artifacts/ready-10-2026-10-14/wuji-success/assemble_hamburger/`,
`artifacts/ready-10-2026-10-14/reports/w-wujisucc-assemble_hamburger.md`.

## Success predicate

All six layer centers must lie within 12 mm of the plate center and their root bodies must remain within 0.22 rad of
upright. Heights must follow the recipe order, all five adjacent ingredient pairs must have active physical contact,
and the bottom bun must contact the plate. The hand must release every ingredient. Linear speeds must be at most
0.025 m/s, angular speeds at most 0.25 rad/s, and the complete condition must remain true for 100 consecutive
50 Hz controls. The episode ends at that moment (success); a partial stack never succeeds.

## Fail-fast failures

Checked after every 2 ms physics substep; the first failure ends the episode, `step` is a no-op afterwards and replays
stop there, so later actions cannot recover it:

| reason | condition |
|---|---|
| `ingredient_dropped` | any ingredient geometry (wings included) touches the table top or the floor |
| `ingredient_below_table` | any ingredient body is below the table top (z < 0.30 m) |
| `ingredient_left_workspace` | any ingredient body leaves `workspace` (x [-0.64, 0.64], y [-0.52, 0.52], z [0.30, 0.80] m) |
| `bend_limit_exceeded` | a cheese/lettuce hinge exceeds 0.65 rad |
| `unstable_physics` | MuJoCo reports a bad qpos/qvel/qacc |
| `episode_budget` | 7,500 controls without success |

The ingredients never touch the table in the validated witness (they move between their supports, the hand, the
plate and the stack), so these checks do not change its outcome.

The verifier ignores trajectory-supplied configurations and claimed success. It reads numeric motor targets and the
hand, and replays the task's frozen configuration twice in separate processes, requiring identical final state hashes.
Visuals and captions do not determine the verdict.

## Modeling scope

The hand uses the existing pinned Sharpa Wave visual meshes, contact geometry, inertias, native joint ranges and
effort bounds. A floating wrist stage provides reach; no arm or full-body dynamics are claimed. Finger servos use
explicit dissipative velocity feedback, as in the existing DexHand prototypes.

Bun halves, patty and tomato are rigid bodies with simple cylinder contact proxies and original procedural visual
details. Lettuce and cheese each have a free central strip and two passive elastically hinged side strips. Their
weights, bending joints, contact and gravity are simulated, but this is a coarse articulated thin-sheet model. It
does not model continuum elasticity, tearing, crushing, tomato fluids or culinary damage. The decorative lettuce
ripples, grill marks, tomato seeds and bun dome do not replace or enlarge the declared contact proxies.

This is an assembly feasibility task. A successful hand demonstration does not establish superiority over a parallel
gripper or zero-shot generalization. Benchmark release remains provisional until independent review and agent trials.

## Authoring and evidence

Use the project's pinned MuJoCo 3.4.0 environment and existing offline Sharpa assets. `demo.py` is authoring-only;
the generator never copies it into agent or verifier environments. It computes robot kinematics and produces motor
targets with physical contact, without driving any object pose or applying external object forces.

```bash
export MUJOCO_GL=egl OPENBLAS_NUM_THREADS=1
python scripts/dexhand/families/assemble_hamburger/demo.py --out $OUT/hamburger/actions.npz
python scripts/dexhand/families/assemble_hamburger/replay.py \
  --traj $OUT/hamburger/actions.npz --video $OUT/hamburger/assembly.mp4 --out $OUT/hamburger/replay1.json
python scripts/dexhand/families/assemble_hamburger/replay.py \
  --traj $OUT/hamburger/actions.npz --out $OUT/hamburger/replay2.json
python scripts/dexhand/generate.py --only-family assemble_hamburger --refresh-manifest
```

Evidence stays outside the repository's task directories. Each recording includes the actual motor replay, current
predicate measurements, playback speed, visible PASS/INCOMPLETE/FAIL status, the frozen scene digest and video digest.
The final closeup is a still of the released physical state. Both Harbor modes use the same frozen scene and runtime.

## Local validation

The native authoring witness passes after 6,090 controls (121.8 s of simulated time). The final state has all six
aligned layers and all five adjacent contacts, a maximum center error of 8.872 mm, a peak passive bending angle of
0.05859 rad, and 396 consecutive released stable controls. The recording replay, another independent replay and
both isolated Docker verifier replays have the same final integration state hash. The isolated verifier scores the
witness 1 and a 130-control no-op 0.

The public standard client also completes the same frozen scene, with float32 wire targets and no reset, after
5,793 recorded controls. Two fresh service replays pass and match the live final hash. An interrupted client request
continues from the recorded control count; it does not repeat or skip targets. Five native tests pass, and the new
task pair passes its structure, protocol, isolation, resource declarations, monitor wiring and agent-pointer checks.
The full repository check still reports generator differences in other benchmark families. These checks are local
feasibility and trust-boundary validation; independent solvability review and full agent/resource calibration remain
pending. The native video is 960 x 544, 10 FPS at 1x playback; every original 2 ms physics step is executed.
Trusted service collection defaults to 5 FPS at 1x playback to fit its bounded CPU rendering time; `--fps` overrides
the sampling rate. This changes drawing frequency only, and does not skip controls or physics steps.

## Studio presentation

`presentation.py` exports every visible native geometry transform from a complete passing actuator replay.
`verify` independently repeats the physics and checks exact equality of every sampled transform and state hash.
The studio renderer uses physically based food surfaces, bread pores, seared meat texture, moisture, porcelain,
soft area lights, optical depth of field and cameras that track the manipulated ingredient. The final shot frames
the released hamburger. The 4x presentation executes every original physics step; it samples poses for rendering
without synthesizing or interpolating object motion.

Rendering is separate from benchmark observations and grading. Visual edge bevels, a static 1.2 mm meat surface
finish and a thin lettuce epidermis are explicitly cosmetic. The lettuce's box contact proxies are hidden in the
studio image, while the original articulated leaf meshes retain their native positions. All these choices are
recorded in the render manifest. The frozen contact model and the success predicate remain the evaluated ones.
Blender and the authoring controller are never copied into the agent or verifier environments.

```bash
python scripts/dexhand/families/assemble_hamburger/presentation.py export \
  --trajectory $OUT/hamburger/actions.npz --export $OUT/hamburger/studio
python scripts/dexhand/families/assemble_hamburger/presentation.py verify \
  --trajectory $OUT/hamburger/actions.npz --export $OUT/hamburger/studio
python scripts/dexhand/families/assemble_hamburger/presentation.py render \
  --export $OUT/hamburger/studio --output $OUT/hamburger/studio.mp4 --engine eevee --frame-step 2
```

The GPU authoring environment uses Blender 4.5.3 LTS. `--engine cycles --still final --samples 96` produces a
path-traced hero image. Eevee Next with ray tracing produces the complete 1280 x 720 film. The helper selects a
task-local NVIDIA EGL vendor file when available, rather than changing shared system graphics configuration.
The default exported pose spacing and render sampling produce 12.5 FPS at 4x playback, followed by a two-second
hold of the final native state. The original 1x physics recording remains separate evidence.
