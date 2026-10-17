"""UPPSTA toy hammering block (AA-2300462-4) in MuJoCo 3.14 with two Franka Panda arms (Menagerie Panda hand).

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'box' (parts as out of the box)
        S.data.ctrl[...] = ...              # arms: left/actuator1..7 (joint position targets, rad),
                                            #       left/actuator8 gripper (0 closed .. 255 open), same for right/
        S.step(n)                           # n x 0.3125 ms physics steps (+ the screws' seat welds; mj_forward
                                            # after every 8th step, the source's 2.5 ms tick)
        S.success()                         # dict, 'success' True when the assembled check holds (success.py)
        S.get_state() / S.set_state(s)      # full state incl. the seat-weld bookkeeping
Parts (free bodies): board (peg board, threaded holes in both ends), end_block_a / end_block_b, dowel_0..3,
screw_a / screw_b, hex_key, peg_0..7, hammer. Manual: dowels into one board end, end block b on, screw b with the hex
key, turn over, dowels, end block a, screw a, stand it on its feet, push the 8 pegs into their holes.
Mechanism: the shared seat weld on the two screws (uppsta_mech.py, seat_weld.py); everything else is contact (the
pegs' and dowels' compliant flutes are slide joints with springs).
Arm TCP sites: left/tcp, right/tcp (fingertip centre). Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
import success as _success
from uppsta_mech import UppstaMechanism


def load(keyframe='box'):
    return Scene(HERE, keyframe=keyframe, mechanism=UppstaMechanism, monitor=_success.Monitor)
