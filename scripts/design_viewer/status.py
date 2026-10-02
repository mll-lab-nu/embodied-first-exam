"""One geometric status line per scene; the viewer refreshes it every 0.5 s.

hedgehog:  ball inside / N% out / OUT of the cage's convex hull (+5 mm), gripper-cage contacts
horseshoe: chain links intact (|linking| = 1) and which bodies pass through the target ring's bore
slotted:   which bodies (and how many cord segments) pass through the ring's bore
"Ring off" means no mesh edge of any other body, and no cord segment, crosses the ring's bore.
"""
from dataclasses import replace

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from scripts.design_viewer import mjcf

OUT_MARGIN = .005


def _crossings(a, b, bore):
    """Segments a->b (ring frame, ring in the z = 0 plane) crossing inside the bore ellipse."""
    cross = (a[:, 2] <= 0) != (b[:, 2] <= 0)
    a, b = a[cross], b[cross]
    hit = a+(a[:, 2]/(a[:, 2]-b[:, 2]))[:, None]*(b-a)
    return int((np.sum((hit[:, :2]/bore)**2, axis=1) < 1).sum())


def _pose(model, data, body):
    b = model.body(body).id
    return data.xpos[b], Rotation.from_quat(data.xquat[b][[1, 2, 3, 0]])


class Status:
    def __init__(self, scene, model):
        self.scene, self.model = scene, model
        if scene.task_id == "hedgehog_in_cage":
            cage = scene.body("cage")
            hull = trimesh.util.concatenate([p.copy().apply_translation(cage.pos) for p in cage.collision]).convex_hull
            self.normals = hull.face_normals
            self.offsets = np.einsum("ij,ij->i", hull.face_normals, hull.vertices[hull.faces[:, 0]])
            self.ball = trimesh.util.concatenate(scene.body("ball").collision).vertices
            return
        if scene.task_id == "horseshoe_ring":
            ring = scene.extras["loops"]["target_ring"]
            self.ring = (ring.center-scene.extras["origins"]["target_ring"], ring.rotation,
                         ring.radii*(1-ring.wire_radius/min(ring.radii)))
        else:
            layout = scene.extras["layout"]
            self.ring = (np.zeros(3), Rotation.identity(), np.full(2, layout.ring_major_radius_m-layout.ring_tube_radius_m))
        self.others = [(b.name, b.visual.vertices, b.visual.edges_unique) for b in scene.bodies if b.name != "target_ring"]

    def __call__(self, data):
        return getattr(self, "_"+self.scene.task_id.split("_")[0])(data)

    def _hedgehog(self, data):
        pos, rot = _pose(self.model, data, "ball")
        outside = ((rot.apply(self.ball)+pos)@self.normals.T-self.offsets).max(axis=1) > OUT_MARGIN
        # Easy spikes already poke out of the windows at the start, hence a percentage.
        where = "OUT" if outside.all() else f"{outside.mean():.0%} out" if outside.any() else "inside"
        m, cage = self.model, self.model.body("cage").id
        touching = sum(1 for c in data.contact[:data.ncon]
                       if cage in (m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2])
                       and mjcf.GRIPPER in (m.geom_contype[c.geom1], m.geom_contype[c.geom2]))
        return (f"ball {where} | gripper-cage contacts {touching} | "
                f"max penetration {mjcf.penetration(m, data)*1e3:.1f} mm")

    def _through(self, data):
        """Names of bodies threading the ring, and the ring frame transform for further points."""
        pos, rot = _pose(self.model, data, "target_ring")
        offset, local, bore = self.ring
        centre, frame = pos+rot.apply(offset), rot*local

        def to_ring(points):
            return frame.inv().apply(points-centre)
        names = []
        for name, vertices, edges in self.others:
            p, r = _pose(self.model, data, name)
            v = to_ring(r.apply(vertices)+p)
            if _crossings(v[edges[:, 0]], v[edges[:, 1]], bore):
                names.append(name)
        return names, to_ring, bore

    def _horseshoe(self, data):
        origins, loops = self.scene.extras["origins"], {}
        for name, loop in self.scene.extras["loops"].items():
            pos, rot = _pose(self.model, data, loop.body)
            loops[name] = replace(loop, center=pos+rot.apply(loop.center-origins[loop.body]), rotation=rot*loop.rotation)
        intact = all(abs(loops[a].linking(loops[b])) == 1 for a, b in self.scene.extras["edges"])
        names, _, _ = self._through(data)
        return f"chain {'intact' if intact else 'BROKEN'} | through ring: {', '.join(names) or 'nothing - ring off'}"

    def _slotted(self, data):
        names, to_ring, bore = self._through(data)
        cord = to_ring(mjcf.cord_points(self.model, data))
        crossings = _crossings(cord[:-1], cord[1:], bore)
        names += [f"cord x{crossings}"] if crossings else []
        return f"through ring: {', '.join(names) or 'nothing - ring off'}"
