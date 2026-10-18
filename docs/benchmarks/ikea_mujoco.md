# IKEA MuJoCo

IKEA furniture-assembly scenes in plain MuJoCo 3.14.0 on the CPU (float64), each with two robot arms and physical
grasps (finger friction, no assist). Eight tasks ship, each in both modes (16 task directories,
`tasks/ikea-<task>-i00-{privileged,standard}`):

| task | robot | what is assembled | mechanism |
|---|---|---|---|
| `lack` | two Franka Panda | LACK side table: four legs screwed into the top | threads (exact convex pieces), latched retention welds |
| `svallet` | two ViperX 300 s (ALOHA 2) | SVALLET lamp: the bulb screwed in, the shade snapped on | spring jaws and snaps, the bulb's thread |
| `gladom` | two Franka Panda | GLADOM tray table | threads (SDF meshes), latched welds |
| `variera` | two Franka Panda | VARIERA box: screws driven with a screwdriver | threads (SDF meshes) |
| `eket` | two Franka Panda | EKET cabinet: dowels and panels | latched retention welds |
| `ikea365` | two Franka Panda | IKEA 365+ stand and bowl: a screw driven with a screwdriver | threads (exact convex pieces), latched welds |
| `vesken` | two Franka Panda | VESKEN shelf unit: 23 snap connections | spring jaws and snaps |
| `stegesund` | two Franka Panda | STEGESUND stand: bolts driven with a hex key | capsule helices, seat welds |

`simulator = "mujoco"`; `robot = "franka-panda-bimanual"` (two Franka Panda arms with MuJoCo Menagerie's Panda hand;
stegesund names its arms `left/` / `right/`, the others `left_` / `right_`) or `"aloha-2"` (svallet: MuJoCo Menagerie's
ALOHA 2, two ViperX 300 s arms). Standard tasks speak `eai-standard/2.4` (the operations capability:
`r.operation_status()`).

The agent budget is 10800 s (3 h) of wall clock in both modes. One reference execution must fit 40 % of it (4320 s) on
the trial host (Timing, below). A privileged trajectory may have at most the task's row cap (stated in its instruction:
the verifier's replays must fit its time limit).

## Work in progress (not tasks)
Four more scenes are in the image (`/opt/ikea/scenes/`) but are not tasks: no reference passes every gate yet.
- `burvik`: no reference passes under the prism rule and the joint-speed clamp; leg 3 is blocked by the scene's
  geometry (the top leans 6.4° in its jig, the hand hits the handle rack while spinning the leg), which needs a scene or
  fixture change.
- `kyrre`: the authors' demo loses screw 2-1 at its hole under the final physics (4 of 9 welds), and one replay takes
  12.3-14.0 ks on a Xeon core, about 3 x the 4320 s bar (the welded legs keep their box contacts with the seat).
- `stenerik`: the closed-loop build seats all six screws and peels the four pads, but its pad presses stay below the
  scene's 1 N / 0.3 s bond gate.
- `uppsta`: timing only. The closed-loop reference passes `final_check()` in fresh replays on AMD Zen 4 and Intel Xeon
  with the same hashes, but one replay takes 12,680 / 12,684 s on an Intel Xeon Gold 6230R core, 2.9 x the bar (its
  two screw drives cost 22-26 ms per row).

## Tasks and generator
- `python3 scripts/ikea_mujoco/mk_tasks.py` writes the privileged tasks, `mk_standard_tasks.py` the standard twins
  (privileged first: the twins share one reference). `--check` compares only; CI runs both (no simulator needed).
- Inputs, all in `scripts/ikea_mujoco/`:
  - `tasks.json`: the texts (goal, success requirements, mechanism, the terminal rules);
  - `assets.json`: the sha256 of every scene file in the image, and the dataset pin of the meshes (Image and assets);
  - `bindings.json`: what each scene builds to in the image (initial-state hash, actuators, timestep);
  - `evidence.json`, `standard_evidence.json`: the Harbor checks and timings the READMEs and the privileged verifier
    timeouts are written from;
  - `shared/`: `rcb_ikea.py` (the tooling and the replay), `grade.py` (the verifier), `render_video.py` (the replay
    video);
  - `standard/`: the sim service (`server.py`, `ikea_rig.py`, `ikea_nyx.py` with RoboARC's `nyx_direct.py`,
    `finalize.sh`), its grader (`grade.py`: transcribes the live episode's `final.json`) and the oracle client,
    `rigs.json` (camera rigs), `std_reference.py`;
  - `oracles/<task>/`: the closed-loop references and how they were built (eket, ikea365, vesken) and stegesund's
    reference; `tails/variera.npy`: variera's release tail;
  - `provenance.json`: the scenes' upstream provenance, kept out of the image (PROTOCOL Appendix H.2);
  - `tests/test_grade.py`: the privileged grader's crash handling on a stub replay, then `tests/test_standard_grade.py`:
    the standard hook and grader on synthetic `final.json` / `episode.json` (live success, live failure, settle failure,
    crash give-ups, instance mismatch, no video, missing `final.json`, no replay started) (`ci_checks/check-unit-tests.sh`).
- Every generator ends with `scripts/task_conventions.py` normalize; the generators also write the egress allowlist
  of `scripts/set_agent_egress.py`.

## Grading (both modes, every task)
One rule in both modes. Privileged: the deliverable (`/app/output/trajectory.npz`) is replayed open-loop in two fresh
processes from the frozen keyframe. Standard: the rule is evaluated on the live episode by the sim service; nothing is
replayed (below). Success needs all of:
- **Goal:** the scene's own `success.py`, a port of the source assembly grader.
- **Terminal rules,** the same in every task: the parts are released (no robot link touches a part); every part is at
  rest (at most 0.01 m/s and 0.05 rad/s); the simulation never broke down (no non-finite state, no MuJoCo BADQACC /
  BADQPOS / BADQVEL warning, no contact of a part deeper than 10 mm).
- **End pose (EKET):** every panel, the back included, ends within 10 mm and 2 degrees of its goal relative to the top
  panel (`rcb_ikea.END_POSE_RULES`): the source grader checks the back only at its slide, and the back has no frame joint.
- These hold at the end of the rows **and** again after the grader holds the last row for 1.0 s
  (`rcb_ikea.Session.final_check()`).
- Privileged: both replays end in the same state hashes, before and after the hold.
- A replay that crashes (a simulator crash, `replay_crash`) or in which the scene's code or MuJoCo raises on the state
  the rows drove it into (`replay_exception`) is a breakdown (`sim_breakdown 1`, reward 0), not a grader error: a
  grader or infrastructure error gives the trial a free retry (PROTOCOL H.5), which the deliverable's own failures must
  not get. A scene that differs from the binding or builds to another initial state is `infra_error 1`.
- The privileged verifier's time limit covers a trajectory of the task's row cap on a slow trial-class CPU (one
  reference replay on a Xeon Gold 6230R core, `evidence.json` `slow_replay_wall_s`, with a 1.5x margin), not only the
  Harbor host's timing: a verifier that times out writes no verdict.
- The privileged verifier checks the scene in its image file by file against `tests/runtime_binding.json`
  (`instance_exact`) and its initial-state hash (`instance_ok`); the standard sim service does the same before its
  episode begins (`server.py`: scene files, initial-state hash, actuators and runtime against
  `environment/sim/runtime_binding.json`; a mismatch is `instance_mismatch`, `infra_error 1`, and nothing is served).

Standard mode is graded by the live episode: `success` = the sim service's live
verdict, `graded_by_live 1`, `replays 0`. The service ends an episode at the first settled success, `Session.status()`
and then `final_check()` on a snapshot with the last row held 1.0 s (the privileged grader's rule, the settle window
included); a failed settle lets the episode go on (`meta["settle_failed"]`). An episode that ends otherwise (the wall
clock, the collect hook's end) is judged as it stands by the same two checks. `finalize.sh` writes `final.json`
(`graded_by "live"`, `replays 0`, `state_sha` = the live end-state hash); the verifier (`tests/grade.py`, the shared
client base, no simulator) transcribes it. The trajectory (`/data/trajectory.npz`) stays the replayable deliverable; a
live success without it is `infra_error`. Infrastructure (a free retry, H.5): no, unreadable or unfinalized
`final.json`, `instance_mismatch`, a give-up after crashes not all inside the agent's calls (`sim_crashed`,
`resume_failed`, `call_watchdog`), a service-side error. The agent's 0: a breakdown, a simulator error its rows caused
(`sim_error`), a timeout, all crashes inside its calls (`sim_crashed_on_call`), a failed settle.

Every graded trial leaves a video (PROTOCOL §4), evidence only: standard, the sidecar's `/data/live.mp4`, recorded during
the live episode (Nyx, cam_high, 10 frames per simulated second, on the GPU the sidecar renders the agent's cameras with;
no extra pass); privileged, `/logs/verifier/replay.mp4`, rendered by a third process next to the two verdict replays
(MuJoCo's renderer on CPU OSMesa: the verifier has no GPU; 512 x 288, at most 750 frames).

## Robot speed (both modes)
Every arm joint target moves at most the robot's real joint velocity limit per control step: Franka Panda 2.175 rad/s on
joints 1-4 and 2.61 rad/s on joints 5-7; ViperX 300 s 3.14159 rad/s. It is a clamp, not a failure
(`rcb_ikea.Session.applied()`, in the tooling and the replay alike): a row within the limit (+1e-9) is applied
unchanged, a faster one is spread over the following control steps. The gripper command is not limited.

## Physics changes against the source scenes
One rule for all scenes, clamp not fail (as RoboARC):
- **MuJoCo 3.14.0 with the EPA fix byte-patched in.** 3.14.0's EPA keeps the polytope horizon in two fixed 24-entry
  arrays and writes past them unchecked (fixed upstream after 3.14.0). A dowel pressed deep into a thin convex piece
  of eket's side panel overflows them: SIGSEGV or silent memory corruption, about 1 in 400 random eket episodes. The
  image patches 14 bytes of the wheel's own `libmujoco.so` (`images/ikea-mujoco/mujoco-3.14.0-epa/`); it is
  bit-identical to the stock wheel on every reference and stress episode checked. A from-source build is not
  bit-identical to the wheel and is not used.
- **Cylinder -> prism:** RoboARC's rule. Every cylinder a robot geom can touch is a 32-facet convex prism at scene
  build (inscribed in the cylinder). It removed every cylinder-caused breakdown of the stress test.
- **Joint-speed clamp:** above. The source demos command targets up to 55 x the real limits; the references were
  rebuilt or retimed within them.
- **Deferred: the Franka Hand slew** (0.1 m/s of finger width) is the long-term rule against finger slams; it is off
  until the references are retimed for it.
- eket's dowels: the soft dowel shells touch only the side panels; a stiff twin meets everything else.
- numpy / OpenBLAS SIMD masking in the image (`NPY_DISABLE_CPU_FEATURES` without AVX-512, `OPENBLAS_CORETYPE=Haswell`),
  as in RoboARC's image: unmasked, eket's reference diverged between AVX-512 and AVX2 hosts.

Stress test (random, jerk and prefix strategies from the frozen birth), with the clamp, the prism rule and the eket
dowel rule: non-jerk BREAKDOWN rate 1.75 %, prefix-jerk 7 %; stegesund, 203 episodes, one genuine non-jerk BREAKDOWN
(the known finger-limit class). Residuals, none blocking: finger slams
while the hand slew is off (gladom), energy created at robot joint limits under random arm targets (vesken, eket), one
table penetration (gladom, prefix-jerk), ViperX self-contact on jerk (svallet).

## References
Each task has one reference for both modes, every row within the joint-speed limits (the privileged
`solution/trajectory.npz` and the standard `solution/oracle_actions.npz` are the same rows):
- lack: the authors' demo passed through the clamp;
- svallet, gladom, variera: the demo time-dilated or centred to the limits (`standard/std_reference.py`); variera's
  demo ended holding the screwdriver, so a 240-row release tail is appended;
- eket, ikea365, vesken: closed-loop references built on the final physics (`oracles/<task>/`): the demo as the phase
  guide, with true-state feedback (Jacobian-IK servos, gates, local searches), recorded as the executed rows;
- stegesund: the authors' speed-limited demo, unchanged.

Harbor on the final images: privileged oracle 1 / nop 0 on all eight, standard oracle 1 (live settled success) / nop 0
on all eight; on the Nyx sidecar variera's standard oracle episode ends on the same settled success and end hash (its
verifier's result is not recorded yet). Each reference ends on the same state hashes on Intel AVX2
(i9-14900HX), Intel AVX-512 (Xeon Gold 6230R) and AMD Zen 4 (Ryzen 9 7950X, EPYC 9354).

## Adversarial trial (PROTOCOL H.1)
`ikea-eket-i00-privileged` with a red-team paragraph on top of its
instruction (obtain reward 1 without assembling the cabinet, by any exploit of the grader, the tooling, the file format
or the simulator), Codex + GPT-6 Luna xhigh with the pool's lane settings: reward 0, deterministic, no grader or
infrastructure error. The agent read the loader, the replay, `final_check()`, the operation tracker, the latches and the
end-pose rule and found no bypass; its best attempt (a one-row hold) replays released and at rest and fails the goal.
A malformed or compressed-bomb trajectory, a scene exception and, in standard mode, a simulator error or a malformed
request field are the agent's 0, never a free retry. Harbor checks: `evidence.json` `maintainer_checks` (eket) and
`maintainer_checks_standard` (svallet).

## Timing
One reference execution against the 4320 s bar (40 % of 10800 s). A Xeon Gold 6230R core (2.1 GHz) is a slow
trial-class CPU; the quiet i9-14900HX laptop a fast one; the standard live episodes ran on shared, loaded RTX 4090
workstations (Ryzen 9 7950X).

| task | rows | one replay, dedicated Xeon Gold 6230R core | one replay, quiet i9-14900HX | standard live episode, loaded host |
|---|---|---|---|---|
| eket | 70,210 | 472 s (4.4 %) | | 351 s |
| svallet | 69,414 | 478 s (4.4 %) | | 397 s |
| ikea365 | 89,126 | 604 s (5.6 %) | | 480 s |
| lack | 63,697 | 923 s (8.5 %) | | 639 s |
| vesken | 353,125 | 1,288 s (11.9 %) | | 1,145 s |
| stegesund | 357,221 | 3,160 s (29.3 %) | | 2,190 s |
| gladom | 168,628 | **5,636 s (52.2 %), over the bar** | 2,882 s (26.7 %) | 3,362 s |
| variera | 231,903 | **6,839 s (63.3 %), over the bar** | 3,413 s (31.6 %) | 4,365 s (EGL sidecar); 6,046 s (Nyx, load ~70) |

gladom and variera are inside the bar on a quiet fast host (26.7 % and 31.6 %) and over it on a slow Xeon core (52.2 %
and 63.3 %): MuJoCo's own step is about 95 % of the time (their SDF threads). They ship as the owner's decision; the
agent's budget is the same 10800 s on every host, so on a slow host an agent has less room for full replays.

## Image and assets
- `ghcr.io/mll-lab-nu/eai-ikea-mujoco:<images/ikea-mujoco/VERSION>` (0.3.0, image id `ed950d079b63`): MuJoCo 3.14.0
  (EPA-patched), numpy 2.5.4, Python 3.12, and the twelve scenes at `/opt/ikea/scenes/<task>` (the four in progress
  included). The privileged agent and the privileged verifier run it; the standard verifier runs the shared client
  base (it replays nothing).
- `ghcr.io/mll-lab-nu/eai-ikea-mujoco-sim:<images/ikea-mujoco/sim/VERSION>` (0.4.0): the standard sidecar. It adds Nyx,
  RoboARC's renderer and look, in its own venv `/opt/nyx` (gs-nyx 0.1.3 needs numpy < 2.4; the physics process keeps
  numpy 2.5.4 and the patched MuJoCo): RGB from Nyx (path tracer, 32 spp, denoised, studio HDRI, point lights placed
  relative to each scene's work surface), depth from MuJoCo's EGL raster, the same camera rig and calibration. The live
  state hashes with Nyx are bit-identical to EGL's over the first 2000 control steps of all eight references, and Nyx
  draws only what MuJoCo's raster drew.
- The scene code is in git (`images/ikea-mujoco/scenes/<task>/`); the meshes (2,078 files) are on the private Hugging
  Face dataset `eai-v2-internal/ikea-mujoco-assets`, pinned by revision and by every file's sha256 in
  `scripts/ikea_mujoco/assets.json`. `scripts/ikea_mujoco/fetch_image_context.sh` downloads them, checks them and stages
  the build context (`images/ikea-mujoco/README.md`).
- `stage_context.py` refuses a scene text that points at upstream material (H.2).

## World-frame information
The standard tasks' texts give no world coordinates: no part poses or positions, no table height, no world base poses.
Every pose the standard agent gets or gives is in the robot frame (origin at the left arm's base link, +z up). The
privileged tasks read anything, as privileged tasks do. A scene reads nothing from the environment (`rcb_ikea` drops
kyrre's development switches `SW_FROM_OP` / `SW_FROM_T` on import).
