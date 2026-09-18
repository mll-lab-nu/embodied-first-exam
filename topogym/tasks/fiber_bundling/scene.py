"""Shared tabletop, fixed ring and a cable permanently wired to a terminal."""
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import COLORS, COPPER_COLOR, FILLER_COLOR, JACKET_COLOR, FiberLayout, generate_assets


def as_numpy(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def apply_cable_colors(bundle):
    """Keep each insulated conductor's color when Nyx exports MJCF geometry."""
    from trimesh.visual.color import ColorVisuals
    for link in bundle.links:
        color = (COLORS[int(link.name.split("_")[1]) % len(COLORS)]
                 if link.name.startswith("fiber_") else JACKET_COLOR)
        for geom in link.vgeoms:
            name = geom.vmesh.metadata["name"]
            shade = COPPER_COLOR if name.startswith("copper_") else FILLER_COLOR if name == "jacket_inner_filler" else color
            if name.startswith("terminal_"):
                from .anchored_geometry import part_color
                shade = part_color(name)
            geom.vmesh.set_color(shade)
            geom.vmesh.trimesh.visual = ColorVisuals(mesh=geom.vmesh.trimesh,
                vertex_colors=(np.array(shade)*255).astype(np.uint8))


def cable_state(bundle, layout):
    """Read actual link transforms, including constrained roots and free tips."""
    positions = as_numpy(bundle.get_links_pos())
    quaternions = as_numpy(bundle.get_links_quat())

    def pose(name):
        index = bundle.get_link(name).idx_local
        return positions[index], Rotation.from_quat(quaternions[index][[1, 2, 3, 0]])

    tip, rotation = pose(f"trunk_{layout.trunk_segments-1:02d}")
    roots, paths, errors = [], [], []
    for i in range(layout.fiber_count):
        phase = 2*np.pi*i/layout.fiber_count
        expected = tip+rotation.apply([layout.trunk_length_m/layout.trunk_segments,
                                     layout.root_spread_m*np.cos(phase), layout.root_spread_m*np.sin(phase)])
        points = []
        for j in range(layout.fiber_segments):
            p, r = pose(f"fiber_{i:02d}_{j:02d}")
            points.append(p)
        points.append(p+r.apply([layout.fiber_length_m/layout.fiber_segments, 0, 0]))
        roots.append(points[0])
        errors.append(np.linalg.norm(points[0]-expected))
        paths.append(points)
    return {"fibers_m": np.asarray(paths), "roots_m": np.asarray(roots),
            "max_root_error_m": float(max(errors))}


@dataclass
class FiberScene:
    tabletop: Any
    layout: FiberLayout
    bundle: Any
    ring: Any
    asset_report: dict
    ring_center: np.ndarray
    origin: Any = None
    verifier: Any = None
    contact_guard: Any = None
    last_step_state: Any = None

    @property
    def scene(self):
        return self.tabletop.scene

    @property
    def cameras(self):
        return self.tabletop.cameras

    @property
    def manifest(self):
        return self.tabletop.manifest

    def grasp_target(self, link_name):
        """The task's grasp interface only exposes the thick trunk."""
        if link_name not in self.asset_report["graspable_links"]:
            raise ValueError("Only trunk links can be grasp targets; fibers are passive")
        return self.bundle.get_link(link_name)

    def state(self):
        state = cable_state(self.bundle, self.layout)
        state["contact_rule"] = self.contact_guard.report()
        state["failed"] = state["contact_rule"]["failed"]
        state["terminated"] = state["failed"]
        # Strict whole-strand check; a tip crossing alone never counts as done.
        exit_plane = self.ring_center[0]+self.layout.ring_tube_radius_m
        state["fibers_fully_beyond_ring"] = (
            state["fibers_m"][:, :, 0].min(axis=1)-self.layout.fiber_radius_m > exit_plane)
        if self.asset_report.get("terminal_fixed"):
            positions=as_numpy(self.bundle.get_links_pos())
            names=self.asset_report["coarse_link_names"]
            # Fine roots are on the same rigid end face, so their mean is its center.
            state["coarse_m"]=np.vstack([positions[[self.bundle.get_link(n).idx_local for n in names]],
                                         state["roots_m"].mean(axis=0)])
            state["threading"]=self.verifier.update(coarse=state["coarse_m"],fibers=state["fibers_m"],
                terminal_pos=as_numpy(self.bundle.get_pos()),terminal_quat=as_numpy(self.bundle.get_quat()),
                ring_pos=as_numpy(self.ring.get_pos()),ring_quat=as_numpy(self.ring.get_quat()),
                forbidden_contact=self.contact_guard.first_contact)
            for key in ("success", "failed", "terminated", "invalid_reasons"):
                state[key] = state["threading"][key]
        return state

    def step(self):
        """Advance physics; return latched failure and episode termination flags."""
        self.scene.step()
        return self.state()


class FiberSceneBuilder:
    def __init__(self, env_cfg, task_cfg, robot_cfg):
        self.env_cfg, self.task_cfg, self.robot_cfg = env_cfg, task_cfg, robot_cfg

    def build(self, *, asset_dir, show_viewer=False):
        import genesis as gs
        from pathlib import Path
        from omegaconf import OmegaConf
        from topogym.world import StandardTabletopSceneBuilder

        cfg = self.task_cfg
        from .contact_precision import CONTACT_MODEL, install_capsule_contact_fix
        contact_model = str(cfg.get("contact_model", "genesis_default"))
        if contact_model == CONTACT_MODEL:
            install_capsule_contact_fix()
        elif contact_model != "genesis_default":
            raise ValueError(f"Unknown cable contact model: {contact_model}")
        if str(cfg.variant) not in ("branched_passive_v1","anchored_terminal_v2"):
            raise ValueError("Unknown fiber bundling variant; refusing a silent free-cable fallback")
        layout = FiberLayout(**OmegaConf.to_container(cfg.geometry, resolve=True))
        anchored = str(cfg.variant)=="anchored_terminal_v2"
        if anchored:
            from .anchored_geometry import AnchoredLayout, generate_anchored_assets
            anchor=AnchoredLayout.from_task_config(cfg)
            layout,report=generate_anchored_assets(asset_dir,layout,anchor)
        else:
            layout, report = generate_assets(asset_dir,layout)
        folder = Path(asset_dir).resolve()
        report["contact_model"] = contact_model
        from .ring_mount import RingMount, export_fixture
        from .numerics import constraint_solver_name
        mount = RingMount.from_task_config(cfg)
        export_fixture(folder, layout, mount,
            (layout.trunk_length_m+float(cfg.ring_distance_from_roots_m),0.,0.),
            -float(cfg.axis_height_m), report)
        builder = StandardTabletopSceneBuilder(self.env_cfg, self.robot_cfg,
            rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
                enable_joint_limit=True, iterations=100, max_collision_pairs=4096,
                constraint_solver=getattr(gs.constraint_solver,constraint_solver_name(cfg)),
                constraint_timeconst=.002))
        base = builder.create(show_viewer=show_viewer, include_robot=True,
                              robot_material=gs.materials.Rigid(gravity_compensation=1.0))
        scene, manifest = base.scene, base.manifest
        floor = base.frames.table_surface_origin[2]
        origin = np.array([*cfg.trunk_origin_xy_m, floor+float(cfg.axis_height_m)])
        center = origin+np.array([layout.trunk_length_m+float(cfg.ring_distance_from_roots_m), 0, 0])
        farthest = max(p[:, 0].max() for p in layout.fibers())
        if origin[0]+farthest+layout.fiber_radius_m >= center[0]-layout.ring_tube_radius_m:
            raise ValueError("Reset fibers intersect the ring plane; increase initial ring distance")
        bundle = manifest.add("fiber_bundle", scene.add_entity(gs.morphs.MJCF(
            file=str(folder/"bundle.xml"), pos=origin, convexify=True, decimate=False),
            material=gs.materials.Rigid(friction=.35, gravity_compensation=1.), name="fiber_bundle"))
        # Explicit per-geometry colors avoid Nyx's shared MJCF surface and
        # material.mtl overwrite paths. Exported GLB assets retain PBR finishes.
        apply_cable_colors(bundle)
        if anchored:
            for name,pos,size,color in anchor.cradle_parts(layout):
                manifest.add(name,scene.add_entity(gs.morphs.Box(pos=origin+pos,size=size,fixed=True),
                    material=gs.materials.Rigid(friction=.45),surface=gs.surfaces.Plastic(color=color),name=name))
        ring = manifest.add("bundling_ring", scene.add_entity(gs.morphs.URDF(
            file=str(folder/"ring.urdf"), pos=center, euler=(0, 90, 0), fixed=True,
            merge_fixed_links=False, convexify=True, decimate=False),
            material=gs.materials.Rigid(friction=.35), name="bundling_ring"))
        mount.add_to_scene(scene, layout, center, floor, manifest)
        builder.finalize(base)
        task=FiberScene(base, layout, bundle, ring, report, center,origin)
        from .contact_guard import GripperFineContactGuard, gripper_link_names
        robot=manifest.get("robot")
        fine_links={bundle.get_link(f"fiber_{i:02d}_{j:02d}").idx: f"fiber_{i:02d}_{j:02d}"
                    for i in range(layout.fiber_count) for j in range(layout.fiber_segments)}
        task.contact_guard=GripperFineContactGuard(gripper_link_names(robot),fine_links,
            float(self.env_cfg.sim.dt)/int(self.env_cfg.sim.substeps))
        task.contact_guard.install(scene.sim.rigid_solver)
        if anchored:
            from .anchored_verifier import AnchoredThreadingVerifier
            task.verifier=AnchoredThreadingVerifier(layout,center,origin,origin+anchor.connector_m,
                                                   as_numpy(ring.get_quat()))
            task.state()
            physics_step=scene.step
            def tracked_step(*args,**kwargs):
                result=physics_step(*args,**kwargs)
                task.last_step_state=task.state()
                return result
            # Existing controllers commonly call task.scene.step directly.
            # Keep entry history complete for both that API and task.step().
            scene.step=tracked_step
        return task
