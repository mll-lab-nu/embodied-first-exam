"""Independent FCL queries on imported collision pieces at measured poses.

No convex hull is taken across a rotor aperture: each original collision piece
is represented separately. Passive Robotiq links use their measured poses.
"""
import fcl
import numpy as np

from topogym.planning.buzz_wire_3d.kinematics import mesh_object, manager, distance
from topogym.utils.arrays import to_numpy
from .lock_picking_medium_planning import rotation


class LockRobotGeometry:
    def __init__(self, env):
        world = env._world.read_state()
        self.parts, self.names = [], {}
        self.robot, self.nonfinger, self.fingers, self.fixture, self.key, self.nonhandle = [], [], [], [], [], []
        fingers = set(env._robot.groups["arm"].grasp.finger_links)
        for name, entity in env._world.entities.items():
            for link in entity.links:
                body = world["articulations"][name]["links"][link.name]
                p, r = np.asarray(body["position_m"]), rotation(body["quaternion_wxyz"])
                for geom in link.geoms:
                    if not geom.contype and not geom.conaffinity:
                        continue
                    vertices = r.inv().apply(to_numpy(geom.get_verts()).reshape(-1,3)-p)
                    # Imported rigid pieces are convex; fail instead of bridging
                    # a future concave hole with a single convex hull.
                    if not geom.is_convex:
                        raise ValueError(f"Nonconvex imported collision piece: {name}/{link.name}")
                    obj = mesh_object(vertices, geom.init_faces)
                    label = f"{name}/{link.name}/{geom.idx}"
                    self.names[id(obj)] = label
                    self.parts.append((name, link.name, obj))
                    if name == "robot":
                        if link.name != "link0":
                            self.robot.append((link.idx_local, obj))
                            (self.fingers if link.name in fingers else self.nonfinger).append(obj)
                    elif name == "lock_key":
                        self.key.append(obj)
                        center = vertices.mean(axis=0)
                        radial = np.linalg.norm(vertices[:,1:], axis=1).max()
                        handle = abs(center[0]+env._task.layout.grip_offset) < .003 and radial > .017
                        if not handle:
                            self.nonhandle.append(obj)
                    else:
                        self.fixture.append(obj)
        self.robot_manager = manager([obj for _, obj in self.robot])
        self.nonfinger_manager = manager(self.nonfinger)
        self.finger_manager = manager(self.fingers)
        self.fixture_manager = manager(self.fixture)
        self.key_manager = manager(self.key)
        self.nonhandle_manager = manager(self.nonhandle)
        if not self.nonhandle or len(self.nonhandle) >= len(self.key):
            raise ValueError("Failed to distinguish the authored handle from shaft/tabs")
        self.self_pairs = []
        for i, (a, first) in enumerate(self.robot):
            for b, second in self.robot[i+1:]:
                if a == b or (a < 8 and b < 8 and abs(a-b) <= 2) or min(a,b) >= 6:
                    continue
                self.self_pairs.append((first, second))
        self.scope = dict(imported_collision_pieces=len(self.parts),
            self_pairs=len(self.self_pairs), key_pieces=len(self.key), nonhandle_pieces=len(self.nonhandle),
            passive_fingers="actual per-link recorded poses; no driver-angle reconstruction",
            self_exclusions="same link; arm links within two indices; wrist/tool mating and internal gripper pairs (both indices >=6)",
            table_mount_exclusion="robot/link0 only", intentional_contact="finger links against handle only",
            coverage="all saved World ticks; not continuous time or every solver substep")

    def check(self, world):
        for entity, link, obj in self.parts:
            body = world["articulations"][entity]["links"][link]
            obj.setTransform(fcl.Transform(rotation(body["quaternion_wxyz"]).as_matrix(), body["position_m"]))
        for group in (self.robot_manager, self.nonfinger_manager, self.finger_manager,
                      self.fixture_manager, self.key_manager, self.nonhandle_manager):
            group.update()
        return dict(robot_fixture_m=distance(self.robot_manager, self.fixture_manager),
            nonfinger_key_m=distance(self.nonfinger_manager, self.key_manager),
            finger_nonhandle_m=distance(self.finger_manager, self.nonhandle_manager),
            nonadjacent_arm_self_m=min(float(fcl.distance(a,b,fcl.DistanceRequest(),fcl.DistanceResult()))
                                      for a,b in self.self_pairs))

    def collision_pairs(self):
        pairs = []
        # Diagnostics only, on a rejected pose. Avoid an all-pairs loop during
        # accepted broadphase queries.
        for label, first, second in (
            ("robot_fixture", [o for _,o in self.robot], self.fixture),
            ("nonfinger_key", self.nonfinger, self.key),
            ("finger_nonhandle", self.fingers, self.nonhandle)):
            for a in first:
                for b in second:
                    if fcl.collide(a,b,fcl.CollisionRequest(),fcl.CollisionResult()):
                        pairs.append(dict(kind=label, a=self.names[id(a)], b=self.names[id(b)]))
                        if len(pairs) >= 20:
                            return pairs
        return pairs
