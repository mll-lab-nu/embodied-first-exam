"""Read actual declared finger collision surfaces; never issue robot commands."""
import numpy as np
from topogym.utils.arrays import to_numpy


def read_grasp_geometry(robot, hand):
    group = robot.groups[hand]
    if group.grasp is None:
        raise ValueError(f"Missing bilateral grasp description: {hand}")
    parent = robot.entity.get_link(group.hand_link)
    surfaces = []
    for name in group.grasp.finger_links:
        link = robot.entity.get_link(name)
        vertices, faces, offset = [], [], 0
        for geom in link.geoms:
            v = to_numpy(geom.get_verts()).reshape(-1, 3)
            f = np.asarray(geom.init_faces, dtype=int).reshape(-1, 3)
            vertices.append(v)
            faces.append(f + offset)
            offset += len(v)
        if not vertices or not sum(len(f) for f in faces):
            raise ValueError(f"No collision surface for grasp finger {name}")
        surfaces.append((np.concatenate(vertices), np.concatenate(faces)))
    return dict(position=to_numpy(parent.get_pos()).reshape(3),
                quaternion=to_numpy(parent.get_quat()).reshape(4), surfaces=surfaces)
