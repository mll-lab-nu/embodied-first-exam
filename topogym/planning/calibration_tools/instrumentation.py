"""Private-worker instrumentation; all patches disappear with this worker."""
def install(owner):
    from topogym.world.genesis_world import GenesisWorld
    from topogym.simulator.env import Env
    from topogym.sensors.observation import SensorSuite
    from topogym.robot import control
    from topogym.solvers.genesis_kinematics import GenesisIKSolver
    from topogym.simulator.rollout_simulation.evidence import SegmentEvidence
    from topogym.simulator.rollout_simulation.history import SegmentHistory
    from topogym.simulator.history import EpisodeHistory
    from topogym.world import initial_state

    p = owner.profiler
    p.wrap(owner.evidence, "event", "development_evidence_io")
    p.wrap(control, "compile_action", "control_compile")
    p.wrap(GenesisIKSolver, "solve_checked", "ik")
    p.wrap(SensorSuite, "sample", "observation")
    p.wrap(Env, "observe", "observe")
    p.wrap(Env, "step", "control_step")
    p.wrap(Env, "_save_state", "state_save")
    p.wrap(Env, "tick_record", "tick_measurement")
    p.wrap(EpisodeHistory, "append", "history_append")
    p.wrap(Env, "_checkpoint_current", "segment_checkpoint")
    p.wrap(GenesisWorld, "read_state", "state_read")
    p.wrap(GenesisWorld, "capture_state", "checkpoint_capture")
    p.wrap(GenesisWorld, "add_entities", "scene_entities")
    p.wrap(initial_state, "restore_declared_initial_state", "initial_state_restore")
    p.wrap(SegmentEvidence, "tick", "tick_evidence_io")
    p.wrap(SegmentEvidence, "write", "journal_io")
    p.wrap(SegmentHistory, "_write", "segment_history_io")

    task = owner.env._task_class
    for name, stage in (("declare", "asset_generation"), ("finalize_spec", "asset_finalize"),
                        ("initialize", "task_initialize"), ("update", "task_update"),
                        ("get_state", "task_snapshot")):
        p.wrap(task, name, stage)

    def instrument_world(world):
        coupler = world.scene.sim.coupler
        owner.object_drives.install(world)
        p.wrap(coupler, "couple", "ipc_coupling" if hasattr(coupler, "_ipc_world") else "coupling", optional=True)
        if hasattr(coupler, "_ipc_world"):
            for name, stage in (("_store_gs_rigid_states", "ipc_rigid_upload"),
                                ("_retrieve_fem_states", "ipc_fem_retrieve"),
                                ("_retrieve_rigid_states", "ipc_rigid_retrieve"),
                                ("_check_articulation_sync", "ipc_sync_check")):
                p.wrap(coupler, name, stage, optional=True)
        p.wrap(world.scene.sim, "step", "solver_step")
        visualizer = world.scene.visualizer
        p.wrap(visualizer, "update", "visualizer_update", optional=True)

    def after_create(world, *args, **kwargs):
        instrument_world(world)

    # Attach before build: initialization can itself advance native frames.
    p.wrap(GenesisWorld, "from_tabletop", "scene_create", after=after_create)

    def after_build(result, world, *args, **kwargs):
        for camera in world.cameras.values():
            p.wrap(camera, "render", "render", optional=True)

    p.wrap(GenesisWorld, "build", "scene_build", after=after_build)
    p.wrap(GenesisWorld, "advance", "physics_tick",
           metadata=lambda world: dict(target_physics_step=world.physics_step+1))
    # pybind types are optional instrumentation points, never replace a native
    # World with a proxy or change its synchronization/solver configuration.
    if owner.env._task_class.physics_model == "fem_ipc":
        import uipc
        native = uipc.World
        p.wrap(native, "advance", "ipc_native_advance", optional=True,
               metadata=lambda world: dict(target_native_frame=int(world.frame())+1),
               after=lambda result, world: dict(native_frame=int(world.frame()), native_valid=bool(world.is_valid())))
        p.wrap(native, "retrieve", "ipc_native_retrieve", optional=True)
        p.wrap(native, "dump", "ipc_checkpoint_dump", optional=True)
        p.wrap(native, "sync", "ipc_explicit_sync", optional=True)
    return p
