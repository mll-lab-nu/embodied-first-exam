"""Robot kinematics queries delegated to Genesis; no task, motion or clock."""
from __future__ import annotations

import numpy as np
from contextlib import contextmanager
from copy import deepcopy
import random
from topogym.utils.arrays import to_numpy


def prepare_kinematics(entity, link=None):
    """Allocate Genesis 1.2.1 FK/IK scratch through a stationary public IK query.

    Genesis FK uses fields allocated only by IK. Prepare them before the initial
    World checkpoint so later queries cannot introduce uncheckpointed buffers.
    The candidate is discarded; no controller command or physical tick occurs.
    """
    if getattr(entity, "_IK_mat", None) is not None:
        return
    link = entity.links[-1] if link is None else link
    with _query_state(entity):
        entity.inverse_kinematics(
            link=link, pos=to_numpy(link.get_pos()).reshape(-1, 3)[0],
            quat=to_numpy(link.get_quat()).reshape(-1, 4)[0],
            init_qpos=entity.get_qpos(), max_samples=1, max_solver_iters=1,
        )


@contextmanager
def _query_state(entity):
    """Preserve RNG and Genesis query scratch fields on success and rejection."""
    import torch
    host = random.getstate(), deepcopy(np.random.get_state())
    tensor = torch.get_rng_state().clone()
    cuda = [state.clone() for state in torch.cuda.get_rng_state_all()] if torch.cuda.is_initialized() else []
    fields = [(value, value.to_numpy()) for name, value in vars(entity).items()
              if (name.startswith("_IK_") or name == "_jacobian") and callable(getattr(value, "to_numpy", None))
              and callable(getattr(value, "from_numpy", None))]
    try:
        yield
    finally:
        for field, value in fields:
            field.from_numpy(value)
        random.setstate(host[0]); np.random.set_state(host[1])
        torch.set_rng_state(tensor)
        if cuda:
            torch.cuda.set_rng_state_all(cuda)


class GenesisIKSolver:
    def __init__(self, entity):
        self.entity = entity

    def solve_checked(self, *, position_tolerance_m=1e-4, orientation_tolerance_rad=1e-3, **kwargs):
        """Reject unreachable poses; finite IK output alone is not a solution."""
        prepare_kinematics(self.entity, self.entity.get_link(kwargs["link_name"]))
        with _query_state(self.entity):
            return self._checked(position_tolerance_m, orientation_tolerance_rad, kwargs)

    def _checked(self, position_tolerance_m, orientation_tolerance_rad, kwargs):
        from scipy.spatial.transform import Rotation
        candidate = self.solve(**kwargs)
        if not np.isfinite(candidate).all():
            raise ValueError("IK produced a non-finite candidate")
        pose = GenesisFKSolver(self.entity).solve(candidate)
        link = self.entity.get_link(kwargs["link_name"])
        actual_position = pose["position_world_m"].reshape(-1, 3)[link.idx_local]
        residual = np.linalg.norm(actual_position - kwargs["position_world_m"])
        orientation = kwargs.get("orientation_wxyz")
        angle = 0.
        if orientation is not None:
            actual = pose["orientation_wxyz"].reshape(-1, 4)[link.idx_local]
            angle = (Rotation.from_quat(actual[[1, 2, 3, 0]]).inv() *
                     Rotation.from_quat(np.asarray(orientation)[[1, 2, 3, 0]])).magnitude()
        if residual > position_tolerance_m or angle > orientation_tolerance_rad:
            raise ValueError(f"Unreachable EE pose: position residual={residual:.6g} m, orientation={angle:.6g} rad")
        return candidate

    def solve(self, *, link_name, position_world_m, orientation_wxyz=None,
              joint_dof_indices=None, initial_qpos=None, max_solver_iterations=100):
        position = np.asarray(position_world_m, dtype=float)
        if position.shape != (3,) or not np.isfinite(position).all():
            raise ValueError("IK position must contain three finite world coordinates")
        if (isinstance(max_solver_iterations, bool) or not isinstance(max_solver_iterations, (int, np.integer))
                or max_solver_iterations < 1):
            raise ValueError("max_solver_iterations must be a positive integer")
        options = dict(link=self.entity.get_link(link_name), pos=position,
                       init_qpos=self.entity.get_qpos() if initial_qpos is None else initial_qpos,
                       max_samples=1, max_solver_iters=int(max_solver_iterations),
                       pos_tol=1e-5, rot_tol=1e-4)
        if orientation_wxyz is not None:
            quat = np.asarray(orientation_wxyz, dtype=float)
            if quat.shape != (4,) or not np.isfinite(quat).all() or not np.isclose(np.linalg.norm(quat), 1.):
                raise ValueError("IK orientation requires a unit wxyz quaternion")
            options["quat"] = quat
        if joint_dof_indices is not None:
            options["dofs_idx_local"] = list(joint_dof_indices)
        # Genesis returns a candidate. This method never sends that candidate
        # to a controller or advances simulation; callers assess residuals.
        return to_numpy(self.entity.inverse_kinematics(**options)).reshape(-1, int(self.entity.n_qs))[0]


class GenesisFKSolver:
    def __init__(self, entity):
        self.entity = entity

    def solve(self, qpos):
        q = np.asarray(qpos, dtype=float)
        if q.shape != (int(self.entity.n_qs),) or not np.isfinite(q).all():
            raise ValueError("FK requires one finite position for every robot q coordinate")
        prepare_kinematics(self.entity)
        with _query_state(self.entity):
            positions, quaternions = self.entity.forward_kinematics(q)
        return dict(position_world_m=to_numpy(positions), orientation_wxyz=to_numpy(quaternions))
