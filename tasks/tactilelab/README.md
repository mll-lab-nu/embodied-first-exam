# TactileLab

Contact-rich manipulation with tactile sensing: a dual-arm X-Trainer whose right gripper carries two GelSight Mini
sensors, on Isaac Lab 2.3.2 / Isaac Sim 5.1. The tactile image of each gel pad is geometric: a 60 x 80 taxel raycast of
the pad against the touched meshes, rendered to 240 x 320 RGB with a Taxim look-up table.

## Tasks
| Task | Mode | What is asked |
|---|---|---|
| `tactilelab-cable-needle-thread-i00` | privileged | Thread the cable tip through the square hole in the wall. |
| `tactilelab-cable-route-channel-i00` | privileged | Press the cable into the channel along its length and let go. |
| `tactilelab-cable-slack-reduce-i00` | privileged | Pinch the free end of the slack cable and pull it taut. |
| `tactilelab-cloth-edge-feed-i00` | privileged | Pinch the overhanging cloth edge and slide the pinch along it to the corner. |
| `tactilelab-cloth-fold-half-i00` | privileged | Fold the cloth in half over the fold line and let go. |
| `tactilelab-dough-fill-tray-i00` | privileged | Pick the scraper from its rack and spread the dough heap evenly over the tray. |
| `tactilelab-dough-press-thickness-i00` | privileged | Pinch the dough ridge to the target thickness at two places and lift the hand. |
| `tactilelab-dough-target-shape-i00` | privileged | Pinch the dough bar thin at its two outer slots, keep the middle thick, and lift the hand. |
| `tactilelab-drawer-container-i00` | privileged | Slide both containers into the drawer box, each to its back stop. |
| `tactilelab-fem-plug-insert-i00` | privileged | Carry the soft plug from its pick socket into the press-fit hole and seat it. |
| `tactilelab-gear-mesh-i00` | privileged | Slide the medium gear onto the middle post of the gear base so that it meshes with its neighbours. |
| `tactilelab-handover-i00` | privileged | Hand the rod over from the right gripper to the left gripper. |
| `tactilelab-insert-hdmi-i00` | privileged | Pick up the HDMI plug and insert it into the port. |
| `tactilelab-insert-tube-i00` | privileged | Pull the test tube out of its rack and insert it into the inclined bore of the tube slot. |
| `tactilelab-lamp-bulb-i00` | privileged | Screw the bulb into the lamp base and seat the hood on top. |
| `tactilelab-lift-i00` | privileged | Pick up the lying bottle, stand it upright on the green pad and let go. |
| `tactilelab-nut-thread-i00` | privileged | Turn the M16 nut further down the fixed bolt and let go. |
| `tactilelab-one-leg-i00` | privileged | Insert one square-table leg into a corner bore of the fixed table top and screw it in. |
| `tactilelab-sleeve-pull-on-forearm-i00` | privileged | Pull the sleeve along the other arm's forearm to the target band. |
| `tactilelab-square-table-i00` | privileged | Insert and screw all four legs into the four corner bores of the fixed table top. |

## Conventions (all tasks)
- Env frame, metres, z up; quaternions WXYZ. Table top z = 1.102, robot base at (-0.5, 0, 1.1) facing +x.
- Action row (22): right / left end-effector targets (7 each), right / left gripper command (0 open, 1 closed), optional
  right / left finger-gap override, optional right finger drive settings (velocity limit, effort limit, stiffness,
  damping); NaN = unused / hold. 60 Hz control. A release of the right gripper is physical (an open command after a close,
  once the fingers have opened 10 mm).
- Every task is privileged-only for now (no standard twin: a TactileLab simulator service is not written yet).
- Physics is PhysX on the GPU, as the tasks were developed: a rigid task is graded on two fresh-process replays that must
  end in the same state (they do on one machine). Deformable bodies run in a Newton sidecar on the GPU, which replays closely but not bit for bit:
  those tasks are graded on one fresh-process replay.
- Tooling: `rcb_tactilelab.py` (`embodied_first_exam/benchmarks/tactilelab/`), with the `tactilelab_tasks` package as the agent may
  read it (scripted policies and expert parameters removed); both come from the files-only image `tactilelab-files`. The files over
  2 MB (the X-Trainer robot USD and five meshes, two calibration arrays) come from the data-only image `tactilelab-assets-files`
  (a Hugging Face dataset, `images/tactilelab-assets-files/FILES.json`). Sources and licences of the third-party files:
  `images/tactilelab-files/ASSET_LICENSES.md`.

## Budget
3600 s per task. Every Python process pays about 1 min of Isaac Sim launch and scene build (the Newton sidecar's first start
compiles its GPU kernels, a few minutes once per trial).
