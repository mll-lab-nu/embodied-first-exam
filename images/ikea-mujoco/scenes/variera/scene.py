"""VARIERA shelf insert (AA-741461-4, step 1) in MuJoCo 3.14 with two Franka Panda arms.

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_actuator1..7 (joint position targets, rad),
                                            #       left_actuator8 gripper (0 closed .. 255 open), same for right_
        S.step(n)                           # n x 1 ms physics steps (+ success bookkeeping)
        S.success()                         # dict, 'success' True when the source criteria hold
Parts (free bodies): frame_1, frame_2, shelf, screw_1..4. Geometry, masses and friction from the
latest VARIERA export; screw threads and receivers are non-convex SDF (octree) meshes, so a screw
advances only by being turned (0.5 mm pitch, right-hand). No welds or other non-contact mechanism.
Arm TCP sites: left_tcp / right_tcp (fingertip centre). Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
import success as _success

def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=False, monitor=_success.Monitor)
