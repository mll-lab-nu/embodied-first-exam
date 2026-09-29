"""Static pin/slot evidence only; URDF joint limits do not drive these queries."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pytest
import trimesh
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation
from topogym.assets.geometry.lock_picking import LockGeometry, write_disc
from topogym.solvers.collision.triangle_meshes import TriangleMeshPair


@pytest.mark.parametrize("bounds,scale", [((-15,35),1.),((-10,75),.75),((-180,180),1.)])
def test_generated_collision_pin_is_blocked_at_slot_ends(tmp_path,bounds,scale):
    g = LockGeometry(disc_radius=.08*scale)
    stop = OmegaConf.create(dict(style="single_ring",bounds_deg=list(bounds),ear_phase_deg=-35))
    path = write_disc(g,g.slots[0],tmp_path/"disc",.15,.02,(.4,.3,.6),stop=stop)
    tree = ET.parse(path)
    joint = tree.find(".//joint[@name='disc_hinge']")
    continuous = bounds[1]-bounds[0] == 360
    assert joint.get("type") == ("continuous" if continuous else "revolute")
    assert joint.find("axis").get("xyz") == "-1 0 0"
    def meshes(urdf):
        return [(Path(n.get("filename")).name,trimesh.load(n.get("filename"),force="mesh",process=False))
                for n in ET.parse(urdf).findall(".//collision/geometry/mesh")]
    pin = [m for name,m in meshes(path) if name.endswith("_pin.obj")]
    assert len(pin) == 1
    frame = trimesh.util.concatenate([m for _,m in meshes(path.parent/"limits"/"stop_frame.urdf")])
    query = TriangleMeshPair((frame,pin[0]))
    lo,hi = bounds
    angles = [-360,-90,0,90,360] if continuous else [lo-1,lo+1,(lo+hi)/2,hi-1,hi+1]
    for angle in angles:
        pose = np.eye(4)
        pose[:3,:3] = Rotation.from_euler("x",-angle,degrees=True).as_matrix()
        intersects = query.clearance((np.eye(4),pose)) < 0
        assert intersects == (not continuous and not lo <= angle <= hi)
