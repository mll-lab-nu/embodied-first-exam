# dexhand-binder-page-load-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-binder-page-load-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `binder_page_load` / seed 0 |
| Oracle | `full` — solution/ replays the validated Sharpa Wave authoring trajectory (2,192 controls, success after 2,042; standard mode submits the same float64 rows through the public client). Two fresh-process replays succeed with identical state hashes; float32-rounded rows also succeed. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Load both punched pages into the open-front ring binder on the desk. The binder (free on the desk, back cover towards +x) has three 1-inch round split rings on two toggle plates with an over-centre spring: both plates rest closed at 0 rad and open at 0.60 rad, and a booster paddle at each end of the mechanism opens them when pressed down. Two rigid punched pages (139.7 x 215.9 mm, 6 g, three 6.35 mm holes 9.5 mm from the binding edge) lie loose and flat on the desk, printed face up, holes towards the binder (-x), as in the source scene. Complete these stages in order. (1) Rings opened: both toggle plates at 0.50 rad or more. (2) Pages placed: with the rings still open (0.50 rad or more), every one of the six holes is threaded by the right ring half of its own station (the ring wire centre line crosses the page plane exactly once within 3.5 mm of the hole centre, the left half not at all), no hand contact on either page, each page touches the binder or the other page, and each page centre (60 mm from the hole line into the sheet) lies over the back cover: binder-frame x in (0.03, 0.16) m, |y| < 0.03 m, z in (-0.01, 0.06) m. (3) Rings closed: both toggle plates at 0.05 rad or less, every hole linked exactly once by its closed ring (one crossing within 3.5 mm of the hole centre) and both page centres over the back cover. (4) Release: the stage-3 condition with no hand contact on any page or any binder part, both pages resting on the binder and each page staying within 2 mm and 0.03 rad of its pose at the start of the window, for 50 consecutive controls (1 s). The episode ends with success at that moment; one page, an unthreaded hole or open rings never count. The episode ends at once with failure, checked after every 2 ms physics substep, when a page touches the floor; when a page has no contact at all, falls faster than 0.2 m/s and no ring runs through any of its holes (dropped); when a page origin goes more than 2 mm below the desk top (z < 0.698 m) or leaves the workspace x in [0.20, 0.98] m, y in [-0.38, 0.48] m, z in [0.698, 1.10] m; when the binder moves more than 0.03 m horizontally from its start or tilts more than 0.35 rad; when a ring wire penetrates a page deeper than 1.2 mm or a hand part penetrates a page deeper than 3 mm (a ring can only enter a page through its hole); or when the physics becomes unstable. Later actions cannot undo a failure. Only robot actuator targets are allowed; the rings, plates, boosters and covers move only through contact and their passive joints. Pages may slide on the desk and hang over its edge (a page touching the desk is not a failure). Pages are stiff cardstock plates: paper bending is not modelled. At most 6000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
The hand has to operate a passive over-centre mechanism (press a booster lever to open the rings, press the raised
toggle plates to close them), pick up thin rigid pages that lie flat on the desk (drag each one with the fingertips
until its far edge hangs over the desk edge, then pinch the overhang between thumb and fingers), and thread three
6.35 mm holes at once over three 2.6 mm ring wires while the page follows the curved ring. Both pages must be
threaded on all three rings before the rings close, and the hand must leave everything still for one second. A
dropped page, a page on the floor, a wire forced through the paper, or a binder pushed more than 3 cm ends the episode
as a failure at once.

## Reference solution
`solution/` replays the validated Sharpa Wave authoring trajectory (3,095 controls; the replay ends at success after
2,940 controls). The authoring controller reads the simulator
state and commands motor targets only; it never sets an object pose or applies an object force, and it is never copied
into the agent's environment or image.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure.
Failures are fail-fast and permanent (see the task text). The frozen geometry and thresholds come from the task, never
from an agent archive. A no-op fails. Human review and full agent-trial calibration remain pending; report this task
as provisional.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 10 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details

### Notes
Source: the DexHand family of this task. Scene: accepted
scene-expansion T37 (Avery 05806 Standard View mini binder reconstruction, 1 in round rings, 5.5 x 8.5 in pages with
1/4 in holes; authored geometry, not manufacturer CAD). The binder is free on the desk with passive spine/cover hinges,
two toggle ring plates (0 to 0.60 rad) coupled by the source's internal linkage, one over-centre spatial-tendon spring
per plate and two boosters. Pages are rigid 6 g cardstock plates with three see-through octagonal holes; paper bending
is not modelled. The two pages start loose and flat on the desk at the source scene's positions. The Sharpa Wave assets
are pinned to MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model
(`hand2/hand2_2`) is pinned to wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT)
and mounted on the same wrist stage with its vendor joints, actuators and contact geometry unchanged.
