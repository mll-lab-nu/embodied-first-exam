"""One Genesis scene, one physical clock and in-episode state restoration."""
from __future__ import annotations

from copy import deepcopy
from importlib.metadata import version
from uuid import uuid4

import numpy as np
from topogym.utils.arrays import to_numpy

from topogym.world.state import WorldState, capture_engine_buffers, capture_rng, copy_native_state, restore_engine_buffers, restore_rng, require_finite_state


class _RigidReadout:
    """The rigid solver's state of one tick in one host transfer per field: every link's pose and velocity, every q, every
    dof velocity. RigidEntity and RigidLink getters are thin wrappers of these solver getters that select one link (or the
    entity's q / dof range); each value is a per-link gather plus the per-link relative-pose offset, so slicing the full
    arrays on the host gives the same numbers (scripts/check_read_state_batch.py compares both every tick, bit for bit).
    Reading each link on its own cost about 700 synchronous GPU->CPU copies per tick on a two-arm scene, 63-84 % of a rigid
    control step (2026-10-01 profiles)."""

    def __init__(self, solver):
        self.pos = to_numpy(solver.get_links_pos(relative=True)).reshape(-1, 3)
        self.quat = to_numpy(solver.get_links_quat(relative=True)).reshape(-1, 4)
        self.vel = to_numpy(solver.get_links_vel()).reshape(-1, 3)
        self.ang = to_numpy(solver.get_links_ang()).reshape(-1, 3)
        self.qpos = to_numpy(solver.get_qpos()).reshape(-1)
        self.dofs_vel = to_numpy(solver.get_dofs_velocity()).reshape(-1)

    def link(self, i):
        return dict(position_m=self.pos[i].copy(), quaternion_wxyz=self.quat[i].copy(),
                    linear_velocity_m_s=self.vel[i].copy(), angular_velocity_rad_s=self.ang[i].copy())

    def entity(self, entity):
        body = dict(self.link(entity.base_link_idx), link_indices=tuple(link.idx for link in entity.links))
        qpos = self.qpos[entity.q_start:entity.q_start + entity.n_qs]
        velocity = self.dofs_vel[entity.dof_start:entity.dof_start + entity.n_dofs]
        return body, dict(
            joints={joint.name: dict(position=qpos[list(joint.qs_idx_local)].copy(),
                    velocity=velocity[list(joint.dofs_idx_local)].copy()) for joint in entity.joints},
            links={link.name: self.link(link.idx) for link in entity.links})


class GenesisWorld:
    """Own a single, non-differentiable rigid/PBD/FEM scene.

    Checkpoints copy native and supplemental numeric engine state. They are
    process-local and valid only for this built scene. Native IPC dumps are
    preserved independently per checkpoint. Batched scenes,
    emitters and differentiable simulation are rejected rather than restored
    from an incomplete pose-only representation.
    """
    _engine_configuration = None

    def __init__(self, scene, *, physics_dt_s=None, entities=None, builder=None, tabletop=None, seed=0):
        self.scene = scene
        self.physics_dt_s = float(scene.dt if physics_dt_s is None else physics_dt_s)
        if not np.isfinite(self.physics_dt_s) or self.physics_dt_s <= 0:
            raise ValueError("physics_dt_s must be finite and positive")
        self.entities = {} if entities is None else entities
        self.tabletop, self._builder = tabletop, builder
        self.physics_step = 0
        self.rng = np.random.default_rng(seed)
        self._world_id = uuid4().hex
        self._last_buffers = ()
        self._buffer_comparison_cache = {}
        self._initial_joint_positions = []
        self._built, self._closed, self._faulted = False, False, False
        self._pbd_table_friction = None
        self._contact_specs = []
        self._contact_collector = None
        self.terminal_contract_version = 1
        self._robot_description = None
        self._grasp_manager = None
        self._material_maps = []
        self._release_geometry = None

    @classmethod
    def from_tabletop(cls, env_cfg, robot_cfg, *, physics_options=None,
                      compute_backend="cpu", precision="64", seed=0, cameras=False):
        import genesis as gs
        from omegaconf import OmegaConf
        from topogym.world.tabletop import StandardTabletopSceneBuilder

        configuration = (str(compute_backend), str(precision))
        if cls._engine_configuration is not None and cls._engine_configuration != configuration:
            raise RuntimeError("Genesis device/precision is fixed for this process")
        if not getattr(gs, "_initialized", False):
            # Quadrants CompileConfig.random_seed requires a signed int32.
            engine_seed = int(seed) & 0x7FFFFFFF
            gs.init(backend=getattr(gs, compute_backend), precision=str(precision), seed=engine_seed,
                    logging_level="warning")
        # Preserve the full uint32 scene seed for Python, NumPy and Torch RNGs.
        gs.set_random_seed(int(seed))
        # The cached declaration cannot detect an external destroy/re-init.
        # Verify the actual runtime for every construction, including ours.
        actual_precision = str(np.dtype(gs.np_float).itemsize * 8)
        if gs.backend != getattr(gs, compute_backend) or actual_precision != str(precision):
            raise RuntimeError("The initialized Genesis runtime has different device/precision settings")
        cls._engine_configuration = configuration
        env_cfg = OmegaConf.create(OmegaConf.to_container(env_cfg, resolve=True))
        if not cameras:
            env_cfg.cameras = {}
        if int(env_cfg.sim.get("n_envs", 0)) != 0:
            raise ValueError("GenesisWorld currently requires one unbatched environment")
        options = physics_options or {}
        if set(options) - {"rigid", "pbd", "fem", "ipc", "pbd_table_friction"}:
            raise ValueError("Unknown physics option group")
        ipc = "ipc" in options
        friction = None
        if "pbd_table_friction" in options:
            if ipc or "pbd" not in options:
                raise ValueError("PBD table friction requires the legacy PBD coupler")
            from .physics.pbd_table_friction import TabletopPBDFriction
            table = env_cfg.world.table
            center, half = np.asarray(table.pos[:2]), np.asarray(table.size[:2])/2
            friction = TabletopPBDFriction(bounds=(center-half, center+half),
                surface_z=float(table.pos[2]+table.size[2]/2), **dict(options["pbd_table_friction"]))
        extra = {}
        if ipc:
            from .physics.ipc import require_episode_checkpoint, scene_options
            require_episode_checkpoint(compute_backend)
            extra = dict(fem_options=gs.options.FEMOptions(**dict(options.get("fem", {}))),
                         coupler_options=scene_options(options["ipc"]))
        builder = StandardTabletopSceneBuilder(
            env_cfg, robot_cfg,
            rigid_options=gs.options.RigidOptions(**dict(options.get("rigid", {}))),
            pbd_options=gs.options.PBDOptions(**dict(options["pbd"])) if "pbd" in options else None,
            scene_options=extra)
        try:
            materials = dict(robot_material=gs.materials.Rigid(gravity_compensation=1.0))
            if ipc:
                materials.update(robot_material=gs.materials.Rigid(gravity_compensation=1., coup_type="external_articulation"),
                                 static_material=gs.materials.Rigid(coup_type="ipc_only"),
                                 table_material=gs.materials.Rigid(coup_type="ipc_only"),
                                 decoration_material=gs.materials.Rigid(needs_coup=False))
            base = builder.create(show_viewer=False, include_robot=True,
                                  **materials)
            if ipc:
                from .physics.ipc import install_for_scene
                from topogym.robot.description import describe_robot
                positions = {name: value for group in describe_robot(robot_cfg).groups
                             for name, value in zip(group.arm_joints+group.finger_joints, group.home)}
                install_for_scene(base.scene, initial_robot_positions=positions)
        except BaseException:
            partial_scene = getattr(builder, "_scene_under_construction", None)
            if partial_scene is not None:
                partial_scene.destroy()
            raise
        world = cls(base.scene, physics_dt_s=env_cfg.sim.dt, entities=base.entity_registry.entities,
                    builder=builder, tabletop=base, seed=seed)
        world._pbd_table_friction = friction
        from topogym.robot.description import describe_robot
        world._robot_description = describe_robot(robot_cfg)
        return world

    @property
    def sim_time_s(self):
        return self.physics_step * self.physics_dt_s

    @property
    def cameras(self):
        return {} if self.tabletop is None else self.tabletop.cameras

    def add_entities(self, specifications):
        self._require_open()
        if self._built:
            raise RuntimeError("Task entities must be declared before World.build")
        import genesis as gs

        from topogym.assets.materials import MaterialSpec
        from topogym.world.visuals.surfaces import from_spec as surface_from_spec
        for spec in specifications:
            if spec.name in self.entities:
                raise ValueError(f"Duplicate world entity: {spec.name}")
            kwargs = dict(spec.morph_options)
            if spec.morph_type == "urdf":
                # Nyx exports the original URDF link structure. Genesis'
                # default merges fixed links, which its Nyx exporter rejects
                # even for a single-link asset. Keep RGB and non-RGB topology
                # identical by choosing this default before scene creation.
                kwargs.setdefault("merge_fixed_links", False)
            kwargs.update(pos=tuple(spec.position_m), quat=tuple(spec.quaternion_wxyz))
            if spec.morph_type in {"urdf", "mesh", "mjcf"}:
                kwargs["file"] = str(spec.asset_path)
            MaterialSpec(spec.physics_model, spec.material)
            if spec.physics_model == "rigid":
                if spec.morph_type == "mjcf":
                    # MJCF encodes articulation/free joints in the document;
                    # Genesis' MJCF morph has no `fixed` option.
                    if spec.fixed:
                        raise ValueError("Fixed MJCF entities must encode their fixed base in the model")
                else:
                    kwargs["fixed"] = bool(spec.fixed)
                material = gs.materials.Rigid(**dict(spec.material))
            elif spec.physics_model in {"pbd_cloth", "pbd_elastic"}:
                if spec.fixed:
                    raise ValueError("PBD cloth pinning requires an explicit constraint declaration")
                from .physics.pbd import material as pbd_material
                material = pbd_material(spec.physics_model, spec.material)
            elif spec.physics_model == "fem_elastic":
                from .physics.fem import material as fem_material
                material = fem_material(spec.material)
                if spec.volume_path is None:
                    raise ValueError("FEM requires a volume asset with explicit reference coordinates")
            else:
                raise ValueError(f"Unsupported physical model: {spec.physics_model}")
            morphs = {"urdf": gs.morphs.URDF, "mesh": gs.morphs.Mesh,
                      "mjcf": gs.morphs.MJCF, "box": gs.morphs.Box,
                      "sphere": gs.morphs.Sphere, "cylinder": gs.morphs.Cylinder}
            if spec.morph_type not in morphs:
                raise ValueError(f"Unknown entity morph: {spec.morph_type}")
            morph = morphs[spec.morph_type](**kwargs)
            surface = surface_from_spec(spec.surface)
            if spec.physics_model == "fem_elastic":
                from .physics.fem import add_volume
                self.entities[spec.name] = add_volume(self.scene, spec, morph, material, surface)
            else:
                self.entities[spec.name] = self.scene.add_entity(morph, material=material, surface=surface, name=spec.name)
            self._initial_joint_positions.append((spec.name, dict(spec.initial_joint_positions)))
            if spec.contact_roles:
                self._contact_specs.append(spec)
            if spec.material_map_path is not None:
                if spec.physics_model != "pbd_cloth":
                    raise ValueError("material_map_path currently supports PBD cloth only")
                self._material_maps.append((spec.name, spec.material_map_path))

    def add_attachments(self, specifications):
        coupler = self.scene.sim.coupler
        if self._built or not hasattr(coupler, "attachments"):
            raise ValueError("Attachments require an unbuilt IPC World")
        coupler.attachments = tuple(specifications)
        coupler.named_entities = self.entities

    def build(self):
        self._require_open()
        if self._built:
            raise RuntimeError("World.build may only be called once")
        try:
            # Match authored frames before Genesis re-expresses free-body geoms
            # around the COM at build. Geometry IDs survive that alignment.
            roles, complete = {}, True
            if self._contact_specs or self.terminal_contract_version == 2:
                from .physics.rigid_contacts import resolve_roles, resolve_robot_parts, RigidContactCollector
                for spec in self._contact_specs:
                    mapping, covered = resolve_roles(self.entities[spec.name], spec)
                    roles.update(mapping)
                    complete &= covered
            if self._builder is None:
                self.scene.build(n_envs=0)
            else:
                self._builder.finalize(self.tabletop)
            self._built = True
            for name, path in self._material_maps:
                from .physics.pbd import bind_material_map
                bind_material_map(self.entities[name], path)
            self._check_checkpoint_support()
            for name, targets in self._initial_joint_positions:
                entity = self.entities[name]
                for joint_name, value in targets.items():
                    joint = entity.get_joint(joint_name)
                    if len(joint.dofs_idx_local) != 1 or not np.isfinite(value):
                        raise ValueError('Initial scalar joint position requires one finite coordinate')
                    entity.set_dofs_position([float(value)], joint.dofs_idx_local, zero_velocity=True)
            if self._contact_specs or self.terminal_contract_version == 2:
                imported_ids = {int(g.idx) for spec in self._contact_specs
                    for link in self.entities[spec.name].links for g in link.geoms}
                complete &= imported_ids == set(roles)
                robot = self.entities.get("robot")
                if robot is not None:
                    roles.update({int(g.idx): "robot" for link in robot.links for g in link.geoms})
                parts, robot_complete = resolve_robot_parts(robot, self._robot_description)
                self._contact_collector = RigidContactCollector(self.scene, roles, geometry_complete=complete,
                    robot_parts=parts, robot_geometry_complete=robot_complete,
                    collect_snapshots=self.terminal_contract_version == 2,
                    grasp=lambda: self._grasp_manager.read() if self._grasp_manager is not None else {})
        except BaseException:
            self._faulted = True
            self.close()
            raise

    def prepare_grasp(self, config):
        """Declare solver resources before build; no active hand constraints."""
        if self._built:
            raise RuntimeError("Prepare grasp before build")
        for target in config.targets:
            if target.entity not in self.entities:
                raise ValueError(f"Unknown soft grasp entity: {target.entity}")
            entity = self.entities[target.entity]
            if config.model == "ipc_soft_band_v1":
                if entity not in self.scene.sim.fem_solver.entities or not hasattr(entity, "material_coordinates"):
                    raise ValueError("IPC soft grasp requires an explicit FEM volume")
            elif config.model == "pbd_local_patch_v1":
                import genesis as gs
                if not isinstance(entity.material, gs.materials.PBD.Cloth):
                    raise ValueError("PBD local patch grasp requires cloth")
                if target.entity not in {name for name, _ in self._material_maps}:
                    raise ValueError("PBD local patch grasp requires material_map_path")
        if config.model == "ipc_soft_band_v1":
            coupler = self.scene.sim.coupler
            if not hasattr(coupler, "fem_grasp_specs"):
                raise ValueError("ipc_soft_band_v1 requires an IPC scene")
            coupler.fem_grasp_specs = {self.entities[t.entity]: t for t in config.targets}

    def configure_grasp(self, robot, config):
        """Owner-only setup after initial preparation and before episode birth."""
        self._require_built()
        if self.physics_step or self._grasp_manager is not None:
            raise RuntimeError("Grasp assistance must be configured once at episode birth")
        if config.model == "none":
            return
        from .physics.grasp_manager import GraspManager
        if config.model == "contact_weld_v1":
            from .physics.grasp_rigid import RigidGraspBackend as Backend
        elif config.model == "ipc_soft_band_v1":
            from .physics.grasp_ipc import IPCGraspBackend as Backend
        elif config.model == "pbd_local_patch_v1":
            from .physics.grasp_pbd import PBDGraspBackend as Backend
        else:
            raise ValueError("Unknown grasp model")
        self._grasp_manager = GraspManager(Backend(self, robot, config), config)

    def advance(self):
        self._require_built()
        if self._faulted:
            raise RuntimeError("World is faulted; restore an existing state before advancing")
        before = int(self.scene.t)
        try:
            if self._grasp_manager is not None:
                self._grasp_manager.before_tick(self.physics_step + 1)
            if self._contact_collector is not None:
                self._contact_collector.begin(self.physics_step + 1)
            self.scene.step()
            if self._pbd_table_friction is not None:
                self._pbd_table_friction.apply(self)
        except BaseException:
            # Genesis may have completed the integration before a visualizer
            # raises. Preserve that actual clock instead of inventing success.
            self.physics_step += max(0, int(self.scene.t) - before)
            self._faulted = True
            raise
        finally:
            if self._contact_collector is not None:
                self._contact_collector.end()
        elapsed = int(self.scene.t) - before
        self.physics_step += max(0, elapsed)
        if elapsed != 1:
            self._faulted = True
            raise RuntimeError(f"One World.advance must complete one Genesis tick, observed {elapsed}")
        try:
            if self._grasp_manager is not None:
                self._grasp_manager.after_tick(self.physics_dt_s)
        except BaseException:
            self._faulted = True
            raise

    def reset_clock(self):
        """Start the episode clock after initialization, without modifying physics."""
        self._require_built()
        if self._faulted:
            raise RuntimeError("Cannot restart the episode clock in a faulted world")
        if self._grasp_manager is not None:
            raise RuntimeError("Configure grasp assistance after restarting the episode clock")
        self.physics_step = 0
        if self._contact_collector is not None:
            self._contact_collector.birth()

    def configure_final_settling(self, rigid_targets):
        """Enable read-only clearance evidence only for tasks that require release."""
        self._require_built()
        from .physics.release_geometry import ReleaseGeometry
        self._release_geometry = ReleaseGeometry(self, rigid_targets)

    def read_state(self):
        self._require_built()
        bodies, particles, articulations, fem = {}, {}, {}, {}
        rigid, readout = self.scene.sim.rigid_solver, None
        for name, entity in self.entities.items():
            if hasattr(entity, "material_coordinates"):
                from .physics.fem import read_vertices
                fem[name] = read_vertices(entity)
            elif hasattr(entity, "get_particles_pos"):
                particles[name] = dict(position_m=to_numpy(entity.get_particles_pos()).reshape(-1, 3),
                                       velocity_m_s=to_numpy(entity.get_particles_vel()).reshape(-1, 3))
            elif getattr(entity, "_solver", None) is rigid:
                readout = readout or _RigidReadout(rigid)
                bodies[name], articulations[name] = readout.entity(entity)
            elif hasattr(entity, "get_pos"):
                bodies[name] = dict(position_m=to_numpy(entity.get_pos()).reshape(-1, 3)[0],
                                    quaternion_wxyz=to_numpy(entity.get_quat()).reshape(-1, 4)[0],
                                    linear_velocity_m_s=to_numpy(entity.get_vel()).reshape(-1, 3)[0],
                                    angular_velocity_rad_s=to_numpy(entity.get_ang()).reshape(-1, 3)[0],
                                    link_indices=tuple(link.idx for link in entity.links))
                qpos = to_numpy(entity.get_qpos()).reshape(-1)
                velocity = to_numpy(entity.get_dofs_velocity()).reshape(-1)
                articulations[name] = dict(
                    joints={joint.name: dict(position=qpos[list(joint.qs_idx_local)].copy(),
                            velocity=velocity[list(joint.dofs_idx_local)].copy()) for joint in entity.joints},
                    links={link.name: dict(position_m=to_numpy(link.get_pos()).reshape(-1, 3)[0],
                            quaternion_wxyz=to_numpy(link.get_quat()).reshape(-1, 4)[0],
                            linear_velocity_m_s=to_numpy(link.get_vel()).reshape(-1, 3)[0],
                            angular_velocity_rad_s=to_numpy(link.get_ang()).reshape(-1, 3)[0]) for link in entity.links})
        coupler = self.scene.sim.coupler
        if hasattr(coupler, "rigid_velocities"):
            for name, (linear, angular) in coupler.rigid_velocities().items():
                bodies[name]["linear_velocity_m_s"] = linear
                bodies[name]["angular_velocity_rad_s"] = angular
                link = articulations[name]["links"][self.entities[name].base_link.name]
                link["linear_velocity_m_s"], link["angular_velocity_rad_s"] = linear.copy(), angular.copy()
        contacts = {}
        if rigid.is_active:
            values = rigid.collider.get_contacts(as_tensor=True, to_torch=True)
            contacts = {key: to_numpy(values[key]) for key in ("link_a", "link_b", "force", "penetration")}
        diagnostics = self.scene.sim.coupler.diagnostics() if fem else {}
        result = dict(bodies=bodies, particles=particles, fem=fem, articulations=articulations, contacts=contacts, ipc=diagnostics,
                    pose_convention="Genesis relative=True authored link poses; wxyz; native world-frame velocities",
                    physics_step=self.physics_step, sim_time_s=self.sim_time_s,
                    assist_active=False, assist_model="none")
        if self._grasp_manager is not None:
            if self._release_geometry is not None:
                self._grasp_manager.backend.verify_bindings([
                    s["binding"] for s in self._grasp_manager.hands.values() if s["binding"] is not None])
            grasp = self._grasp_manager.read()
            result.update(assist_active=grasp["active"], assist_model=self._grasp_manager.config.model,
                          grasp=grasp)
        if self._release_geometry is not None:
            result["release_geometry"] = self._release_geometry.read()
        if self._contact_collector is not None:
            result["contact_events"] = self._contact_collector.read()
        result["terminal_contract_version"] = self.terminal_contract_version
        try:
            require_finite_state(result)
        except FloatingPointError:
            self._faulted = True
            raise
        return result

    def _check_checkpoint_support(self):
        if version("genesis-world").split("+", 1)[0] != "1.2.1":
            raise RuntimeError("Full-buffer state capture is currently tied to Genesis 1.2.1")
        if self.scene.requires_grad or self.scene.n_envs != 0 or self.scene._emitters:
            raise NotImplementedError("State capture requires unbatched, forward-only simulation without emitters")
        allowed = {"RigidSolver", "KinematicSolver", "PBDSolver", "FEMSolver"}
        unexpected = {type(s).__name__ for s in self.scene.sim._active_solvers} - allowed
        if unexpected or type(self.scene.sim.coupler).__name__ not in {"LegacyCoupler", "EpisodeIPCCoupler"}:
            raise NotImplementedError(f"Complete state capture is unavailable for {unexpected or 'this coupler'}")
        if any(type(s).__name__ == "FEMSolver" for s in self.scene.sim._active_solvers):
            if getattr(self.scene.sim.coupler, "checkpoint_store", None) is None:
                raise NotImplementedError("FEM requires the complete native IPC checkpoint codec")
        if any(getattr(solver, "_ffs", ()) for solver in self.scene.sim._active_solvers):
            raise NotImplementedError("External force-field Python state has no checkpoint codec")

    def capture_state(self):
        self._require_built()
        if self._faulted:
            raise RuntimeError("Cannot capture a partially failed physical step")
        self._check_checkpoint_support()
        queried = self.scene.get_state()
        native = copy_native_state(queried, device="cpu")
        self.scene.sim._queried_states.discard(queried)
        buffers = capture_engine_buffers(self.scene, self._last_buffers, self._buffer_comparison_cache)
        self._last_buffers = buffers
        flags = []
        for solver in self.scene.sim._active_solvers:
            for name in ("_is_forward_pos_updated", "_is_forward_vel_updated", "_is_backward"):
                if hasattr(solver, name):
                    flags.append((solver, name, getattr(solver, name)))
            constraint = getattr(solver, "constraint_solver", None)
            if constraint is not None and hasattr(constraint, "_eq_const_info_cache"):
                flags.append((constraint, "_eq_const_info_cache", deepcopy(constraint._eq_const_info_cache)))
        inputs = tuple((entity, deepcopy(getattr(entity, "_tgt", {})))
                       for entity in self.scene.sim.entities if hasattr(entity, "_tgt"))
        python_rng, numpy_rng, torch_rng, cuda_rng, world_rng = capture_rng(self.rng)
        store = getattr(self.scene.sim.coupler, "checkpoint_store", None)
        return WorldState(self._world_id, self.physics_step, native, buffers, tuple(flags), inputs,
                          python_rng, numpy_rng, torch_rng, cuda_rng, world_rng,
                          int(self.scene.t), int(self.scene.sim._cur_substep_global),
                          None if store is None else store.capture(),
                          None if self._contact_collector is None else self._contact_collector.read(),
                          None if self._grasp_manager is None else self._grasp_manager.capture())

    def restore_state(self, state):
        self._require_built()
        if not isinstance(state, WorldState) or state.world_id != self._world_id:
            raise ValueError("WorldState belongs to another built world")
        if (state.grasp_state is None) != (self._grasp_manager is None):
            raise ValueError("WorldState grasp configuration mismatch")
        try:
            import genesis as gs
            self.scene.reset(state=copy_native_state(state.native_state, device=gs.device))
            if state.ipc_state is not None:
                self.scene.sim.coupler.checkpoint_store.restore(state.ipc_state)
            # reset clears controls/contact caches; restore their full buffers
            # afterwards, including PBD pin/coupling data and hibernation flags.
            restore_engine_buffers(state.buffers)
            for target, name, value in state.engine_flags:
                setattr(target, name, deepcopy(value))
            for entity, pending in state.entity_inputs:
                entity._tgt = deepcopy(pending)
            self.scene._t = state.scene_tick
            self.scene.sim._cur_substep_global = state.engine_substep
            self.physics_step = state.physics_step
            if self._contact_collector is not None:
                if state.contact_events is None:
                    raise ValueError("Checkpoint lacks contact event history")
                self._contact_collector.restore(state.contact_events)
            if self._grasp_manager is not None:
                self._grasp_manager.restore(state.grasp_state)
            restore_rng(state, self.rng)
            self._last_buffers = state.buffers
            self._buffer_comparison_cache.clear()
            self._faulted = False
        except BaseException:
            self._faulted = True
            raise

    def discard_states(self, states):
        """Drop native on-disk dumps for the explicitly abandoned future."""
        store = getattr(self.scene.sim.coupler, "checkpoint_store", None)
        if store is not None:
            store.discard([state.ipc_state for state in states if state.ipc_state is not None])

    def close(self):
        if self._closed:
            return
        if self._contact_collector is not None:
            self._contact_collector.close()
        try:
            coupler = self.scene.sim.coupler
            if hasattr(coupler, "close"):
                coupler.close(getattr(self, "diagnostics_dir", None) if self._faulted or not self._built else None)
            self.scene.destroy()
        except BaseException:
            # Genesis.destroy can fail partway through renderer/simulator
            # cleanup. Keep the scene reachable and allow close to be retried.
            self._faulted = True
            raise
        self._closed = True
        self.entities.clear()
        self._last_buffers = ()
        self._buffer_comparison_cache.clear()

    def _require_open(self):
        if self._closed:
            raise RuntimeError("World is closed")

    def _require_built(self):
        self._require_open()
        if not self._built:
            raise RuntimeError("World has not been built")
