"""IKEA 365+ serving stand (AA-2568481-2) in MuJoCo 3.14 with two Franka Panda arms.

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_actuator1..7 (joint position targets, rad),
                                            #       left_actuator8 gripper (0 closed .. 255 open), same for right_
        S.step(n)                           # n x 1 ms physics steps (+ operation ledger / retention mechanism)
        S.success()                         # dict, 'success' True when the source grader's criteria hold
Parts (free bodies): member_a (root; stands on its two feet at the assembly location, with the
same_screw threaded into its insert), member_b, same_screw, bowl. Geometry, masses, inertia and
friction from the accepted c5af013e export (member_b rim colliders disabled, visual only).
Thread: the source SDF meshes (screw 'Thread', member_a 'Insert_0') are visual only; collision is the
shared tools/threads.py model (exact convex pieces, M4 x 0.5 right-hand), so the screw advances only
by being turned.
Operations, in order (S.mech.accepted() / S.mech.ops): remove_same_screw, park_same_screw,
cross_members, return_same_screw, reinstall_same_screw, turn_stand, place_bowl.
Non-contact mechanism: two weld equalities (ret_member_a_same_screw, ret_member_a_member_b) switched
on with the current relative pose once the reinstalled screw is seated (source post-seat retention).
Arm TCP sites: left_tcp / right_tcp (fingertip centre). Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
from mechanism import Ikea365Mechanism
import success as _success

def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=Ikea365Mechanism, monitor=_success.Monitor)
