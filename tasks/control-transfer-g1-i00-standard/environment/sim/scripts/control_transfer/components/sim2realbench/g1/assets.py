from control_assets import ROOT, check
from pathlib import Path
import hashlib

COMMIT = "1425b15f73bd4095f0df53709d7c389c3eb9e790"
UPSTREAM = ROOT / "unitree_rl_mjlab"
SCENE = UPSTREAM / "src/assets/robots/unitree_g1/xmls/scene_g1.xml"
POLICY = ROOT / "reference/g1.npz"


def verify():
    return check("unitree_rl_mjlab/src/assets/robots/unitree_g1")


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
