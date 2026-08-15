"""FEM + IPC rope backend.

The implementations here are the vertical slice's, verified 2026-08-06
(run15~20): material and contact values from the spike calibration, end
constraints from ``genesis_ipc_vertex_constraints`` (per-vertex ``is_fixed``
for anchors, ``SoftPositionConstraint`` + animator for the follow band).

``follow_link`` reproduces ``fix_particles_to_link``'s semantics -- the band
is carried by the link, rotation included -- by capturing each band vertex's
offset in the link's local frame at engage time and writing
``link_pos + R(link_quat) @ offset`` into the band's constraint targets before
every ``scene.step`` (a step-wrapper, the same pattern ``recording_session``
and ``StepProbe`` use). No position is ever written into the solver: the
targets enter IPC's Newton solve next to the contact barrier, which is the
property this backend exists for.

Config: material and contact knobs come from the task's ``rope.fem`` block,
whose single source is ``prefabs.rope_fem`` in
``configs/prefab_configs/topogym_prefabs_v1.yaml`` (spike-calibrated; rest
crossing gap 9.66mm of the 10mm target at those values). The block is required,
not optional -- see `_fem_value`.
"""

from __future__ import annotations

import numpy as np

from topogym.world import genesis_ipc_vertex_constraints as vc
from topogym.world.rope import tensor_to_numpy

def _fem_value(rope_cfg, key: str) -> float:
    """One material or contact value from the task's ``rope.fem`` block.

    These used to be a `_DEFAULTS` dict here, with the config block optional and
    falling back to it. Two of them (`contact_d_hat`, `follow_strength`) then had
    no command-line flag either, so the only way to change them was to edit this
    file -- and no run recorded which values it had used. They live in
    ``configs/prefab_configs/topogym_prefabs_v1.yaml`` under ``rope_fem`` now,
    and every task config that selects ``rope.model: fem_ipc_tube`` refers to it.

    Missing keys raise rather than fall back: a silent default is what made the
    values invisible in the first place.
    """

    fem_cfg = getattr(rope_cfg, "fem", None)
    if fem_cfg is None:
        raise ValueError(
            "rope.model is 'fem_ipc_tube' but the task config has no rope.fem block. "
            "Add one referring to ${prefabs.rope_fem.*}."
        )
    value = getattr(fem_cfg, key, None)
    if value is None:
        raise ValueError(
            f"rope.fem.{key} is missing. Every key in prefabs.rope_fem must be "
            f"referred to by the task's rope.fem block."
        )
    return float(value)


def _quat_to_mat(quat: np.ndarray) -> np.ndarray:
    """Genesis (w, x, y, z) quaternion to rotation matrix."""

    w, x, y, z = (float(v) for v in np.asarray(quat, dtype=float).reshape(4))
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


class _FollowSync:
    """Write link-carried targets into every engaged follow band, pre-step."""

    def __init__(self, swivel: bool = False) -> None:
        self._entries: list[tuple] = []  # (handle, link, local_offsets, entity)
        self._scene = None
        self._swivel = bool(swivel)
        # How far each band has let the rope's end turn, accumulated. Kept
        # because the fitted angle is otherwise computed and thrown away every
        # step, which left "is the band actually yielding?" unanswerable -- and
        # on 2026-08-14 that was the question holding up the twist work.
        self._turned: list[float] = []
        self._last_angle: list[float | None] = []

    def add(self, scene, handle, link, local_offsets: np.ndarray, entity) -> None:
        self._entries.append((handle, link, local_offsets, entity))
        self._turned.append(0.0)
        self._last_angle.append(None)
        if self._scene is None:
            self._scene = scene
            original = scene.step

            def step_with_follow_sync(*args, **kwargs):
                self.sync()
                return original(*args, **kwargs)

            scene.step = step_with_follow_sync

    def sync(self) -> None:
        for index, (handle, link, local_offsets, entity) in enumerate(self._entries):
            link_pos = np.asarray(tensor_to_numpy(link.get_pos()), dtype=float).reshape(3)
            rotation = _quat_to_mat(tensor_to_numpy(link.get_quat()))
            offsets = (
                self._spun(index, local_offsets, entity, handle, link_pos, rotation)
                if self._swivel
                else local_offsets
            )
            handle.update_targets(link_pos[None, :] + offsets @ rotation.T)

    def turned_turns(self) -> list[float]:
        """Accumulated swivel per band, in turns, in declaration order.

        Zero everywhere means the bands are not yielding -- either the swivel is
        off, or `_spun` is failing to fit. A band that is doing its job on a
        winding route reads roughly one turn per orbit.
        """

        return [value / (2.0 * np.pi) for value in self._turned]

    def _spun(self, index, local_offsets, entity, handle, link_pos, rotation) -> np.ndarray:
        """Re-aim the band at the rope's OWN azimuth instead of the link's.

        Without this the band is a torsional clamp: it fixes where every node of
        the rope's end sits around the cross section, so the end cannot turn
        relative to the fitting. With both ends clamped, winding the rope around
        a post pumps in one full turn of twist per orbit and the twist has
        nowhere to go -- the rope arrives wrung out.

        Here the band still fixes the end's position along and across the axis;
        it just yields about it. One rigid angle is fitted for the whole band
        (not per node, which would let the ring shear), by the best rotation
        about the fitting's axis taking the material offsets onto the current
        ones. The complex product weights each node by its radius, so nodes near
        the axis -- whose azimuth means nothing -- barely count.

        Assumes the band's axis is the fitting's local +z, which is how both the
        plug and the fixed terminal are built (the rope runs up their bore).
        """

        nodes = tensor_to_numpy(entity.get_state().pos)
        if nodes.ndim == 3:
            nodes = nodes[0]
        current = np.asarray(nodes[handle.verts], dtype=float) - link_pos[None, :]
        current = current @ rotation  # world -> fitting frame
        material = local_offsets[:, 0] + 1j * local_offsets[:, 1]
        actual = current[:, 0] + 1j * current[:, 1]
        total = complex(np.sum(actual * np.conjugate(material)))
        if not np.isfinite(total.real) or abs(total) < 1e-18:
            return local_offsets
        angle = float(np.angle(total))
        # Accumulate the fit, unwrapped in TIME. `np.angle` only ever returns
        # (-pi, pi], so a band that has let the end round past half a turn reads
        # as if it had turned back -- the same aliasing that made the old spatial
        # twist measure unusable. Only the running total is meaningful.
        previous = self._last_angle[index]
        if previous is not None:
            step = angle - previous
            self._turned[index] += float(np.arctan2(np.sin(step), np.cos(step)))
        self._last_angle[index] = angle
        cos_a, sin_a = float(np.cos(angle)), float(np.sin(angle))
        spun = np.array(local_offsets, dtype=float, copy=True)
        spun[:, 0] = cos_a * local_offsets[:, 0] - sin_a * local_offsets[:, 1]
        spun[:, 1] = sin_a * local_offsets[:, 0] + cos_a * local_offsets[:, 1]
        return spun


class FemIpcRopeBackend:
    name = "fem_ipc"

    def __init__(self, rope_cfg) -> None:
        self.rope_cfg = rope_cfg
        self._follow_handles: dict[str, list[vc.FollowHandle]] = {}
        fem_cfg = getattr(rope_cfg, "fem", None)
        self._follow_sync = _FollowSync(
            swivel=bool(getattr(fem_cfg, "follow_swivel", False))
            if fem_cfg is not None
            else False
        )

    # -- scene-level -----------------------------------------------------------

    def pre_scene(self) -> None:
        """Install the coupler patch; must run before gs.Scene()."""

        import genesis as gs

        # libuipc is CUDA-only. On a CPU genesis backend it dies inside muda
        # with an unreadable C++ abort (cudaErrorInvalidDevice) -- fail here
        # with a message instead. Bitten by the discrete untangle demo, whose
        # default backend is cpu unlike the continuous demos.
        backend_name = str(getattr(gs, "backend", "")).lower()
        if "cpu" in backend_name:
            raise RuntimeError(
                "rope.model=fem_ipc_tube requires a CUDA backend (libuipc is "
                "GPU-only); run with --backend gpu."
            )
        vc.reset()
        vc.install()

    def scene_options(self) -> dict:
        import genesis as gs

        coupler_kwargs = {
            "contact_d_hat": _fem_value(self.rope_cfg, "contact_d_hat"),
            # Every rigid this backend puts into IPC is a STATIC ('ipc_only')
            # contact body for the rope; rigid<->rigid dynamics belong to the
            # rigid solver. Genesis defaults these to True, and cable_routing's
            # deliberately overlapping static compounds (post shaft + flared
            # base) then feed the barrier an interpenetrating ABD pair --
            # infinite energy in the first line search.
            "enable_rigid_rigid_contact": False,
            "enable_rigid_ground_contact": False,
        }
        fem_cfg = getattr(self.rope_cfg, "fem", None)
        sanity = getattr(fem_cfg, "sanity_check_enable", None) if fem_cfg is not None else None
        if sanity is not None:
            # libuipc's sanity checker demands an intersection-free initial
            # state. Scenes with deliberately overlapping STATIC compounds
            # (cable_routing's post shaft + flared base, flush fixtures on the
            # table) fail it even though fixed-fixed overlap carries no degrees
            # of freedom; rope.fem.sanity_check_enable=false waives the check
            # for those scenes.
            coupler_kwargs["sanity_check_enable"] = bool(sanity)
        # Newton 求解器的迭代预算。null 时不传，libuipc 用自己的默认（1024 / 0.05）。
        # 这两项是 IPC 求解耗时的直接旋钮，调小=精度换速度。
        for key, cast in (("newton_max_iterations", int), ("newton_tolerance", float)):
            value = getattr(fem_cfg, key, None) if fem_cfg is not None else None
            if value is not None:
                coupler_kwargs[key] = cast(value)
        return {
            "coupler_options": gs.options.IPCCouplerOptions(**coupler_kwargs),
            "fem_options": gs.options.FEMOptions(),
        }

    def material(self):
        import genesis as gs

        return gs.materials.FEM.Elastic(
            model="stable_neohookean",
            E=_fem_value(self.rope_cfg, "E"),
            nu=_fem_value(self.rope_cfg, "nu"),
            rho=_fem_value(self.rope_cfg, "rho"),
            friction_mu=_fem_value(self.rope_cfg, "friction_mu"),
        )

    def static_rigid_material(self):
        """Fixed rigids must be 'ipc_only' under the IPC coupler.

        The coupler's auto-select sees their base joint, picks
        'external_articulation', and then rejects it; the spike hit this on the
        ground plane first (rope_backend_migration doc).
        """

        import genesis as gs

        return gs.materials.Rigid(coup_type="ipc_only")

    def decoration_rigid_material(self):
        """Collision-free fixtures leave IPC entirely.

        With no collision geometry they cannot satisfy any coupling type (the
        coupler's external_articulation path raises on them), and having no
        contact is exactly their current behavior.
        """

        import genesis as gs

        return gs.materials.Rigid(needs_coup=False)

    # -- pre-build declarations ------------------------------------------------

    def declare_anchor(self, entity, centers, radius: float) -> None:
        vc.pin_near(entity, np.atleast_2d(np.asarray(centers, dtype=float)), radius)

    def declare_rest_straight(self, entity, centerline) -> None:
        """Register the entity with a straight rest shape (declare pre-build).

        The spawn route then carries real bending pre-stress instead of being
        the stress-free configuration -- the Kirchhoff-rod fix for the helix
        (rest curvature kappa_0 -> 0; see rope_backend_migration_zh.md).
        """

        vc.rest_shape_straight(entity, centerline)

    def declare_follow(self, entity, center, radius: float) -> int:
        """Declare one follow band; returns its token (index)."""

        handles = self._follow_handles.setdefault(str(entity.uid), [])
        handles.append(
            vc.follow_near(
                entity,
                center,
                radius,
                strength=_fem_value(self.rope_cfg, "follow_strength"),
            )
        )
        return len(handles) - 1

    # -- post-build ------------------------------------------------------------

    def resolve_indices(self, entity, centers, radius: float) -> list[int]:
        positions = self.nodes(entity)
        indices: set[int] = set()
        for center in np.atleast_2d(np.asarray(centers, dtype=float)):
            dist = np.linalg.norm(positions - center[None, :], axis=1)
            near = np.flatnonzero(dist <= radius)
            if len(near) == 0:
                near = np.array([int(np.argmin(dist))], dtype=int)
            indices.update(int(i) for i in near)
        return sorted(indices)

    def anchor(self, entity, indices=None) -> list[int]:
        # ``indices`` is a PBD-parity affordance; FEM pins are declared by
        # selector pre-build, so the resolved set is authoritative here.
        pins = vc.resolved_pins(entity)
        if pins is None or len(pins) == 0:
            raise RuntimeError(
                "no pinned vertices resolved -- declare_anchor() must run before "
                "scene.build(), with pre_scene() called before gs.Scene()."
            )
        return [int(i) for i in pins]

    def follow_link(self, entity, link, band: int | None = None, indices=None) -> list[int]:
        # ``indices`` is a PBD-parity affordance; the FEM band is the declared one.
        handles = self._follow_handles.get(str(entity.uid))
        if not handles:
            raise RuntimeError("declare_follow() was not called for this entity.")
        if band is None:
            if len(handles) != 1:
                raise ValueError("multiple follow bands declared; pass band=token.")
            band = 0
        handle = handles[int(band)]
        indices = handle.verts
        positions = self.nodes(entity)[indices]
        link_pos = np.asarray(tensor_to_numpy(link.get_pos()), dtype=float).reshape(3)
        rotation = _quat_to_mat(tensor_to_numpy(link.get_quat()))
        # Offsets in the link's local frame, so the band follows its rotation --
        # fix_particles_to_link's crucial property (see the blow-up debug log for
        # what a world-axis weld did to this task).
        local_offsets = (positions - link_pos[None, :]) @ rotation
        handle.engage(positions.astype(np.float64))
        self._follow_sync.add(entity.scene, handle, link, local_offsets, entity)
        return [int(i) for i in indices]

    # -- probes ----------------------------------------------------------------

    def nodes(self, entity) -> np.ndarray:
        positions = tensor_to_numpy(entity.get_state().pos)
        return positions[0] if positions.ndim == 3 else positions

    def swivel_turns(self) -> list[float]:
        """Accumulated follow-band swivel, in turns, in declaration order."""

        return self._follow_sync.turned_turns()

    def node_velocities(self, entity) -> np.ndarray:
        velocities = tensor_to_numpy(entity.get_state().vel)
        return velocities[0] if velocities.ndim == 3 else velocities

    def zero_node_velocities(self, entity) -> None:
        # FEMEntity.set_velocity broadcasts one velocity to every vertex.
        entity.set_velocity(np.zeros(3, dtype=float))
