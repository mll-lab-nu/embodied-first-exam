"""Triangle-surface clearance for the blanket's unassisted gravity phase."""
import numpy as np
import trimesh


def surface_clearance(positions, faces, robot_meshes):
    """Use surfaces, not vertex distances, so crossing triangle interiors fail."""
    manager = trimesh.collision.CollisionManager()
    for name, vertices, triangles in robot_meshes:
        manager.add_object(name, trimesh.Trimesh(vertices, triangles, process=False))
    return float(manager.min_distance_single(trimesh.Trimesh(positions, faces, process=False)))


def robot_clearance(robot, positions, faces):
    meshes = [(str(geom.idx), geom.get_verts().detach().cpu().numpy(), np.asarray(geom.mesh.faces))
              for geom in robot.geoms if len(geom.mesh.faces)]
    if not meshes:
        raise ValueError('No robot collision meshes available for birth clearance audit')
    return surface_clearance(positions, faces, meshes)
