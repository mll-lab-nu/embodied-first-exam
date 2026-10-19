# dexhand-bicycle-pump-stroke-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-bicycle-pump-stroke-i00-standard` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `bicycle_pump_stroke` |
| Oracle | `full` — solution/ replays the validated Sharpa Wave episode on the Marvin right arm (4,299 controls, success after 4,149: hose head pushed onto the valve and locked at control 306, 28 counted strokes to 210.64 kPa, lock opened and head pulled off at control 4,083, released hold); the standard oracle submits the same rows as float64 through the public client. Two fresh-process replays succeed with identical state hashes, and the rows rounded to float32 also succeed. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Inflate the bicycle tire with the portable bicycle pump, using the right hand of the Tianji Marvin robot that stands at the bench (stand at the world origin, facing +x; the left arm stays parked). A mini floor pump (Topeak Mini Morph type, 154 g class, barrel 0.25 m tall) stands free on its folding foot on the bench next to a 406 (20 inch) wheel lying on the bench; as in the source scene, the pump's hose head starts disconnected from the wheel's Schrader valve and the tire is at 200.0 kPa gauge. The head (TRK-RP04 type) sits on the valve stem's axis 17.5 mm out from its seat (an 8 mm gap to the stem tip) with its thumb lock open (lever pointing up). The head moves only along the stem axis: a passive slide guided by the hose, with 2 N of friction and an end stop at the seat; pushing it 17.5 mm toward the rim seats it on the stem. The thumb lock is a passive hinge on the head (axis along world y, at the lever's foot, 0.004 N m friction) that turns 1.65 rad from up (open) to lying flat toward the wheel hub (closed). The pump's T handle rests at the top of its 0.20 m travel: the piston is a passive slide whose compressed-air spring pushes the handle back up (about 6 N at the top and 46 N at the bottom of the stroke) with viscous damping and 1 N seal friction. A stroke counts only while the head is connected (see stage 1), when the handle is pushed down to a piston depth of at least 0.18 m (90 % of the travel) and then returns to a depth of at most 0.04 m (20 %); shallower strokes never count and are not failures. The tire pressure is a checker quantity, not simulated air: every counted stroke adds 380 Pa (the mean rise per stroke of the source gas model, which reaches 210.6 kPa after its 28 strokes). Success requires, in this order: (1) the head connected: seated within 0.5 mm of its 17.5 mm travel while the thumb lock is closed to within 0.15 rad of its 1.65 rad stop (this latches; a stroke is armed and counted only while the head is seated and locked like this at that very moment); (2) at least 28 counted strokes; (3) tire pressure at least 210.6 kPa gauge; (4) the head disconnected again, as at the end of the source: the thumb lock opened to at most 0.5 rad and the head pulled at least 12.5 mm back off its seat (off the 9.5 mm stem engagement; this latches; the pressure stays, since only counted strokes change it); (5) the handle released at the top: piston depth at most 0.01 m, no contact of any robot part (hands, arms, stand) with any part of the pump or the head, pump tilt at most 0.0873 rad (5 degrees) from upright, pump centre-of-mass speed at most 0.02 m/s and handle speed at most 0.02 m/s, held continuously for 50 consecutive controls (1 s). The episode ends with success at that moment. The episode ends immediately with failure, checked after every 2 ms physics substep, when the pump tilts more than 0.2618 rad (15 degrees) from upright, when its base moves more than 0.03 m horizontally from its start or rises more than 0.02 m above it, when its centre of mass falls below the bench top (z < 0.70 m) or any pump part touches the floor, when the head, once connected and before stage 3 is reached, is pulled back more than 2 mm from its seat or its thumb lock is opened below 1.2 rad (head_disconnected), when the head is pulled back more than 2 mm from its seat while its thumb lock is still closed (at least 1.2 rad) after stage 3 (head_forced_off: open the lock first), or when the physics becomes unstable; later actions cannot undo a failure. The episode allows at most 5000 controls at 50 Hz; reaching that limit without success is a failure. Only robot actuator targets are allowed (the Marvin arm joints and the hands' finger joints); no object teleports, grasp welds, scripted object motion or direct object forces. The wheel, valve and hose are static props (the hose end at the head moves with the head, for display only); the head and its thumb lock move only through contact.

## Difficulty
The pump is free-standing, light (125 g) and narrow-footed (28 mm wide foot), with its T handle 0.45 m above the
bench: every downstroke needs about 45 N along the pump axis, and pushing off-axis levers it over. The hand sits on the
right arm of a Tianji Marvin robot whose 7 joints are position servos without gravity compensation, so the arm sags
under the handle's push unless its targets account for it. First the disconnected hose head has to be pushed 17.5 mm
onto the Schrader stem and its small thumb lock (a 24 mm lever between the spokes) swung down 1.65 rad to lock it;
only then do strokes count (only while the head stays seated and locked). 28 full-depth strokes are required (the
source scene's count; partial strokes never count), then, as at the end of the source, the lock has to be swung open
again and the head pulled back off the stem, then the hand must let go with the handle back at the top and the pump standing
still. Any tip, slide or lift of the pump, the head pulled off or unlocked before the strokes are done, or the head pulled
off while still locked, ends the episode as a failure at once.

## Reference solution
`solution/trajectory.npz` replays the validated Sharpa Wave episode on the arm: 4,299 controls; the head is connected
at control 306, the 28th stroke is counted at control 3,377, the head is disconnected at control 4,083 and the
released hold completes at control 4,149, where the replay ends with success (the last
150 rows hold the final targets as slack). In privileged mode `solve.sh` hands these rows in; in standard mode it
submits the same rows as float64 through the public client in 250-row chunks. The rows are arm-joint and finger
targets recorded from a closed-loop authoring controller (index finger pointed down beside the upright lever: push
the head onto the stem through the lever, then hook over the lever and swing it down along its arc; then fingers
wrapped over the T-handle grip, 28 eased strokes to about 0.19 m depth, release and withdraw; arm inverse kinematics
toward the planned hand path, the pumping part following the earlier floating-stage witness with one stroke cycle
repeated; finally the index finger, again pointing down beside the closed lever's free end, lifts it back up along its
arc, and thumb and index pinch the head behind the lever's foot and pull it 19 mm back off the stem). With `wuji` there is no reference episode for this version (the Wuji fingertip did not reach under the closed
lock's free end in the authoring attempts); the hand is selectable and graded the same way. The authoring tools compute motor targets only; they never drive an object pose or apply an object
force, and they are never copied into the agent's environment or image.

## Verification
privileged mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent: the pump tipping over 15 degrees, sliding more than 3 cm, lifting more than
2 cm, falling below the bench top or touching the floor, the head pulled back more than 2 mm or the lock opened below
1.2 rad after connecting and before the pressure is reached, the head pulled back more than 2 mm while still locked
afterwards, unstable physics, or the 5,000-control budget. The frozen
thresholds come from the task, never from an agent archive. A no-op fails. Human review and full agent-trial
calibration remain pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 5 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-3 integration smoke of the Marvin-arm families (Harbor 0.23, efe:dexhand-0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier 3.40-3.51 GiB with two concurrent replays, standard sim sidecar 2.13-2.65 GiB, agent containers < 0.05 GiB; one fresh replay process 1.75-1.81 GiB max RSS (os.wait4); x1.2 rounded up to a GB, the values of pot_shelf_transfer (the same robot); two cores for the two concurrent verifier replays
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: 8 GiB lets an agent run three or four 1.8 GiB Marvin simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details

### Notes
Source: `scripts/dexhand/families/bicycle_pump_stroke/`, generated by `scripts/dexhand/generate.py`. Scene geometry,
colours and poses come from the approved T50 scene-expansion film export (`assets/t50_scene.json`, meshes and sha256
manifest in `assets/`): Topeak MINI MORPH pump geometry and masses, the 32-spoke Schwalbe Big Apple 57-406 wheel with
its smooth tire shell, the Schrader valve and the locked TRK-RP04 head with its hose. Modelling scope: the pump is a
free rigid body on its foot; the piston chamber is a linear air spring on a passive slide (200 N/m, reference 0.23 m:
6 N at the top, 46 N at the bottom of the stroke), 15 N s/m damping and 1 N seal friction; tire pressure is a checker
quantity (380 Pa per counted stroke from the source's 200.0 kPa start, so the source's 28 strokes reach 210.64 kPa;
the source gas model ends at 210.62 kPa). The head starts disconnected as in the source (frame 0: 17.5 mm out, lever
up); it moves on a passive slide along the stem axis (the hose guides it; 2 N friction; the seat is the slide's end
stop) and its thumb lock on a passive hinge (0.004 N m friction, 0 to 1.65 rad); the cam's clamping force and the
grommet seal are not simulated (connected = seated and lever closed; disconnected = lever opened to <= 0.5 rad and
the head pulled >= 12.5 mm back, the source's final stages). The wheel, valve and hose are static props (the last four hose segments move with the head and the
two at the pump outlet are visual only). The Sharpa fingertip pads use the vendor's very soft elastomer contact, so a pressing fingertip can engulf the 1 mm-radius wheel spokes (a contact-model property; the head and lock states come only from their own joints and contacts). The Sharpa Wave assets are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same
arm flanges with its vendor joints, actuators and contact geometry unchanged. The robot is the Tianji Marvin stand
with two 7-DoF arms (the pot_shelf_transfer rig: position servos kp 700, kv 48, no gravity compensation) at the world
origin of the T50 frame, a hand on each flange, the left arm parked.

### Change Log
- 2026-10-16 (board 0136, video only): the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after `reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video. The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
