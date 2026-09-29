"""Synthetic measurements: these are not physical success demonstrations."""
import numpy as np
from topogym.utils.geometry.regions import GoalRegion


def body(position=(0.,0.,0.), quaternion=(1.,0.,0.,0.)):
    return dict(position_m=np.array(position, float), quaternion_wxyz=np.array(quaternion, float),
                linear_velocity_m_s=np.zeros(3), angular_velocity_rad_s=np.zeros(3))


def soft(points):
    points = np.asarray(points, float)
    return dict(position_m=points.copy(), velocity_m_s=np.zeros_like(points),
                material_s_m=np.arange(len(points), dtype=float))


def ipc(soft_names=("rope",), attachments=()):
    return dict(native_valid=True, volume_ratio={n:dict(minimum=1., maximum=1.) for n in soft_names},
                attachment_residual_m={n:0. for n in attachments})


def region():
    return GoalRegion((1.,0.), (.2,.2), .75, .15, (1.,0.), .5, boundary_margin_m=.001)


def placement(task, targets, remainder, *, soft_names=(), attachments=()):
    task.placement_targets, task.placement_remainder = targets, remainder
    task.placement_vertices = {n:np.array([[-.02,-.02,0.],[.02,.02,.04]])
                               for n in (*targets,*remainder) if n not in soft_names}
    state = dict(bodies={n:body((1. if n in targets else 0.,0.,.75)) for n in task.placement_vertices},
                 fem={n:soft([[1. if n in targets else 0., 0., .77],
                              [1.01 if n in targets else .01, 0., .77]]) for n in soft_names},
                 ipc=ipc(soft_names,attachments), physics_step=1)
    return state
