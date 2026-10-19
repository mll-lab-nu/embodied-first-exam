"""Robot bodies that are put together in memory: parts drawn by code here, and vendored models changed in memory.

`gripper_parallel`: a two-finger parallel gripper written as MJCF by this repository (no vendored file).
`g1_glide`: the Unitree G1 of `assets/third_party` on planar joints, its legs fixed in the standing posture, with that
gripper on both wrists: the robot `g1_glide` of `embodied_safety_exam.sim.robots`, whose spec names `g1_glide.make_spec` as the
function that makes its model. docs/MOTION.md 10.4 says what was measured on the body alone, section 13 what it does
as a robot of the room.
"""
