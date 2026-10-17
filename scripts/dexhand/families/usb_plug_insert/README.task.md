## Task
{{TASK_TEXT}}

## Difficulty
A 7 g plug lying on its side must be picked up with fingertips much larger than its 8 mm housing, turned polarity-up in
the hand, carried past the desk edge and aligned to a cavity with 0.15-0.25 mm clearance, then released without
pulling it back out or disturbing the light, free hub. The grasp must survive the drag of a 0.5 m cable. Any drop,
displaced hub or partial insertion fails.

## Reference solution
`solution/trajectory.npz` holds the validated Sharpa Wave trajectory on the Marvin right arm: 1,595 rows of 58 targets;
the replay ends at success after 1,475 controls (the remaining 120 hold rows are slack and are not executed). The hand
picks the plug up with a thumb against index and middle fingertips and lifts it; the arm then changes its posture in
joint space while carrying the plug (the pick and the insertion under the desk edge need different arm
configurations), turns it polarity-up in front of the desk edge, aligns it with port 4 in closed loop on the plug pose,
inserts it about 11.9 of 12 mm, releases it (index up, thumb down, then open) and withdraws. In standard mode the oracle
submits the same rows through `rcb_client` in 250-row chunks. The authoring controller that produced the rows
(`scripts/dexhand/families/usb_plug_insert/tools/arm_author.py`, closed loop on the simulator state) computes robot
motor targets only; it never drives an object pose or applies an object force, and it is never copied into the agent's
environment or image.

## Verification
{{MODE}} mode. The verifier rebuilds the frozen scene with the recorded hand and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent: a dropped plug, the plug below z = 0.685 m, the hub moved more than 20 mm or
tilted more than 20 degrees, plug or hub outside the workspace box, the cable's far end pulled off the desk, an arm
link, the robot's stand or the parked hand touching anything, unstable
physics, or the 3,000-control budget. A no-op fails. Human review and full agent-trial calibration remain pending;
report this task as provisional.

## Details
Source scene: T24 "Connect a USB cable to a held device" (scene-expansion kinematic demo,
`scripts/scene_expansion/repairs/usb_cable_meta_delivery_trajectory_r1`): original authored real-scale four-port hub
and USB-A-to-B cable dimensions and materials (`assets/usb_scene.json`, sha256 in `assets/manifest.json`). Physical
modelling for a 2 ms dexterous-hand task: the hand is carried by the right arm of a Tianji Marvin robot standing in
front of the desk (floor 0.10 m lower than in the source, so the desk top is 0.90 m above it, and the desk's two front
legs set back under the top to clear the robot's base plate; both disclosed), the hub rests free on the desk (one hand; the hub is not held), each port is
an open cavity with generous clearance, receptacle tongue and contacts are visual, retention springs are omitted, the
hub's upstream cable is a visual rigidly attached to the hub, and the plug cable is a passive 20-link ball-joint rod.
