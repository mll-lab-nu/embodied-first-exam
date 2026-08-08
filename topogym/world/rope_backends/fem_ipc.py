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

Config: material and contact knobs read from an optional ``rope.fem`` block,
falling back to the spike-calibrated defaults (rest crossing gap 9.66mm of the
10mm target at these values).
"""

from __future__ import annotations

import numpy as np

from topogym.world import genesis_ipc_vertex_constraints as vc
from topogym.world.rope import tensor_to_numpy

# Spike calibration (fem_ipc_rope_spike.py, run15). d_hat deliberately below
# the 4mm rope radius: libuipc's 10mm default would hold the ropes ~10mm apart.
_DEFAULTS = {
    "E": 1.0e5,
    "nu": 0.45,
    "rho": 650.0,
    "friction_mu": 0.3,
    "contact_d_hat": 0.002,
    "follow_strength": 100.0,
}


def _fem_value(rope_cfg, key: str):
    fem_cfg = getattr(rope_cfg, "fem", None)
    if fem_cfg is not None and getattr(fem_cfg, key, None) is not None:
        return float(getattr(fem_cfg, key))
    return _DEFAULTS[key]


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

    def __init__(self) -> None:
        self._entries: list[tuple] = []  # (handle, link, local_offsets)
        self._scene = None

    def add(self, scene, handle, link, local_offsets: np.ndarray) -> None:
        self._entries.append((handle, link, local_offsets))
        if self._scene is None:
            self._scene = scene
            original = scene.step

            def step_with_follow_sync(*args, **kwargs):
                self.sync()
                return original(*args, **kwargs)

            scene.step = step_with_follow_sync

    def sync(self) -> None:
        for handle, link, local_offsets in self._entries:
            link_pos = np.asarray(tensor_to_numpy(link.get_pos()), dtype=float).reshape(3)
            rotation = _quat_to_mat(tensor_to_numpy(link.get_quat()))
            handle.update_targets(link_pos[None, :] + local_offsets @ rotation.T)


class FemIpcRopeBackend:
    name = "fem_ipc"

    def __init__(self, rope_cfg) -> None:
        self.rope_cfg = rope_cfg
        self._follow_handles: dict[str, list[vc.FollowHandle]] = {}
        self._follow_sync = _FollowSync()

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

        return {
            "coupler_options": gs.options.IPCCouplerOptions(
                contact_d_hat=_fem_value(self.rope_cfg, "contact_d_hat")
            ),
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
        self._follow_sync.add(entity.scene, handle, link, local_offsets)
        return [int(i) for i in indices]

    # -- probes ----------------------------------------------------------------

    def nodes(self, entity) -> np.ndarray:
        positions = tensor_to_numpy(entity.get_state().pos)
        return positions[0] if positions.ndim == 3 else positions

    def node_velocities(self, entity) -> np.ndarray:
        velocities = tensor_to_numpy(entity.get_state().vel)
        return velocities[0] if velocities.ndim == 3 else velocities

    def zero_node_velocities(self, entity) -> None:
        # FEMEntity.set_velocity broadcasts one velocity to every vertex.
        entity.set_velocity(np.zeros(3, dtype=float))
