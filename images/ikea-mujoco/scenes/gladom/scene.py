"""GLADOM tray table (IKEA AA-1832218-3), full seven-operation scope, MuJoCo 3.14, two Franka Pandas.

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_actuator1..7 (joint position targets, rad),
                                            #       left_actuator8 gripper (0 closed .. 255 open), same for right_
        S.step(n)                           # n x 1 ms physics steps (+ retention mechanism + success bookkeeping)
        S.success()                         # dict, 'success' True when the source criteria hold
Parts (free bodies): frame_a (root), frame_b, ring, tray, screw_long, screw_bottom, screw_ring_l,
screw_ring_r. Geometry, masses and inertias from the source assets; screw threads and frame_a's
four nut sleeves are SDF meshes (0.5 mm pitch, right-hand), so a screw advances only by turning.
Non-contact mechanism: source retention joints = welds 'retain_<part>' to frame_a, switched on
by gladom_mechanism.GladomRetention when the source acceptance gates hold (see that file).
The tray is never jointed. Arm TCP sites: left_tcp / right_tcp. Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
from gladom_mechanism import GladomRetention
import success as _success

def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=GladomRetention, monitor=_success.Monitor)
