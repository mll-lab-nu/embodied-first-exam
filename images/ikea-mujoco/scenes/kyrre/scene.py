"""KYRRE stool (AA-2118871-4, step 1: three legs, six screws) in MuJoCo 3.14 with two Franka Panda arms.

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_actuator1..7 (joint position targets, rad),
                                            #       left_actuator8 gripper (0 closed .. 255 open), same for right_
        S.step(n)                           # n x 1 ms physics steps (+ retention mechanism + success bookkeeping)
        S.success()                         # dict, 'success' True when the source criteria hold
        S.mech.metrics / S.mech.active(key) # per-operation gate values / weld state
Parts (free bodies): seat, leg_1..3, screws 130915_<leg>_<k> (2 per leg).
Each leg still carries the idle spring jaw of the removed press-in pin (jaw_s2_press_in_<leg>_0, slide joint).
The seat lies upside-down; operations (task.json, strictly in order): place leg 1, screw 1-1, screw 1-2,
leg 2, ..., screw 3-2; then release it (the stool stays upside-down). The press-in pins and the turn-over
were removed by user decision on 2026-10-16.
Non-contact mechanisms: one retention weld per operation, switched on by the source acceptance gates
(kyrre_mechanism.py); the jaw springs. Screws thread by SDF contact (0.5 mm pitch, right-hand).
Arm TCP sites: left_tcp / right_tcp (fingertip centre). Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
from kyrre_mechanism import KyrreMechanism
import success as _success

def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=KyrreMechanism, monitor=_success.Monitor)
