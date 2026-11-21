# embodied-olympics-fun-taekwondo-kick-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-taekwondo-kick-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `taekwondo_kick` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by a real front kick (lowcmd: 14.2 N s in 0.027 s on the protector, the threshold is 7.2 N s, peak 990 N) with an injected recovery (the robot put back at its start pose 0.25 s after the kick). No recovery was found: the robot falls within 0.6 s in every one of about 60 settings tried; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Kick the trunk protector of the dummy in front of you once with a foot, hard enough to score, then land and stand still for 2.0 s. (Embodied Olympics `taekwondo-kick`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The protector is above the robot's hip joints: the foot has to rise above hip height, fast, while the other leg alone carries the 33 kg body; the robot has no kicking or one-leg balance skill, and the protector's push back and the leg's swing both throw the body off its standing foot before it has to come down on both feet and stand. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-taekwondo-kick-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: A body-opponent dummy stands free on the floor in front of you: a heavy round base (0.61 m across, 0.5 m high, 122.0 kg, friction 0.5 on the floor) carrying on a stem a torso (0.36 m wide, 0.22 m deep, from 0.74 m up, 8.0 kg) and a head, 1.52 m tall in all, one rigid body. Its torso wears a taekwondo trunk protector, 0.32 m wide and 0.04 m thick, from 0.78 m to 1.12 m above the floor, facing you; the front of the protector is 0.58 m in front of your pelvis. Your first touch of the dummy is your kick: it must be made with a foot (the part below the ankle; your lower leg counts only where it lies over the foot and below the ankle joint) and must land on the protector. It is an impact, not a push: the touch lasts at most 0.05 s (it ends when foot and dummy have been apart for 0.03 s), and during it the protector must receive an impulse of at least 7.2 N s (the sum of the contact forces on it over the touch). After a valid kick you succeed when you stand for 2.0 s without a break, clear of the dummy: both feet and nothing else on the floor, the torso within about 20 degrees of upright, the pelvis slower than 0.35 m/s. You fail if any other part of you touches the dummy, if the kick lands anywhere but on the protector, is too weak or is a push, if after the kick any part of you other than a foot touches the dummy (a foot may touch it again but scores nothing more), if you fall (your pelvis lower than 0.35 m above the floor, or any part of you other than the feet on the floor), or after 15 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | World Taekwondo Competition Rules & Interpretation (2024): Article 5 (weight divisions: cadet male -33 kg, the robot's 33 kg), Article 11 (permitted techniques: a foot technique delivered with any part of the foot below the ankle bone; permitted area: the trunk, the area covered by the trunk protector), Article 12 (valid points: a valid kick to the trunk protector scores; the Protector and Scoring System (PSS) decides validity by the level of impact, set per weight division and gender), Article 21 (prohibited acts: falling down is a penalty); deviations: Article 12 (the PSS level): WT sets the impact level per division in its PSS's own units (KP&P men's levels 18-25 from -58 kg to +80 kg, Choi, Oh and Jeon 2021, BMC Sports Sci Med Rehabil 13:110); no conversion to physical units is published, nor a cadet level. The referee measures the impulse the protector receives during the kick and requires 7.2 N s: the mean minus one standard deviation of elite adult roundhouse kicks on an electronic protector (19.8 +- 4.5 N s input impulse, Chae et al. 2026, PLoS One 21:e0328749; athletes of 70 kg) scaled to a 33 kg athlete by body mass (a kick's impulse is its striking leg's momentum, which scales with body mass). · Article 12 (an impact, not a push): a PSS registers impacts; here a touch may last at most 0.05 s, about twice an elite kick's 0.026 s on a protector (Chae et al. 2026): a longer touch is a push. · No opponent and no bout: the target is a free-standing body-opponent dummy (Century BOB at its lowest setting, 1.52 m tall; its base filled with sand, about 122.0 kg, 0.61 m across) wearing a trunk protector from 0.78 m to 1.12 m above the floor, 0.32 m wide: the height of a cadet's protector. One kick, then stand: a single action, not a round. · The protector's padding: its contact lasts as long as a measured kick's (half an oscillation of 0.026 s, Chae et al. 2026) with a damping ratio of 0.5 (an estimate: the foam absorbs most of a kick's energy); the dummy is one rigid body (BOB's stem and plastisol torso do not bend). The floor is rigid, not a foam mat. · Article 11 (below the ankle bone): the foot is the robot's ankle-roll link; its lower-leg collision hull covers the top of the foot, so a contact with that hull counts as the foot only over the foot (from 0.08 m behind to 0.15 m ahead of the ankle joint) and not above the ankle joint. |
| Stages | kick → stand |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1500 control steps (15 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
