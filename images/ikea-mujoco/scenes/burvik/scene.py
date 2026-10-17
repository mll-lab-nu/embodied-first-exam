"""BURVIK side table (IKEA AA-2445102-1, 7 operations) in MuJoCo 3.14 with two Franka Panda arms.

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_actuator1..7 (joint position targets, rad),
                                            #       left_actuator8 gripper (0 closed .. 255 open), same for right_
        S.step(n)                           # n x 1 ms physics steps (+ retention mechanism)
        S.success()                         # dict, 'success' True when the source endpoint criteria hold
Parts (free bodies): top (1 kg, starts upside down on a 4-post stand), leg_0..leg_3 (0.15 kg, in a
notched rack), handle (0.35 kg, flat on a rack). Geometry/masses/inertias from the source
BURVIK assets. Each leg end is a right-hand M8 thread (1 mm lead, SDF mesh) that screws into an SDF
nut: leg_0/leg_1 into the top's two bosses, leg_2/leg_3 into the handle's sleeves through the top
holes; about 12.5 turns from first engagement to the seat.
Operations (source order): leg_0, leg_1 into the upside-down top; turn the top on its side; push the
handle through the two remaining top holes; leg_2, leg_3 into the handle; turn the table upright.
Non-contact mechanism: retention welds leg_*/handle -> top, switched on once the source gates hold
for 0.15 s (mechanism.py). Arm TCP sites: left_tcp / right_tcp. Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
import success as _success
from mechanism import BurvikRetention

def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=BurvikRetention, monitor=_success.Monitor)
