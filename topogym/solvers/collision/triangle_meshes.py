"""Triangle BVH collision queries, independent of Genesis' sampled SDF."""
import fcl
import numpy as np
import trimesh


class TriangleMeshPair:
    def __init__(self, meshes):
        meshes = tuple(meshes)
        if len(meshes) != 2:
            raise ValueError("TriangleMeshPair requires exactly two meshes")
        self.objects = []
        for mesh in meshes:
            model = fcl.BVHModel()
            model.beginModel(len(mesh.vertices), len(mesh.faces))
            model.addSubModel(np.asarray(mesh.vertices), np.asarray(mesh.faces, dtype=np.int32))
            model.endModel()
            self.objects.append(fcl.CollisionObject(model))

    def clearance(self, poses):
        poses = tuple(poses)
        if len(poses) != 2:
            raise ValueError("Expected two body transforms")
        for obj, pose in zip(self.objects, poses):
            obj.setTransform(fcl.Transform(pose[:3, :3], pose[:3, 3]))
        collision = fcl.collide(*self.objects, fcl.CollisionRequest(), fcl.CollisionResult())
        if collision:
            return -1.0  # Intersection flag, NOT a penetration estimate.
        return float(fcl.distance(*self.objects, fcl.DistanceRequest(), fcl.DistanceResult()))

    def contact_depth(self):
        """Maximum FCL intersecting-triangle contact depth at the last query."""
        result = fcl.CollisionResult()
        fcl.collide(*self.objects, fcl.CollisionRequest(num_max_contacts=10000, enable_contact=True), result)
        if len(result.contacts) >= 10000:
            raise RuntimeError("Triangle contact buffer saturated")
        return max((float(c.penetration_depth) for c in result.contacts), default=0.)


def surface_clearance(positions, faces, obstacle_meshes):
    """Use surfaces, not vertex distances, so crossing triangle interiors fail."""
    manager = trimesh.collision.CollisionManager()
    for name, vertices, triangles in obstacle_meshes:
        manager.add_object(name, trimesh.Trimesh(vertices, triangles, process=False))
    return float(manager.min_distance_single(trimesh.Trimesh(positions, faces, process=False)))
