# RoboARC · buzz_wire_3d (standard)

| | |
|---|---|
| Task ID | `roboarc-buzz-wire-3d-03-i01-standard` |
| Benchmark | [RoboARC](https://github.com/mll-lab-nu/RoboARC) (The RoboARC authors, 2026), upstream `mll-lab-nu/RoboARC@153eb8c` |
| Robot | Franka Panda 7-DoF arm with a Robotiq 2F-85 parallel gripper (MuJoCo Menagerie) |
| Mode | standard |
| Instance | `buzz_wire_3d`, seed 0 |
| Time limit | 3 h |
| Reference solution | Included |

## Task
Guide the metal loop along the whole wire from start to finish without any metal part of the tool touching the wire.
Then lay the tool on the finish support the way it lay at the start, let go of it and move the arm clear of it.

## Success criteria
Success needs all of these:
- Start within 10 mm along the wire from its starting end and traverse continuously until within 10 mm of its
  finishing end. Keep one unambiguous wire crossing inside the loop. Skipping branches or taking the loop off the
  route before completing traversal does not count. A traversal that is lost must start again from the starting end.
- After completing traversal, lower the tool onto the finish support. The completed traversal remains valid when the
  loop leaves the wire to rest on the support.
- Match the finish resting pose within 5 mm and 10 degrees. A half-turn about the handle axis is an equivalent
  orientation. The tool must actually contact the finish support.
- Keep all metal parts of the tool clear of the metal wire throughout the episode. Wooden-handle contact is not a
  metal-wire failure. Remove all robot contact before final confirmation.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of
  verified clearance from every target part; opening the fingers while still touching or surrounding the target is
  insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement
  from the start of confirmation at most 1 mm. Each target rigid body's angular speed must be at most 0.02 rad/s and
  angular drift at most 0.02 rad.
- Confirmation window: all of these conditions hold together for at least 1 s of simulated time. If one stops holding,
  the window starts again.

How the grader measures it:
- The release clearance is measured between axis-aligned bounding boxes: one around each collision geometry of the
  whole robot (every link of both arms) and one around each collision geometry of the tool, so the true gap usually
  has to be larger than 5 mm.
- The loop's usable opening: the wire's centreline must cross the loop's disk less than 12.67 mm from the loop's
  centre (loop inner radius 14.14 mm minus the 1.47 mm wire radius).
- Continuous traversal: from one physics tick to the next, the crossing point may move along the wire by at most twice
  the loop's own motion in that tick (its displacement plus 12.67 mm times its rotation angle) plus 3 mm. A larger
  jump, no crossing, two crossings or a tangency cancels the traversal; it must then start again within 10 mm of the
  starting end, the end where the tool rests at the start.
- The finish support is the deck, and the finish resting pose is the start resting pose repeated at the wire's
  finishing end: the tool lies on the deck with its loop at that end of the wire and its handle pointing inward, the
  way it lies at the start.
- Metal contact is sampled at all 4 solver substeps of every tick. If any tick since the start had incomplete contact
  coverage (a simulator-side condition), the episode can no longer succeed.
- Forcing: an arm drive (not a gripper drive) at 95% or more of its torque cap while that arm's gripper, or a part it
  holds, presses on anything else with 20 N or more in total. Forcing alone never ends the episode and never changes
  the score.

Failures:
- Any metal-tool touch of the metal wire ends the episode in failure, including brief or zero-force touches.
- The tool falling more than 100 mm below the tabletop ends the episode in failure.

The graded episode is the one live episode in the `sim` service; nothing is replayed, and there is no reset. The
episode ends when the agent sends `/finish` or when the agent's session ends (at the latest after 3 h, which the
service counts from the agent's first request), or after 200,000 control steps (holds count).

These ends are judged on the end state. The conditions above must hold when the episode ends and keep holding, with
the last targets held, until they have held for the whole confirmation window; the time they already held before the
end counts. Meeting them earlier in the episode does not count, and the service never reports success while the
episode runs. A task failure (above) ends the episode at once and scores 0, even after a success; so does a simulator
error caused by the agent's actions.

Before the agent is served, the service checks the scene against the frozen instance; a mismatch is an infrastructure
failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 4096 | no GPU | 10 GiB |
| `sim` | 4 | 9 GiB | 1024 | 4 GiB | — |
| verifier (as `main`) | 4 | 16 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB / L4 24GB (sm_86 or newer).

## License
RoboARC ([mll-lab-nu/RoboARC](https://github.com/mll-lab-nu/RoboARC) @ `153eb8c`) is released under the MIT License
(Copyright (c) 2026 The RoboARC authors). The robot models are MuJoCo Menagerie's: ALOHA 2 (BSD-3-Clause, Trossen
Robotics), Franka Emika Panda (Apache License 2.0) and Robotiq 2F-85 (BSD-2-Clause, ROS-Industrial). The furniture part
meshes of the furniture-assembly scenes are CC BY 4.0 (Hugging Face dataset `MLL-Lab/embodied-first-exam-public`,
`ikea-mujoco/`). The simulator is MuJoCo 3.14.0 (Apache License 2.0). RGB images are rendered with Nyx (`gs-nyx`), used
in the images with its owners' permission; the studio lighting is a CC0 HDRI from Poly Haven. Puzzle designs modelled
after Hanayama's Huzzle Cast puzzles and the IKEA product names and designs are used with the owners' permission. No
non-commercial terms apply.
