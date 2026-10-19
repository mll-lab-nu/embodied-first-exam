"""Optional control libraries of the robot library (bodies/README.md): shared code a sport may import, never required.

  wholebody.py   the whole-body planner (a tool pose and velocity at a contact time -> 100 Hz targets of a wheeled
                 robot's controlled vector, or of a legged robot's planar copy)
  arbiter.py     joint-group arbitration for the legged robots (walking policy, plans of joint targets, skills,
                 handovers) and the low-level plan interface
  kinematics.py  forward / inverse kinematics on MuJoCo's Jacobians for low-level players (self-contained: numpy +
                 mujoco only, copied into a player's toolkit); the IK keeps the model's self-collision pairs apart
                 (test: test_selfcollision_ik.py)

A sport lists the ones it uses in sport.toml [body] controllers; they are part of its assembled configuration's hash
(bodies/assembly.py). None of them is a lifecycle the robot or the sport must implement.
"""
