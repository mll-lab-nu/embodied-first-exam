"""Pure host FK for Knot command checks, using Genesis' authored chain data.

Adapted from the v14 tooling's _ChainFK. Native forward_kinematics restores qpos
but recomputes live solver fields. This implementation copies constants once;
queries retain no entity or solver reference and never launch a physics kernel.
Only a single, fixed-root revolute/prismatic/fixed chain is supported.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation


class StaticChainFK:
    def __init__(self, entity):
        import genesis as gs

        solver = entity._solver
        if solver.n_envs not in (0, 1):
            raise ValueError('Knot command FK requires one environment')
        self.l0, self.l1 = int(entity.link_start), int(entity.link_end)
        self.q0, self.nq = int(entity.q_start), int(entity.n_qs)

        def read(field, width=0):
            value = np.asarray(field.to_numpy(), dtype=float)
            value = (value.reshape(value.shape[0], -1, width)[:, 0, :] if width
                     else value.reshape(value.shape[0], -1)[:, 0])
            return value.copy()

        links, joints, dofs = solver.links_info, solver.joints_info, solver.dofs_info
        self.lpos, self.lquat = read(links.pos, 3), read(links.quat, 4)
        self.parent = read(links.parent_idx).astype(int)
        fixed = read(links.is_fixed).astype(bool)
        self.jstart, self.jend = read(links.joint_start).astype(int), read(links.joint_end).astype(int)
        self.jtype, self.jq = read(joints.type).astype(int), read(joints.q_start).astype(int)
        self.jdof, self.jpos = read(joints.dof_start).astype(int), read(joints.pos, 3)
        self.mang, self.mvel = read(dofs.motion_ang, 3), read(dofs.motion_vel, 3)
        self.qpos0 = read(solver._rigid_global_info.qpos0)
        root_pos, root_quat = read(solver.links_state.pos, 3), read(solver.links_state.quat, 4)
        self.root = {}
        self.types = tuple(int(getattr(gs.JOINT_TYPE, kind)) for kind in ('FIXED', 'REVOLUTE', 'PRISMATIC'))
        for i in range(self.l0, self.l1):
            parent = self.parent[i]
            if parent == -1:
                if not fixed[i]:
                    raise ValueError('Knot command FK requires a fixed root')
                self.root[i] = root_pos[i].copy(), root_quat[i].copy()
            elif not self.l0 <= parent < i:
                raise ValueError('Unsupported robot link ordering or external parent')
            if not all(kind in self.types for kind in self.jtype[self.jstart[i]:self.jend[i]]):
                raise ValueError('Unsupported robot joint type')
        if not self.root:
            raise ValueError('Missing fixed robot root')

    @staticmethod
    def rotation(wxyz):
        return Rotation.from_quat(np.asarray(wxyz)[[1, 2, 3, 0]])

    def solve(self, qpos):
        qpos = np.asarray(qpos, float)
        if qpos.shape != (self.nq,) or not np.isfinite(qpos).all():
            raise ValueError('FK requires all finite robot q coordinates')
        q = self.qpos0.copy()
        q[self.q0:self.q0+self.nq] = qpos
        fixed, revolute, prismatic = self.types
        positions, turns = {}, {}
        for i in range(self.l0, self.l1):
            if i in self.root:
                pos, quat = self.root[i]
                turn = self.rotation(quat)
            else:
                parent = self.parent[i]
                turn = turns[parent]*self.rotation(self.lquat[i])
                pos = positions[parent]+turns[parent].apply(self.lpos[i])
                for j in range(self.jstart[i], self.jend[i]):
                    kind = self.jtype[j]
                    if kind == fixed:
                        continue
                    angle = q[self.jq[j]]-self.qpos0[self.jq[j]]
                    if kind == revolute:
                        anchor = pos+turn.apply(self.jpos[j])
                        turn = turn*Rotation.from_rotvec(self.mang[self.jdof[j]]*angle)
                        pos = anchor-turn.apply(self.jpos[j])
                    elif kind == prismatic:
                        pos = pos+turn.apply(self.mvel[self.jdof[j]])*angle
            positions[i], turns[i] = pos, turn
        return dict(position_world_m=np.stack([positions[i] for i in range(self.l0, self.l1)]),
                    orientation_wxyz=np.stack([turns[i].as_quat()[[3, 0, 1, 2]] for i in range(self.l0, self.l1)]))
