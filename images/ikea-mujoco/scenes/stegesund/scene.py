"""STEGESUND roll stand (AA-2652783-1) in MuJoCo 3.14 with two Franka Panda arms (Menagerie Panda hand).

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left/actuator1..7 (joint position targets, rad),
                                            #       left/actuator8 gripper (0 closed .. 255 open), same for right/
        S.step(n)                           # n x 0.625 ms physics steps (+ the seat welds of the bolts)
        S.success()                         # dict, 'success' True when the assembled check holds (success.py)
        S.get_state() / S.set_state(s)      # full state incl. the seat-weld bookkeeping
Parts (free bodies): half_A, half_B (the two leg frames), shelf (its rail ends hold the threaded nuts), rod (the top
rod), bolt_1..4 (threaded, standing on their heads), hex_key. Manual: the halves slide together, the shelf goes in
from the foot end, a bolt through each leg into the shelf rail (hex key), the rod drops into the crotches.
Mechanism: the shared seat weld on the four bolts (stegesund_mech.py, seat_weld.py); everything else is contact.
Arm TCP sites: left/tcp, right/tcp (fingertip centre). Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
import success as _success
from stegesund_mech import StegesundMechanism


def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=StegesundMechanism, monitor=_success.Monitor)
