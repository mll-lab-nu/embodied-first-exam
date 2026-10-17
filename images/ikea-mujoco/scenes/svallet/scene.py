"""SVALLET work lamp (AA-2140039-1, unpowered steps 1-2) in MuJoCo 3.14 with two ViperX 300s arms (menagerie aloha).

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_waist, left_shoulder, left_elbow, left_forearm_roll, left_wrist_angle,
                                            #       left_wrist_rotate (joint position targets, rad; wrist_rotate unlimited),
                                            #       left_gripper (finger rail position 0.002 closed .. 0.037 m open), same for right_
        S.step(n)                           # n x 0.625 ms physics steps (+ retention mechanism)
        S.success()                         # dict, 'success' True when the source endpoint criteria hold
Parts (free bodies): stand (with its spring jaw jaw_s1_mount_shade_0 on a slide joint), shade, bulb_E12.
Step 1: press the shade's key down into the socket on top of the stand column (the barb cams the spring
jaw open and it snaps back over the barb). Step 2: thread the bulb up into the shade socket (E12
surrogate, 11.9 mm x 1.5 mm right-hand, shared tools/threads.py convex thread pieces; seats on the socket stop). Non-contact mechanisms: the jaw spring
(slide joint stiffness/damping, as the source's prismatic drive) and the source's retention joints
(welds ret_s1_mount_shade / ret_s2_thread_bulb switched on by svallet_mechanism.SvalletRetention when
the source's seating gates hold). The prewired cable is not built (cable.enabled = false).
Arm TCP sites: left_gripper / right_gripper (between the fingertips). Bases: right_ (screw arm) at x 0.6 on the +x side, left_ (handler) at y -0.43, both on pedestals at bench height,
facing the stand. Task details: task.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
from svallet_mechanism import SvalletRetention
import success as _success

def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=SvalletRetention, monitor=_success.Monitor)
