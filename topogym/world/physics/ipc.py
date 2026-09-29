"""Pinned Genesis 1.2.1 / pyuipc 0.0.25 integration and branch-safe native dumps.

The native dump includes FEM/ABD position, velocity, previous position and
contact trajectory caches. Numeric geometry inputs and Genesis buffers are
saved separately. No action replay or pose-only recovery is used.
"""

from dataclasses import dataclass
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path
import shutil
import os
import zlib

import numpy as np


def require_episode_checkpoint(compute_backend="cuda"):
    if compute_backend != "cuda":
        raise RuntimeError('FEM/IPC requires CUDA; select compute_backend="cuda"')
    for package, required in (("genesis-world", "1.2.1"), ("pyuipc", "0.0.25")):
        if version(package).split("+")[0] != required:
            raise RuntimeError(f"IPC checkpoint codec requires {package}=={required}")
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "FEM/IPC CUDA device is unavailable; run scripts/test_base_tasks.py on a CUDA host"
        )


def scene_options(parameters):
    import genesis as gs

    defaults = dict(
        contact_d_hat=0.0005,
        newton_tolerance=1.0e-4,
        linear_system_tolerance=1.0e-6,
        enable_rigid_rigid_contact=True,
        enable_rigid_ground_contact=True,
    )
    return gs.options.IPCCouplerOptions(**(defaults | dict(parameters)))


@dataclass(frozen=True)
class IPCState:
    frame: int
    files: tuple
    attributes: tuple
    previous_link_transforms: tuple


class CheckpointStore:
    def __init__(self, coupler):
        self.coupler = coupler
        self.workspace = Path(coupler._ipc_engine.workspace()).resolve()
        self.attribute_slots = None

    def _slots(self):
        from uipc.backend import SceneVisitor

        visitor = SceneVisitor(self.coupler._ipc_scene)
        result = []
        for slot in visitor.geometries():
            geometry = slot.geometry()
            # Geometry JSON supplies attribute names; copy typed buffers rather
            # than retaining a live geometry handle as a purported snapshot.
            for collection_name, collection in geometry.to_json().items():
                if not isinstance(collection, dict):
                    continue
                for name in collection:
                    target = geometry[collection_name].find(name)
                    try:
                        value = np.asarray(target.view())
                    except (AttributeError, TypeError):
                        continue
                    if value.dtype.kind in "fiu":
                        result.append(target)
        return result

    def capture(self):
        native = self.coupler._ipc_world
        native.sync()
        if not native.dump():
            raise RuntimeError("Native IPC dump failed")
        frame = int(native.frame())
        files = []
        for path in sorted(self.workspace.rglob("*")):
            if path.is_file() and (
                path.name.endswith(f".{frame}") or path.name.endswith(f".{frame}.json")
            ):
                files.append(
                    (
                        str(path.relative_to(self.workspace)),
                        zlib.compress(path.read_bytes()),
                    )
                )
        if not files or not any("finite_element_method" in name for name, _ in files):
            raise RuntimeError("Native IPC dump omitted FEM state")
        if self.attribute_slots is None:
            self.attribute_slots = self._slots()
        attributes = tuple(
            (slot, np.asarray(slot.view()).copy()) for slot in self.attribute_slots
        )
        previous = tuple(
            (data, deepcopy(data.prev_links_transform))
            for data in self.coupler._articulation_data_by_entity.values()
        )
        return IPCState(frame, tuple(files), attributes, previous)

    def restore(self, state):
        import uipc

        # Restore original filenames from immutable bytes. Same native frame
        # on another branch can never overwrite a saved branch's payload.
        for relative, data in state.files:
            path = self.workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zlib.decompress(data))
        for slot, values in state.attributes:
            np.copyto(uipc.view(slot), values)
        native = self.coupler._ipc_world
        if not native.recover(state.frame) or int(native.frame()) != state.frame:
            raise RuntimeError(f"Native IPC recover({state.frame}) failed")
        native.retrieve()
        # Genesis replaces these list elements each step; restoring an old
        # ndarray handle alone does not restore the currently referenced input.
        for data, values in state.previous_link_transforms:
            data.prev_links_transform = deepcopy(values)

    def discard(self, states):
        # Payloads are immutable bytes inside the checkpoint. Rewind has already
        # restored the current frame, so only strictly later native frames go.
        current = int(self.coupler._ipc_world.frame())
        for state in states:
            if state.frame <= current:
                continue
            for relative, _ in state.files:
                path = (self.workspace / relative).resolve()
                if not path.is_relative_to(self.workspace):
                    raise ValueError("IPC dump path escaped the owned workspace")
                path.unlink(missing_ok=True)

    def close(self):
        self.attribute_slots = None
        # Owned scene UID workspace only; never touch another scene's outputs.
        if self.workspace.name.startswith("genesis_ipc_"):
            shutil.rmtree(self.workspace)
        self.coupler = None


def install_for_scene(scene, *, initial_robot_positions=None):
    """Replace only this scene's unbuilt coupler, with a version-pinned subclass."""
    import genesis as gs
    import uipc
    from genesis.engine.couplers.ipc_coupler.coupler import IPCCoupler
    from uipc.backend import SceneVisitor
    from uipc.constitution import StableNeoHookean, ElasticModuli, SoftVertexStitch
    from uipc.core import FiniteElementStateAccessorFeature

    class EpisodeIPCCoupler(IPCCoupler):
        def __init__(self, simulator, options):
            super().__init__(simulator, options)
            uipc.view(self._ipc_scene.config().find("dt"))[:] = (
                float(simulator.dt) / simulator.substeps
            )
            self.attachments = ()
            self.named_entities = {}
            self.fem_slots = {}
            self.attachment_pairs = []
            self.checkpoint_store = None
            self._fem_accessor = self._fem_state_geom = None
            self._target_substep = 0
            self.fem_grasp_specs = {}
            self.grasp_backend = None

        def build(self):
            # qpos0 is the model reference, not a configurable spawn pose.
            # Change actual solver qpos after rigid allocation, but before
            # creating IPC geometry/EAC reference transforms. Entity setters
            # correctly forbid this once external articulation is initialized.
            if initial_robot_positions:
                robot = next(e for e in self.rigid_solver.entities if e.name == "robot")
                qpos = robot.init_qpos.copy()
                for name, value in initial_robot_positions.items():
                    qpos[robot.get_joint(name).qs_idx_local] = value
                self.rigid_solver.set_qpos(
                    qpos, qs_idx=slice(robot.q_start, robot.q_end)
                )
            super().build()
            geoms = self.rigid_solver.geoms
            pairs = self.rigid_solver.collider._valid_collision_pairs
            names = [(geoms[a].entity.name, geoms[b].entity.name) for a, b in pairs]
            native_dynamic = {
                entity.name
                for entity in self._coup_type_by_entity
                if entity.material.coup_type == "ipc_only"
                and not entity.base_link.is_fixed
            }
            self.contact_ownership = dict(
                rigid_robot_self_pairs=sum(a == b == "robot" for a, b in names),
                rigid_robot_table_pairs=sum(
                    {a, b} == {"robot", "table"} for a, b in names
                ),
                rigid_native_body_pairs=sum(
                    a in native_dynamic or b in native_dynamic for a, b in names
                ),
            )

        def _init_ipc(self):
            super()._init_ipc()
            # Keep native convergence warnings in the run log. Upstream
            # suppresses them whenever Genesis is above DEBUG.
            level = (
                uipc.Logger.Level.Info
                if os.getenv("TOPOGYM_IPC_VERBOSE") == "1"
                else uipc.Logger.Level.Warn
            )
            uipc.Logger.set_level(level)

        def _add_rigid_geoms_to_ipc(self):
            # Render-oriented meshes can duplicate vertices at normal/UV seams.
            # Weld coincident vertices for IPC volume integration, without
            # changing the Genesis collision topology or filling real holes.
            import trimesh

            originals = []
            try:
                for entity in self._coup_type_by_entity:
                    for link in entity.links:
                        for geom in link.geoms:
                            if geom.type == gs.GEOM_TYPE.PLANE:
                                continue
                            mesh = trimesh.Trimesh(
                                geom.init_verts.copy(),
                                geom.init_faces.copy(),
                                process=True,
                            )
                            if not mesh.is_watertight and geom.is_convex:
                                # Genesis already uses the convex support hull
                                # for this collider; construct its closed shell.
                                mesh = mesh.convex_hull
                            if not mesh.is_watertight:
                                raise ValueError(
                                    f"IPC collision mesh is open: {entity.name}/{link.name}/geom_{geom.idx}"
                                )
                            mesh.fix_normals(multibody=True)
                            originals.append((geom, geom._init_verts, geom._init_faces))
                            geom._init_verts, geom._init_faces = (
                                np.asarray(mesh.vertices),
                                np.asarray(mesh.faces),
                            )
                super()._add_rigid_geoms_to_ipc()
            finally:
                for geom, vertices, faces in originals:
                    geom._init_verts, geom._init_faces = vertices, faces

        def couple(self, f):
            self._target_substep = f + 1
            super().couple(f)
            if not self._ipc_world.is_valid():
                raise RuntimeError("Native IPC world became invalid while stepping")

        def reset(self, envs_idx=None):
            super().reset(envs_idx)
            # Scene.build performs a warm-up step and recovers native frame 0.
            # Upstream reset leaves its Python ABD velocities and articulation
            # reference at that warm-up step, corrupting the observed initial
            # state and the next joint update. Rebuild those inputs from reset
            # Genesis/native states, without advancing either clock.
            self._target_substep = 0
            self._store_gs_rigid_states()
            for data in self._articulation_data_by_entity.values():
                data.ref_dof_prev[:] = data.qpos_stored
                data.qpos_current[:] = data.qpos_stored
                data.qpos_new[:] = data.qpos_stored
                data.delta_theta_tilde.fill(0)
                data.delta_theta_ipc.fill(0)
                data.prev_links_transform = [
                    [None] * self.sim._B for _ in data.joints_child_link
                ]
            self._retrieve_fem_states()
            self._retrieve_rigid_states()

        def _register_contact_pairs(self):
            super()._register_contact_pairs()
            items = list(self._ipc_abd_contacts.items())
            for i, (a, ca) in enumerate(items):
                for b, cb in items[i:]:
                    static_pair = (
                        a.base_link.is_fixed
                        and a.n_dofs == 0
                        and b.base_link.is_fixed
                        and b.n_dofs == 0
                    )
                    articulated_self = a is b and a.n_dofs > 6
                    robot_static = (a.name == "robot" and b.n_dofs == 0) or (
                        b.name == "robot" and a.n_dofs == 0
                    )
                    if static_pair or articulated_self or robot_static:
                        # Fixed fixtures may intentionally intersect. Robot
                        # self-contact remains owned by the Genesis rigid solver.
                        self._ipc_contact_tabular.insert(ca, cb, 0.0, 0.0, False)
            for ground in self._ipc_ground_contacts.values():
                for entity, contact in items:
                    if entity.n_dofs == 0 or entity.name == "robot":
                        self._ipc_contact_tabular.insert(
                            ground, contact, 0.0, 0.0, False
                        )

        def _add_fem_entities_to_ipc(self):
            self._ipc_stk = StableNeoHookean()
            self._ipc_constitution_tabular.insert(self._ipc_stk)
            grasp_constraint = None
            if self.fem_grasp_specs:
                from uipc.constitution import SoftPositionConstraint
                grasp_constraint = SoftPositionConstraint()
                self._ipc_constitution_tabular.insert(grasp_constraint)
            for i, entity in enumerate(self.fem_solver.entities):
                if not hasattr(entity, "material_coordinates"):
                    raise ValueError("IPC FEM requires an explicit reference volume")
                if entity.material.model != "stable_neohookean":
                    raise ValueError(
                        "This IPC volume bridge supports stable_neohookean materials only"
                    )
                from topogym.utils.arrays import to_numpy

                mesh = uipc.geometry.tetmesh(
                    to_numpy(entity.init_positions), entity.elems
                )
                rest = uipc.geometry.tetmesh(entity.material_coordinates, entity.elems)
                contact = self._ipc_contact_tabular.create(f"fem_contact_{i}")
                self._ipc_fem_contacts[entity] = contact
                moduli = ElasticModuli.youngs_poisson(
                    entity.material.E, entity.material.nu
                )
                for geometry in (mesh, rest):
                    uipc.geometry.label_surface(geometry)
                    contact.apply_to(geometry)
                    self._ipc_stk.apply_to(
                        geometry, moduli, mass_density=entity.material.rho
                    )
                    geometry.meta().create("solver_type", "fem")
                    geometry.meta().create("entity_idx", str(i))
                    geometry.meta().create("env_idx", "0")
                obj = self._ipc_objects.create(f"fem_{i}_0")
                if entity in self.fem_grasp_specs:
                    for geometry in (mesh, rest):
                        # libuipc's soft constraint kernels require an explicit
                        # per-vertex fixed mask even in an unpinned scene.
                        if geometry.vertices().find(uipc.builtin.is_fixed) is None:
                            geometry.vertices().create(uipc.builtin.is_fixed, 0)
                        grasp_constraint.apply_to(geometry, self.fem_grasp_specs[entity].strength)
                        uipc.view(geometry.vertices().find(uipc.builtin.is_constrained))[:] = 0
                    self._ipc_animator.insert(obj, lambda info, e=entity: self._animate_grasp(e, info))
                self.fem_slots[entity] = obj.geometries().create(mesh, rest)[0]

        def _animate_grasp(self, entity, info):
            # IPC animator runs after rigid-state synchronization, before solve.
            # The scene-local backend survives rewind; its state does not.
            if self.grasp_backend is not None:
                self.grasp_backend.update_entity_targets(entity, info.geo_slots()[0].geometry())

        def _finalize_ipc(self):
            self._create_attachments()
            super()._finalize_ipc()
            if not self._ipc_world.is_valid():
                raise RuntimeError("IPC initialization failed its native sanity check")
            self._fem_accessor = self._ipc_world.features().find(
                FiniteElementStateAccessorFeature
            )
            if self._fem_accessor is None:
                raise RuntimeError("IPC FEM velocity accessor is unavailable")
            self._fem_state_geom = self._fem_accessor.create_geometry()
            self._fem_state_geom.vertices().create(uipc.builtin.position, np.zeros(3))
            self._fem_state_geom.vertices().create(uipc.builtin.velocity, np.zeros(3))
            self._retrieve_fem_states()
            self.checkpoint_store = CheckpointStore(self)

        def _create_attachments(self):
            if not self.attachments:
                return
            stitch = SoftVertexStitch()
            self._ipc_constitution_tabular.insert(stitch)
            rest_slots = {
                slot.id(): slot
                for slot in SceneVisitor(self._ipc_scene).rest_geometries()
            }
            for spec in self.attachments:
                soft = self.named_entities[spec.soft_entity]
                rigid = self.named_entities[spec.rigid_entity]
                coordinates = soft.material_coordinates[:, 0]
                distance = (
                    coordinates - coordinates.min()
                    if spec.endpoint == "start"
                    else coordinates.max() - coordinates
                )
                indices = np.flatnonzero(distance <= spec.band_length_m)
                if not len(indices):
                    raise ValueError(f"Empty attachment band: {spec.name}")
                rigid_slot = self._abd_slots_by_link[rigid.base_link][0]
                geometry = rigid_slot.geometry()
                transform = np.asarray(
                    geometry.instances().find("transform").view()
                ).reshape(-1, 4, 4)[0]
                world_points = np.asarray(soft.init_positions.detach().cpu())[indices]
                local = (world_points - transform[:3, 3]) @ np.linalg.inv(
                    transform[:3, :3]
                ).T
                start = geometry.vertices().size()
                for target in (geometry, rest_slots[rigid_slot.id()].geometry()):
                    target.vertices().resize(start + len(indices))
                    uipc.view(target.positions()).reshape(-1, 3)[start:] = local
                    # These are massless constraint anchors, not new collision
                    # surface points coincident with the stitched FEM vertices.
                    for flag in ("is_surf", "is_facet"):
                        attribute = target.vertices().find(flag)
                        if attribute is not None:
                            uipc.view(attribute)[start:] = 0
                    # The native sanity checker retains all vertices of a
                    # triangle mesh, even non-surface virtual anchors. Give
                    # only these anchors the existing no-contact element.
                    contacts = target.vertices().find("contact_element_id")
                    if contacts is None:
                        contacts = target.vertices().create(
                            "contact_element_id", self._ipc_abd_contacts[rigid].id()
                        )
                    uipc.view(contacts)[start:] = self._ipc_no_collision_contact.id()
                pairs = np.column_stack(
                    [indices, np.arange(start, start + len(indices))]
                )
                coupling = stitch.create_geometry(
                    (self.fem_slots[soft], rigid_slot), pairs, spec.stiffness_n_m, 0.0
                )
                self._ipc_objects.create(spec.name).geometries().create(coupling)
                self.attachment_pairs.append(
                    (spec.name, soft, indices, rigid_slot, local)
                )

        def _retrieve_fem_states(self):
            if self._fem_accessor is None:
                return
            self._fem_accessor.copy_to(self._fem_state_geom)
            positions = np.asarray(self._fem_state_geom.positions().view()).reshape(
                -1, 3
            )
            velocities = np.asarray(
                self._fem_state_geom.vertices().find("velocity").view()
            ).reshape(-1, 3)
            offset = 0
            for entity in self.fem_solver.entities:
                count = entity.n_vertices
                entity.set_pos(
                    self._target_substep,
                    np.array(
                        positions[offset : offset + count][None], dtype=gs.np_float
                    ),
                )
                entity.set_vel(
                    self._target_substep,
                    np.array(
                        velocities[offset : offset + count][None], dtype=gs.np_float
                    ),
                )
                offset += count
            if offset != len(positions):
                raise RuntimeError("IPC/Genesis FEM vertex ordering mismatch")

        def diagnostics(self):
            residuals = {}
            for name, entity, indices, slot, local in self.attachment_pairs:
                matrix = np.asarray(
                    slot.geometry().instances().find("transform").view()
                ).reshape(-1, 4, 4)[0]
                targets = local @ matrix[:3, :3].T + matrix[:3, 3]
                from .fem import read_vertices

                actual = read_vertices(entity)["position_m"][indices]
                residuals[name] = float(
                    np.max(np.linalg.norm(actual - targets, axis=1))
                )
            volume_ratios = {}
            from .fem import read_vertices

            for entity in self.fem_solver.entities:
                p = read_vertices(entity)["position_m"][entity.elems]
                r = entity.material_coordinates[entity.elems]
                jacobian = np.linalg.det(p[:, 1:] - p[:, :1]) / np.linalg.det(
                    r[:, 1:] - r[:, :1]
                )
                volume_ratios[entity.name] = dict(
                    minimum=float(jacobian.min()), maximum=float(jacobian.max())
                )
            return dict(
                native_frame=int(self._ipc_world.frame()),
                native_dt_s=float(self.sim.dt) / self.sim.substeps,
                attachment_residual_m=residuals,
                volume_ratio=volume_ratios,
                native_valid=bool(self._ipc_world.is_valid()),
                contact_ownership=self.contact_ownership,
            )

        def rigid_velocities(self):
            """Native velocities, which Genesis zeros to avoid double integration."""
            from genesis.engine.couplers.ipc_coupler.data import COUPLING_TYPE

            result = {}
            for entity in self._entities_by_coup_type.get(COUPLING_TYPE.IPC_ONLY, ()):
                if entity.base_link.is_fixed:
                    continue
                entry = self._abd_data_by_link[entity.base_link][0]
                spin = entry.velocity[:3, :3] @ entry.transform[:3, :3].T
                result[entity.name] = (
                    entry.velocity[:3, 3].copy(),
                    np.array(
                        [
                            spin[2, 1] - spin[1, 2],
                            spin[0, 2] - spin[2, 0],
                            spin[1, 0] - spin[0, 1],
                        ]
                    )
                    / 2,
                )
            return result

        def close(self, diagnostics_dir=None):
            self.grasp_backend = None
            workspace = (
                None
                if self._ipc_engine is None
                else Path(self._ipc_engine.workspace()).resolve()
            )
            if (
                workspace is not None
                and diagnostics_dir is not None
                and workspace.is_dir()
            ):
                shutil.copytree(
                    workspace, Path(diagnostics_dir) / "ipc", dirs_exist_ok=True
                )
            # Accessor features refer to the native engine. Drop them before
            # its world/engine, also on initialization failures before a store.
            self._fem_accessor = self._abd_state_feature = None
            self._fem_state_geom = self._abd_state_geom = None
            self._ipc_world = None
            self._ipc_engine = None
            if self.checkpoint_store is not None:
                self.checkpoint_store.close()
                self.checkpoint_store = None
            elif workspace is not None and workspace.name.startswith("genesis_ipc_"):
                shutil.rmtree(workspace, ignore_errors=True)

    scene.sim._coupler = EpisodeIPCCoupler(scene.sim, scene.sim.coupler_options)
    solver = scene.sim.rigid_solver
    original_init_collider = solver._init_collider

    def init_owned_contacts():
        # Genesis normally removes every pair delegated to IPC. This bridge
        # intentionally lets its rigid solver own robot self/static contacts,
        # so retain those pairs while allocating the collider. Native dynamic
        # bodies stay delegated. Restore all material identities immediately;
        # only the collision ownership table is affected, not physical material.
        originals = []
        try:
            for entity in solver.entities:
                if entity.name == "robot" or (
                    entity.base_link.is_fixed and entity.n_dofs == 0
                ):
                    originals.append((entity, entity.material))
                    entity._material = entity.material.model_copy(
                        update={"needs_coup": False, "coup_type": None}
                    )
            original_init_collider()
        finally:
            for entity, physical_material in originals:
                entity._material = physical_material
            solver._init_collider = original_init_collider

    solver._init_collider = init_owned_contacts
    # Native IPC has already integrated the FEM step. The stock post-coupling
    # Euler position update would integrate it again and discard native velocity.
    scene.sim.fem_solver.substep_post_coupling = lambda f: None
    return scene.sim.coupler
