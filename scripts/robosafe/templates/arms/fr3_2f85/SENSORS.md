Each row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: the joints' positions
(`q_*`, rad) and speeds (`dq_*`, rad/s) as measured; `gripper`, the fingers' position as measured (0 open .. 1 closed),
and `gripper_opening_m`, the free distance between the pads; `tcp_x` .. `tcp_qz`, the hand's pose in the bench frame
(the convention of `ee_pose`: an observed pose is a valid target); `ft_fx` .. `ft_tz`, force (N) and torque (N m) at
the wrist flange in the flange's frame, the hand's own weight included; `time_s`, the robot's time.
