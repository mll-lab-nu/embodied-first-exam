"""IKEA VESKEN shelf unit (AA-1842283-5), body steps 1-8, in MuJoCo 3.14 with two Franka Panda arms.

Load:   import scene; S = scene.load()      # run with this directory on sys.path (or importlib)
        S.model, S.data                     # MuJoCo model/data, reset to keyframe 'home'
        S.data.ctrl[...] = ...              # arms: left_actuator1..7 (joint position targets, rad),
                                            #       left_actuator8 gripper (0 closed .. 255 open), same for right_
        S.step(n)                           # n x 1 ms physics steps (+ retention mechanism)
        S.success()                         # dict, 'success' True when the source endpoint holds
Parts (free bodies, source names): tray_0..3, foot_0..3, column_<level>_<corner> (12), cap_0..3.
Operations (task.json, source order, each depends on the previous):
  s1 feet into tray_0 from BELOW (outward -z), s2 columns into tray_0, s3 tray_1 onto columns,
  s4/s5 next level, s6/s7 top level, s8 caps into tray_3.
Mechanisms that are not plain contact:
  * 32 spring jaws: child bodies of their host with a slide joint (source prismatic drive:
    1200 N/m, 0.8 N s/m, 2.5 mm travel). The hooked snap pins deflect them by contact.
  * 23 retention welds conn_<op>: switched on by vesken_mechanism.VeskenMechanism when the source
    acceptance gates hold for 0.15 s (snap passed, jaw returned, seated, at rest).
Arm TCP sites: left_tcp / right_tcp (fingertip centre). Details: task.json, layout.json.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from ikea_runtime import Scene
from vesken_mechanism import VeskenMechanism
import success as _success

def load(keyframe='home'):
    return Scene(HERE, keyframe=keyframe, mechanism=VeskenMechanism, monitor=_success.Monitor)
