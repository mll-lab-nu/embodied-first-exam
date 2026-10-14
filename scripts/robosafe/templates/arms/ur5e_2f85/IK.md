Each step moves the joint targets by at most the joints' speed limits (in `spec()["control"]`): a row further away
than that is approached at that speed. A target that runs more than 0.9 rad ahead of where the joint is (the arm is
held up by something it presses on) is held back. An `ee_pose` row is turned into joint targets by the arm's inverse
kinematics from the targets in force; a pose the arm cannot reach is approached as near as its joints allow and
reported in the row's result (`ik`: how far the pose was missed). Send consecutive quaternions with the same sign (a
positive dot product): `q` and `-q` are the same orientation, but rows in between are interpolated number by number.
