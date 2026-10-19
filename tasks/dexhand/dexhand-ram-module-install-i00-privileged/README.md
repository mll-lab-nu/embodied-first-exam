# dexhand-ram-module-install-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-ram-module-install-i00-standard` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `ram_module_install` |
| Oracle | `full` — solution/trajectory.npz replays the validated Sharpa Wave authoring trajectory in both modes (1,529 rows; the episode ends at success after 1,379 controls, with the source's 1.66 mm socket throat). Two fresh-process replays give identical state hashes; Harbor 0.23 oracle trials score 1 in privileged and standard mode, nop trials 0. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Install the DDR4 memory module into the outer DIMM socket of the motherboard (socket_3, the slot nearest the board edge). The module stands upright in a slotted anti-static foam holder on the bench, key notch towards +y; the motherboard is fixed in its service tray and the socket's single moving latch starts open. Pick the module up, keep its keyed orientation, insert it straight into the socket and press it home so that the passive latch snaps closed, then let go. The episode succeeds when these stages have happened in order: (1) picked: the module is out of the holder (no holder contact, its lower edge at least 10 mm above the slit top, z >= 0.851 m) and held by the thumb and at least one other finger; (2) seated: both lower module ends 1.5 to 2.6 mm above the socket base (the 2 mm seating datum), lateral offset of both ends at most 0.5 mm, along-slot offset at most 1.0 mm, the module's height axis within 3 degrees of vertical and its length axis within 3 degrees of the socket's keyed direction (a reversed module never counts); (3) latched: while seated, the moving latch hinge is at most 0.08 rad (closed); and then, for 50 consecutive controls (1 s), the module stays seated and latched with no hand contact on the module or the latch, module speed at most 0.01 m/s and angular speed at most 0.2 rad/s. The episode ends with success at that moment; a partial installation never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the module touches anything other than the hand, its foam holder or the target socket (the bench, the service tray, the motherboard and its components, the other three sockets, the floor), when the module is unsupported (touches nothing) while its centre of mass falls faster than 0.2 m/s, or has fallen freely more than 5 cm (no drop-and-catch), when any lower module corner drops below the bench top (z < 0.825 m) or a lower module end inside the socket comes closer than 1.2 mm to the socket base (pushed into the 2 mm floor), when the module origin leaves the workspace box x in [0.30, 0.95] m, y in [-0.36, 0.34] m, z in [0.826, 1.25] m, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct module forces. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure. The socket throat is the source's 1.66 mm (module 1.27 mm).

## Difficulty
The module is a 1.27 mm thick, 133 mm long PCB: the hand must pinch it out of its holder without wedging it, carry
it without letting it pivot or yaw in the pinch, keep the keyed orientation, bring both ends into the 1.66 mm throat
between 16 mm end guides, seat it level on a narrow key and press it home far enough to flip the over-centre latch,
then let go without disturbing it. Any contact of the module with the bench, tray, board, components or the other
sockets, a free fall, or a module below the socket floor ends the episode as a failure at once.

## Reference solution
`solution/` (when present) replays a Sharpa Wave authoring trajectory produced by a closed-loop scripted controller
(`scripts/dexhand/families/ram_module_install/demo.py`): a thumb-index pinch at the module's upper band, a levelling
touch on the foam holder, carry, closed-loop alignment over the slot using the module pose, fixed-end-first entry,
levelling along the arc about the seated end (the latch end pushes the latch foot over centre), release and withdrawal.
It computes robot kinematics and motor targets only; it never drives an object pose or applies an object force, and
it is never copied into the agent's environment or image.

## Verification
privileged mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent: module contact with anything but the hand, the holder or the target socket, an
unsupported module falling faster than 0.2 m/s (no drop-and-catch window) or a free fall above 5 cm, a module below
the bench top or pushed into the socket floor, leaving the workspace box, unstable physics, or the 3,000-control
budget. The frozen thresholds come from the task, never from an agent archive. A no-op fails.
Human review and full agent-trial calibration remain pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-2 integration smoke (Harbor 0.23, efe:dexhand-0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier <= 0.64 GiB with two concurrent replays, standard sim sidecar <= 0.96 GiB, agent containers < 0.05 GiB; one fresh replay process 0.26-0.39 GiB max RSS (os.wait4); x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3-0.5 GiB each)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: 8 GiB lets an agent run more than a dozen 0.3-0.5 GiB simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details

### Notes
Source: `scripts/dexhand/families/ram_module_install/`, generated by `scripts/dexhand/generate.py`. Scene geometry,
materials, label texture and module dimensions/mass/inertia come from the accepted scene-expansion scene T28
("Install a desktop RAM module", `assets/t28_scene.xml`, sha256 in `assets/manifest.json`); it is an approximate
authored DDR4 module and ATX motherboard, not manufacturer CAD. Physics changes for a hand-executed episode: the 30
copper contact sliders and both side catches are visual only; the target socket throat and end guides keep the source's
1.66 mm (module 1.27 mm), with 0.6 rad lead-in chamfers; its floor is raised to the source's 2 mm seating datum; the key
keeps its off-centre position and height but is 0.7 mm wide with a rounded top; the fixed-end post is rigid; the moving
latch keeps its hinge, range and damping, and its spring is an over-centre toggle (a passive spatial tendon) because
the source's frictionloss detent creeps shut in MuJoCo's soft-constraint solver. The module starts upright in a
slotted anti-static foam holder (a flat 1.27 mm PCB cannot be picked off the bench by this rig). No electrical
contact, retention force or boot is simulated. The Sharpa Wave assets are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same wrist
stage with its vendor joints, actuators and contact geometry unchanged. This is assembly feasibility on a floating
wrist stage, not a full-arm or zero-shot claim.

### Change Log
- 2026-10-16 (board 0136, video only): the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after `reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video. The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
