"""STENERIK laptop stand (AA-2372559-2, all 17 source operations) in MuJoCo 3.14 with two Franka Panda arms.

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_actuator1..7 (joint position targets, rad),
                                            #       left_actuator8 gripper (0 closed .. 255 open), same for right_
        S.step(n)                           # n x 1 ms physics steps (+ source mechanisms)
        S.success()                         # dict, 'success' True when the source grader criteria hold
        S.get_state() / S.set_state(s)      # full state incl. weld/mechanism bookkeeping
Parts (free bodies): support_1, support_2 (identical side supports), crossbar (6 threaded SDF inserts),
screw_1..6 (SDF thread, 0.5 mm pitch, right-hand; stand tip-down in a static holder), backing (strip),
pad_1..4 (bonded to the backing at start). Source world frame: bench top z = 0.12, the stand assembles
at x = 0 (supports at x = -/+0.109, y = 0), crossbar under the support flanges at y = -0.077.
Non-contact mechanisms (source fixed joints, switched by measured gates): see stenerik_mech.py.
Task details: task.json; arm/part layout: layout.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
from stenerik_mech import StenerikMechanism
import success as _success

def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=StenerikMechanism, monitor=_success.Monitor)
