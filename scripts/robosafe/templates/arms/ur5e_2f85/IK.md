Each step moves the joint targets by at most the joints' speed limits (in `spec()["control"]`): a row further away
than that is approached at that speed. A target that runs more than 0.9 rad ahead of where the joint is (the arm is
held up by something it presses on) is held back. An `ee_pose` row is turned into joint targets by the arm's inverse
kinematics from the targets in force; a pose the arm cannot reach is approached as near as its joints allow and
reported in the row's result (`ik`: how far the pose was missed). `q` and `-q` are the same orientation; rows are
interpolated along the shorter way. An `ee_pose` row whose quaternion is not of unit length (|‖q‖−1| > 0.01, or not
finite) refuses the whole /submit (HTTP 400) and nothing is executed; a quaternion within 0.01 of unit length is
normalised.
