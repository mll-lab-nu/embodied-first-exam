"""IKEA LACK side table (AA-207276-4, four legs) in MuJoCo 3.14 with two Franka Panda arms.

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_actuator1..7 (joint position targets, rad),
                                            #       left_actuator8 gripper (0 closed .. 255 open), same for right_
        S.step(n)                           # n x 1 ms physics steps (+ seat mechanism + success bookkeeping)
        S.success()                         # dict, 'success' True when the source grader's criteria hold
Parts (free bodies): tabletop (1 kg slab, studs up, four preinstalled Factory M16 studs at
task.json['slots_in_tabletop_frame']) and leg_0..leg_3 (0.12 kg, lying on their side). Screw each leg
(nut end down) onto a stud: the M16 x 2 right-hand threads are exact convex pieces (tools/threads.py), no SDF.
Non-contact mechanism (source): auto-weld on seat, see lack_mechanism.py.
Arm TCP sites: left_tcp / right_tcp (fingertip centre). Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
import success as _success
from lack_mechanism import SeatWeldMechanism


def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=SeatWeldMechanism, monitor=_success.Monitor)
