"""Three independent closed rings joined only by geometric contact."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks._rigid_geometry import RingGeometry, write_ring, world_ring, disk_linking_number


@dataclass(frozen=True)
class ChainProbeLayout:
    ring: RingGeometry = RingGeometry()
    spacing_m: float = .06
    top_height_m: float = .50

    def poses(self):
        return [([0., 0., self.top_height_m-i*self.spacing_m],
                 Rotation.from_euler("xyz", [90,0,0] if i%2==0 else [0,90,0], degrees=True)
                 .as_quat()[[3,0,1,2]].tolist()) for i in range(3)]

    def linking(self, poses):
        rings = [world_ring(self.ring, np.asarray(p), q) for p, q in poses]
        return [disk_linking_number(np.asarray(poses[i][0]), rings[i][1],
                    self.ring.radius_m, rings[i+1][0]) for i in (0,1)]

    def validate(self):
        if not 2*self.ring.tube_radius_m < self.spacing_m < 2*(self.ring.radius_m-self.ring.tube_radius_m):
            raise ValueError("Chain spacing does not leave a linked, nonintersecting initial pose")
        if min(self.spacing_m, 2*self.ring.radius_m-self.spacing_m) <= 2*self.ring.tube_radius_m:
            raise ValueError("Initial ring surfaces overlap")
        if self.top_height_m-2*self.spacing_m-self.ring.radius_m-self.ring.tube_radius_m <= 0:
            raise ValueError("Bottom ring intersects floor")
        if not all(abs(v)==1 for v in self.linking(self.poses())):
            raise ValueError("Initial rings are not linked")


def build_chain_probe(layout, output: Path, dt=.001, substeps=4, render=True, contact_timeconst=.001, renderer="nyx"):
    import genesis as gs
    from topogym.core import EntityManifest
    from topogym.world.presentation import add_preview_camera
    layout.validate()
    scene = gs.Scene(show_viewer=False, sim_options=gs.options.SimOptions(
        dt=dt, substeps=substeps, gravity=(0,0,-9.81)),
        rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
            iterations=100, max_collision_pairs=512, constraint_timeconst=contact_timeconst))
    scene.add_entity(gs.morphs.Plane(), material=gs.materials.Rigid(friction=.3))
    # The top link is an explicit fixed fixture. Other links have six free DOFs.
    scene.add_entity(gs.morphs.Box(pos=(0,0,.59), size=(.16,.025,.02), fixed=True),
                     surface=gs.surfaces.Plastic(color=(.35,.38,.4)))
    scene.add_entity(gs.morphs.Box(pos=(0,0,.565), size=(.012,.012,.05), fixed=True),
                     surface=gs.surfaces.Plastic(color=(.35,.38,.4)))
    rings, metadata = [], []
    for i, (pos, quat) in enumerate(layout.poses()):
        path = output / "assets" / f"ring_{i}.urdf"
        metadata.append(write_ring(path, layout.ring,
            ((.8,.55,.18,1),(.2,.55,.75,1),(.7,.25,.2,1))[i]))
        rings.append(scene.add_entity(gs.morphs.URDF(file=str(path.resolve()), pos=pos,
            quat=quat, fixed=i==0, align=False, merge_fixed_links=False, convexify=True,
            decimate=False), material=gs.materials.Rigid(friction=.3), name=f"chain_link_{i}"))
    camera = add_preview_camera(scene, EntityManifest(), res=(800,600), pos=(.42,-.65,.52),
                                lookat=(0,0,.42), fov=36, renderer=renderer) if render else None
    scene.build()
    return scene, rings, camera, metadata
