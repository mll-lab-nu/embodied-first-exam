"""Slotted Post Ring oracle on the rigid-chain settings (slotted_post_ring_{hard,medium,easy}_chain).

oracle.run runs five stages in one Session from the task's reset, each ending in a fixed state (states.py):
M1 S0 -> S1 disc1 through the slot; M2 S1 -> S2 the ring over the post top; M3 S2 -> S3 the ring back through the slot
and off the bight; M4b S3 -> S4b the other parts inside the separator; M4a S4b -> S4a the ring into the goal.

Assembly frame throughout: origin at the post centre on the table, x right, y back (away from the robot's cameras),
z up. Hand A is the right arm, B the left.
"""
