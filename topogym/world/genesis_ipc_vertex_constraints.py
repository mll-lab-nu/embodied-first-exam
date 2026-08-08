"""Vertex pin / follow support for FEM entities under Genesis' IPC coupler.

Genesis 1.2.1 exposes no rope-end constraint under the IPC coupler:
``FEMEntity.set_vertex_constraints`` raises when the coupler is IPC
(fem_entity.py:906), and ``IPCCoupler._add_fem_entities_to_ipc`` registers FEM
tetmeshes with material + contact only -- no per-vertex ``is_fixed``, no soft
position constraint. libuipc itself has both primitives (the rigid path uses
``uipc.builtin.is_fixed`` at coupler.py:531; ``SoftPositionConstraint`` +
animator is the documented libuipc way to drive soft-body vertices), so this
module wires them in from outside:

- ``install()`` swaps the coupler class the simulator instantiates for a
  subclass whose ``_add_fem_entities_to_ipc`` is a vendored copy of the
  Genesis 1.2.1 method plus the attribute hookups. Call it after ``gs.init()``
  and **before** ``gs.Scene(...)``.
- ``pin_near(entity, centers, radius)`` -- vertices near those points become
  immovable at their spawn positions (the PBD ``fix_particles`` analog).
- ``follow_near(entity, center, radius, strength=...)`` -- returns a handle
  whose targets can be updated every step (the ``fix_particles_to_link`` /
  ``ParticleAttachment`` analog).

Vertices are addressed by *selector* (center + radius), not by index: the FEM
vertex set is the tet mesh (tetgen inserts Steiner points), so surface-mesh
indices do not carry over, and ``entity.init_positions`` is only reliably
populated by build time. Selectors are resolved inside the patched coupler
method -- the same place the stock code reads ``init_positions`` -- with the
same within-radius-else-nearest rule as ``rope.endpoint_particle_indices``.

Constraint *capacity* is declared pre-build; engagement (attach / drive /
release) is runtime, via the handle. Single environment only (``n_envs=0``).

Vendored-copy caveat: the override tracks genesis 1.2.1 exactly; a Genesis
upgrade must re-diff ``_add_fem_entities_to_ipc``. The additions are fenced
with ``# --- topogym addition ---`` markers.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass, field
from functools import partial

import numpy as np

_SPECS: dict[str, "_EntitySpec"] = {}
_INSTALLED = False


@dataclass
class _EntitySpec:
    """Declared constraint capacity for one FEM entity (single env only)."""

    pin_selectors: list[tuple[np.ndarray, float]] = field(default_factory=list)
    # One entry per follow band: (center, radius, strength). A rope can carry
    # several -- the discrete untangle welds BOTH ends to rigid handles.
    follow_selectors: list[tuple[np.ndarray, float, float]] = field(default_factory=list)
    # Resolved at build time by the patched coupler (one array per band).
    pin_verts: np.ndarray | None = None
    follow_verts: list[np.ndarray] | None = None
    # Runtime state per band, mutated through FollowHandle. Each targets entry is
    # (n_band, 3) world positions; `engaged` gates is_constrained per band.
    targets: list = field(default_factory=list)
    engaged: list = field(default_factory=list)


@dataclass
class FollowHandle:
    """Runtime control over one follow band declared pre-build."""

    _uid: str
    band: int

    @property
    def _spec(self) -> _EntitySpec:
        return _SPECS[self._uid]

    @property
    def verts(self) -> np.ndarray:
        bands = self._spec.follow_verts
        if bands is None:
            raise RuntimeError(
                "follow bands not resolved yet -- scene.build() has not run "
                "(or install() was not called before gs.Scene)."
            )
        return bands[self.band]

    def engage(self, targets: np.ndarray) -> None:
        self.update_targets(targets)
        self._spec.engaged[self.band] = True

    def update_targets(self, targets: np.ndarray) -> None:
        targets = np.asarray(targets, dtype=np.float64)
        if targets.shape != (len(self.verts), 3):
            raise ValueError(f"targets shape {targets.shape} != ({len(self.verts)}, 3)")
        self._spec.targets[self.band] = targets

    def release(self) -> None:
        self._spec.engaged[self.band] = False


def pin_near(entity, centers, radius: float) -> None:
    """Pin all vertices within ``radius`` of any center. Declare pre-build."""

    spec = _SPECS.setdefault(str(entity.uid), _EntitySpec())
    for center in np.atleast_2d(np.asarray(centers, dtype=float)):
        spec.pin_selectors.append((center.copy(), float(radius)))


def follow_near(entity, center, radius: float, *, strength: float = 100.0) -> FollowHandle:
    """Declare a driveable band around ``center``. Declare pre-build.

    May be called several times per entity (one band per call); each call
    returns the handle for its own band.
    """

    spec = _SPECS.setdefault(str(entity.uid), _EntitySpec())
    spec.follow_selectors.append(
        (np.asarray(center, dtype=float).copy(), float(radius), float(strength))
    )
    spec.targets.append(None)
    spec.engaged.append(False)
    return FollowHandle(str(entity.uid), len(spec.follow_selectors) - 1)


def resolved_pins(entity) -> np.ndarray | None:
    """Pin indices for this entity, once the scene is built."""

    spec = _SPECS.get(str(entity.uid))
    return None if spec is None else spec.pin_verts


def reset() -> None:
    """Drop all declared specs (between scenes in one process)."""

    _SPECS.clear()


def _select(positions: np.ndarray, center: np.ndarray, radius: float) -> np.ndarray:
    """Within-radius vertex selection, else the single nearest vertex.

    Same rule as ``rope.endpoint_particle_indices``, applied to FEM vertices.
    """

    dist = np.linalg.norm(positions - center[None, :], axis=1)
    near = np.flatnonzero(dist <= radius)
    if len(near) == 0:
        near = np.array([int(np.argmin(dist))], dtype=int)
    return near


def _resolve_spec(spec: _EntitySpec, positions: np.ndarray) -> None:
    if spec.pin_selectors and spec.pin_verts is None:
        indices: set[int] = set()
        for center, radius in spec.pin_selectors:
            indices.update(int(i) for i in _select(positions, center, radius))
        spec.pin_verts = np.asarray(sorted(indices), dtype=np.int64)
    if spec.follow_selectors and spec.follow_verts is None:
        bands: list[np.ndarray] = []
        for center, radius, _strength in spec.follow_selectors:
            follow = np.asarray(sorted(_select(positions, center, radius)), dtype=np.int64)
            if spec.pin_verts is not None:
                overlap = np.intersect1d(follow, spec.pin_verts)
                if len(overlap):
                    raise ValueError(
                        f"follow band and pinned band overlap on {len(overlap)} vertices -- "
                        "is_fixed and SoftPositionConstraint would fight over them."
                    )
            bands.append(follow)
        spec.follow_verts = bands


def _animate_fem_follow(coupler_ref, uid: str, env_idx: int, info) -> None:
    """Animator callback: write is_constrained + aim_position for the band."""

    import uipc

    if coupler_ref() is None:
        return
    spec = _SPECS.get(uid)
    if spec is None or spec.follow_verts is None:
        return
    geom_slots = info.geo_slots()
    if not geom_slots:
        return
    geom = geom_slots[0].geometry()
    is_constrained = geom.vertices().find(uipc.builtin.is_constrained)
    aim_position = geom.vertices().find(uipc.builtin.aim_position)
    assert is_constrained and aim_position
    constrained_view = uipc.view(is_constrained)
    aim_view = uipc.view(aim_position)
    for band, verts in enumerate(spec.follow_verts):
        if spec.engaged[band] and spec.targets[band] is not None:
            constrained_view.reshape(-1)[verts] = 1
            aim_view.reshape(-1, 3)[verts] = spec.targets[band]
        else:
            constrained_view.reshape(-1)[verts] = 0


def install() -> None:
    """Make the simulator build the patched coupler. Call before gs.Scene()."""

    global _INSTALLED
    if _INSTALLED:
        return

    import genesis.engine.simulator as simulator_module
    from genesis.engine.couplers.ipc_coupler import coupler as coupler_module
    from genesis.engine.couplers.ipc_coupler.coupler import IPCCoupler

    # Substep-consistent IPC time step. Stock genesis 1.2.1 hands the IPC scene
    # the FULL sim.dt (utils.py:93) while couple() advances it once per substep
    # (simulator.py:321) -- correct only at substeps=1. But substeps=1 gives the
    # RIGID solver 10ms substeps, which destabilizes marginally-resting free
    # bodies: the connector plugs walked ~21mm during one arm-home settle
    # (probe 2026-08-07; 3mm for PBD at substeps=1, ~0 at substeps=4). Dividing
    # the IPC dt by substeps makes both solvers advance the same clock at any
    # substep count, so the FEM preset can run the baseline substeps=4.
    _stock_build_cfg = coupler_module.build_ipc_scene_config

    def _substep_aware_build_cfg(options, sim_options):
        config = _stock_build_cfg(options, sim_options)
        config["dt"] = float(sim_options.dt) / max(1, int(sim_options.substeps))
        return config

    coupler_module.build_ipc_scene_config = _substep_aware_build_cfg

    import uipc
    from uipc.constitution import (
        DiscreteShellBending,
        ElasticModuli,
        ElasticModuli2D,
        SoftPositionConstraint,
        StableNeoHookean,
        StrainLimitingBaraffWitkinShell,
    )

    from genesis.engine.materials.FEM.cloth import Cloth
    from genesis.utils.misc import tensor_to_array

    class VertexConstraintIPCCoupler(IPCCoupler):
        """IPCCoupler + per-vertex is_fixed / SoftPositionConstraint for FEM."""

        # Vendored from genesis 1.2.1 `_add_fem_entities_to_ipc`; additions fenced.
        def _add_fem_entities_to_ipc(self) -> None:
            # --- topogym addition: constraint declarations need a single env ---
            if _SPECS and self.sim._B > 1:
                raise NotImplementedError(
                    "FEM vertex constraints support a single environment (n_envs=0)."
                )
            spc = None
            # --- end addition ---

            for env_idx in range(self.sim._B):
                for i_e, entity in enumerate(self.fem_solver.entities):
                    is_cloth = isinstance(entity.material, Cloth)
                    solver_type = "cloth" if is_cloth else "fem"

                    fem_obj = self._ipc_objects.create(f"{solver_type}_{i_e}_{env_idx}")

                    if is_cloth:
                        verts = tensor_to_array(entity.init_positions).astype(np.float64, copy=False)
                        faces = entity.surface_triangles.astype(np.int32, copy=False)
                        mesh = uipc.geometry.trimesh(verts, faces)
                    else:
                        mesh = uipc.geometry.tetmesh(
                            tensor_to_array(entity.init_positions), entity.elems
                        )
                    uipc.geometry.label_surface(mesh)

                    if self.sim.n_envs > 0:
                        self._ipc_subscenes[env_idx].apply_to(mesh)

                    if is_cloth:
                        if entity not in self._ipc_cloth_contacts:
                            self._ipc_cloth_contacts[entity] = self._ipc_contact_tabular.create(
                                f"cloth_contact_{i_e}"
                            )
                        self._ipc_cloth_contacts[entity].apply_to(mesh)
                    else:
                        if entity not in self._ipc_fem_contacts:
                            self._ipc_fem_contacts[entity] = self._ipc_contact_tabular.create(
                                f"fem_contact_{i_e}"
                            )
                        self._ipc_fem_contacts[entity].apply_to(mesh)

                    if is_cloth:
                        if self._ipc_nks is None:
                            self._ipc_nks = StrainLimitingBaraffWitkinShell()
                            self._ipc_constitution_tabular.insert(self._ipc_nks)
                        moduli = ElasticModuli2D.youngs_poisson(entity.material.E, entity.material.nu)
                        self._ipc_nks.apply_to(
                            mesh,
                            moduli=moduli,
                            mass_density=entity.material.rho,
                            thickness=entity.material.thickness,
                        )
                        if entity.material.bending_stiffness is not None:
                            if self._ipc_dsb is None:
                                self._ipc_dsb = DiscreteShellBending()
                                self._ipc_constitution_tabular.insert(self._ipc_dsb)
                            self._ipc_dsb.apply_to(
                                mesh, bending_stiffness=entity.material.bending_stiffness
                            )
                    else:
                        if self._ipc_stk is None:
                            self._ipc_stk = StableNeoHookean()
                            self._ipc_constitution_tabular.insert(self._ipc_stk)
                        moduli = ElasticModuli.youngs_poisson(entity.material.E, entity.material.nu)
                        self._ipc_stk.apply_to(mesh, moduli, mass_density=entity.material.rho)

                    # --- topogym addition: vertex pin + follow ---
                    spec = _SPECS.get(str(entity.uid))
                    if spec is not None and not is_cloth:
                        _resolve_spec(spec, tensor_to_array(entity.init_positions))
                        # Always materialize is_fixed on a constrained mesh, even
                        # when nothing is pinned. Every scene validated before the
                        # discrete untangle happened to have anchor pins creating
                        # it as a side effect; a follow-only mesh (no attribute at
                        # all) died inside libuipc's CUDA kernels with an
                        # unattributable cudaErrorInvalidDevice.
                        is_fixed = mesh.vertices().find(uipc.builtin.is_fixed)
                        if not is_fixed:
                            is_fixed = mesh.vertices().create(uipc.builtin.is_fixed, 0)
                        if spec.pin_verts is not None and len(spec.pin_verts):
                            uipc.view(is_fixed).reshape(-1)[spec.pin_verts] = 1
                        if spec.follow_verts is not None and len(spec.follow_verts):
                            if spc is None:
                                spc = SoftPositionConstraint()
                                self._ipc_constitution_tabular.insert(spc)
                            # One constitution per mesh; the strength rate
                            # is mesh-wide, so take the strongest band.
                            spc.apply_to(
                                mesh,
                                max(s for _c, _r, s in spec.follow_selectors),
                            )
                            self._ipc_animator.insert(
                                fem_obj,
                                partial(
                                    _animate_fem_follow,
                                    weakref.ref(self),
                                    str(entity.uid),
                                    env_idx,
                                ),
                            )
                    # --- end addition ---

                    meta_attrs = mesh.meta()
                    meta_attrs.create("solver_type", solver_type)
                    meta_attrs.create("entity_idx", str(i_e))
                    meta_attrs.create("env_idx", str(env_idx))

                    fem_obj.geometries().create(mesh)

    simulator_module.IPCCoupler = VertexConstraintIPCCoupler
    _INSTALLED = True
