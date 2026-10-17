"""EKET 70332124 (AA-1914763-5) manual steps 1-4 in MuJoCo 3.14 with two Franka Panda arms.

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_actuator1..7 (joint position targets, rad),
                                            #       left_actuator8 gripper (0 closed .. 255 open), same for right_
        S.step(n)                           # n x 1 ms physics steps (+ source latch + success bookkeeping)
        S.success()                         # dict, 'success' True when the source grader's criteria hold
        S.mech.tracker.status()             # current operation, its goal (top frame) and live gate metrics
Parts (free bodies): top, bottom, side_a, side_b, back (source masses/inertias; boards stand on their front
edges in low racks).  Assembled pose of every panel = identity orientation relative to `top`, offset
task.json['goals_in_top_frame'][part].  Operation order and gates: success.py / eket_ops.py.
Non-contact mechanism: source frame joints joint_side_a, joint_side_b, joint_bottom_a, joint_bottom_b
(weld equalities) latched with the measured relative pose when side_a_slide / side_b_slide /
bottom_slide pass.  Everything else (mitres, keyholes, dowels, back grooves) is contact.
Arm TCP sites: left_tcp / right_tcp (fingertip centre). Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
import success as _success
from eket_ops import EketMechanism

def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=EketMechanism, monitor=_success.Monitor)
