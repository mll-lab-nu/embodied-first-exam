# robocasa-gr1-placemat-to-bowl-i00-standard

Standard-mode twin of `robocasa-gr1-placemat-to-bowl-i00` (see its README): the same instance and success check, served as a
robot service (`images/robocasa-gr1/standard/server_casa.py`, protocol eai-standard/2.1, tool module `casa_tool`). The
agent sees the robot's cameras (RGB-D, calibrated), its own joints and end effector, and the instruction.

## Difficulty
The agent has to find the objects in the humanoid's camera images, coordinate two arms and two dexterous hands
through the IK controller, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged reference's 136 actions submitted through the client, one row per control
step.

## Verification
The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no network)
reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`.
