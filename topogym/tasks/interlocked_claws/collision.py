"""Triangle BVH collision queries, independent of Genesis' sampled SDF."""
import fcl
import numpy as np


class ClawCollision:
    def __init__(self, assembly):
        self.objects = []
        for body in assembly.bodies:
            model = fcl.BVHModel()
            model.beginModel(len(body.mesh.vertices), len(body.mesh.faces))
            model.addSubModel(np.asarray(body.mesh.vertices), np.asarray(body.mesh.faces, dtype=np.int32))
            model.endModel()
            self.objects.append(fcl.CollisionObject(model))

    def clearance(self, poses):
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
