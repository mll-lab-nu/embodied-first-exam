"""Read-only ALOHA planning with the actual, nonconvex threading fixtures."""
import fcl
import numpy as np
from topogym.planning.knot_untying.kinematics import KnotIK, vertical_pinch, CONTACT_IN_TCP_M
from topogym.planning.buzz_wire_3d.kinematics import manager, distance
from topogym.utils.arrays import to_numpy


class ThreadingIK(KnotIK):
    def __init__(self, env):
        super().__init__(env._world, env._robot, env._task.table_height_m)
        objects = []
        for name, entity in env._world.entities.items():
            if name in {'robot', 'table', 'rope'}:
                continue
            for link in entity.links:
                for geom in link.geoms:
                    # A convex hull would fill the ring aperture and reject
                    # the intended threading path. Preserve its triangles.
                    vertices = to_numpy(geom.get_verts()).reshape(-1, 3)
                    faces = np.asarray(geom.init_faces)
                    model = fcl.BVHModel()
                    model.beginModel(len(vertices), len(faces))
                    model.addSubModel(vertices, faces)
                    model.endModel()
                    objects.append(fcl.CollisionObject(model))
        self.fixtures = manager(objects)
        self.moving = manager([row[4] for row in self.shapes
                               if row[1].rsplit('/', 1)[-1] != 'base_link'])

    def check(self, q):
        result = super().check(q)
        if 'same_arm_collision' in result['issues']:
            result['self_collision_pairs'] = [(a[1], b[1]) for a, b in self.self_pairs
                if fcl.collide(a[2], b[2], fcl.CollisionRequest(), fcl.CollisionResult())]
        self.moving.update()
        gap = float(distance(self.moving, self.fixtures))
        if gap < .0005:
            result['issues'].append('ring_or_support')
        result.update(fixture_clearance_m=gap, passed=not result['issues'])
        return result
