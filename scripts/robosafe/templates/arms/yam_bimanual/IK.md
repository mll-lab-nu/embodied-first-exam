In both motion types a row holds the left arm's numbers first, then the right arm's (the `layout` of each type names
every column). Each step moves the joint targets by at most the joints' speed limits (in `spec()["control"]`): a row
further away than that is approached at that speed. A target that runs more than 0.9 rad ahead of where the joint is
(the arm is held up by something it presses on) is held back. An `ee_pose` row is turned into joint targets by each
arm's inverse kinematics from the targets in force; a pose an arm cannot reach is approached as near as its joints
allow and reported in the row's result (`ik`: how far the pose was missed, per arm). An arm that is to stay where it is
needs its own current numbers in the row. Send consecutive quaternions with the same sign (a positive dot product): `q`
and `-q` are the same orientation, but rows in between are interpolated number by number.
