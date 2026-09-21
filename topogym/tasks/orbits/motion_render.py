"""Shared Nyx four-camera playback of measured Orbits states.

The PBD entity is only a graphics carrier. Its mesh vertices are uploaded from
the recorded MuJoCo cord, and no Genesis physics step is taken during replay.
"""
from pathlib import Path
import shutil

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from .geometry import tube_mesh


class MotionRenderer:
    def __init__(self,cfg,initial_points,folder):
        import genesis as gs
        import torch
        from topogym.world import StandardTabletopSceneBuilder
        from topogym.robot import initialize_robot_controller
        self.cfg=cfg;self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.yaw=Rotation.from_euler('z',float(cfg.task.yaw_deg),degrees=True)
        self.origin=np.r_[cfg.task.origin_xy_m,float(cfg.env.frames.table_surface.origin[2])]
        self.radius=float(cfg.task.geometry.cord_radius_m)*float(cfg.task.scale)
        self.handle_origin=np.array([float(cfg.task.geometry.handle_x_m)*float(cfg.task.scale),0,
                                     float(cfg.task.geometry.handle_height_m)*float(cfg.task.scale)/2+.00135])
        cameras={new:OmegaConf.to_container(cfg.env.cameras[old],resolve=True)
                 for new,old in [('cam_high','overhead'),('cam_low','front_oblique'),
                                 ('cam_left_wrist','wrist'),('cam_right_wrist','wrist_right')]}
        for spec in cameras.values():spec['res']=[1280,720]
        cfg.env.cameras=OmegaConf.create(cameras)
        OmegaConf.save(cfg,self.folder/'render_config.yaml',resolve=True)
        builder=StandardTabletopSceneBuilder(cfg.env,cfg.robot_control,
                    pbd_options=gs.options.PBDOptions(particle_size=.004))
        self.base=builder.create(show_viewer=False,include_robot=True,
                                robot_material=gs.materials.Rigid(gravity_compensation=1.))
        fixture=Path(__file__).resolve().parents[3]/'runs/demo_metadata/orbits/2026-09-20_static_base_centered_v5/assets'
        assets=self.folder/'assets';assets.mkdir(exist_ok=True)
        for source in fixture.glob('*.glb'):
            if source.stem in ('cord','scene'):continue
            shutil.copy2(source,assets/source.name)
            position = self.origin
            if source.stem == 'handle':
                import trimesh
                centered = trimesh.load(assets/source.name, force='scene', process=False)
                centered.apply_translation(-self.handle_origin)
                centered.export(assets/source.name)
                position = self.yaw.apply(self.handle_origin)+self.origin
            entity=self.base.scene.add_entity(gs.morphs.Mesh(file=str(assets/source.name),
                pos=position,quat=self.yaw.as_quat()[[3,0,1,2]],fixed=source.stem!='handle',
                collision=False,convexify=False,decimate=False,file_meshes_are_zup=True),
                material=gs.materials.Rigid(),name=f'orbits_{source.stem}')
            if source.stem=='handle':self.handle=entity
        points=self.yaw.apply(initial_points)+self.origin
        mesh=tube_mesh(points,self.radius,sides=12)
        mesh.export(assets/'cord_render.obj')
        self.cord=self.base.scene.add_entity(gs.morphs.Mesh(file=str(assets/'cord_render.obj'),
                collision=False,convexify=False,decimate=False,file_meshes_are_zup=True),
                material=gs.materials.PBD.Cloth(),surface=gs.surfaces.Rough(color=(.95,.78,.03)),
                name='recorded_cord_surface')
        builder.finalize(self.base)
        initialize_robot_controller(scene=self.base.scene,manifest=self.base.manifest,
                                    robot_cfg=cfg.robot_control,settle_steps=0)
        self.robot=self.base.manifest.get('robot')
        distance,self.vertex_map=cKDTree(mesh.vertices).query(self.cord._vverts)
        if distance.max()>1e-6:raise ValueError('Render mesh vertex binding differs from recorded tube')
        self.renderer=next(iter(self.base.cameras.values())).sensor._shared_metadata.renderer
        if self.renderer._num_pbd_verts!=len(self.vertex_map):raise ValueError('Unexpected extra PBD graphics entities')
        self.vertices=torch.as_tensor(np.asarray(mesh.vertices)[self.vertex_map].copy(),dtype=torch.float32,device='cuda')
        original=self.renderer._update_geometry_tensors
        def upload(env_index):
            original(env_index)
            self.renderer._deformable_pbd_verts_view.copy_(self.vertices)
        self.renderer._update_geometry_tensors=upload

    def set_state(self,points,*,robot_qpos=None,handle_pose=None):
        import torch
        world=self.yaw.apply(points)+self.origin
        vertices=np.asarray(tube_mesh(world,self.radius,sides=12).vertices)[self.vertex_map]
        self.vertices.copy_(torch.as_tensor(vertices.copy(),dtype=torch.float32,device='cuda'))
        if robot_qpos is not None:self.robot.set_qpos(robot_qpos,zero_velocity=True)
        if handle_pose is not None:
            rotation=Rotation.from_quat(np.asarray(handle_pose[3:])[[1,2,3,0]])
            # The playback asset is centered at the physical handle body origin.
            position=self.yaw.apply(np.asarray(handle_pose[:3]))+self.origin
            self.handle.set_pos(position)
            self.handle.set_quat((self.yaw*rotation).as_quat()[[3,0,1,2]])

    def frames(self):
        self.base.scene.visualizer.update_visual_states(force_render=True)
        return {name:camera.render(force_render=i==0)[0]
                for i,(name,camera) in enumerate(self.base.cameras.items())}


def render_native(folder, *, stride=2):
    """Four synchronized views of one recorded native development run."""
    import imageio.v2 as imageio
    import genesis as gs
    import json
    from contextlib import ExitStack
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    folder = Path(folder)
    with np.load(folder/'trajectory.npz') as saved:
        trajectory = {k: saved[k] for k in saved.files}
    config_path = folder/'config.yaml'
    if config_path.exists():
        cfg = OmegaConf.load(config_path)
    else:
        # Compatibility with early approach probes that predate config snapshots.
        with initialize_config_dir(config_dir=str(Path(__file__).resolve().parents[3]/'configs'), version_base='1.3'):
            cfg = compose(config_name='orbits_preview')
    if not isinstance(stride, int) or stride < 1:
        raise ValueError('Playback stride must be a positive integer')
    gs.init(backend=gs.gpu, logging_level='warning')
    renderer = MotionRenderer(cfg, trajectory['points'][0], folder/'four_views')
    indices = np.arange(0, len(trajectory['time_s']), stride)
    fps = 1./np.median(np.diff(trajectory['time_s'][indices]))
    with ExitStack() as stack:
        writers = {name: stack.enter_context(imageio.get_writer(
            folder/'four_views'/f'{name}.mp4', fps=fps, codec='libx264',
            quality=8, macro_block_size=1)) for name in renderer.base.cameras}
        for frame_number, i in enumerate(indices):
            renderer.set_state(trajectory['points'][i], robot_qpos=trajectory['qpos'][i, :16],
                               handle_pose=trajectory['qpos'][i, 16:23])
            for name, rgb in renderer.frames().items():
                writers[name].append_data(rgb)
                if frame_number in (0, len(indices)-1):
                    imageio.imwrite(folder/'four_views'/f'{name}_{frame_number}.png', rgb)
            if frame_number % 80 == 0:
                print(f'{frame_number}/{len(indices)}', flush=True)
    (folder/'four_views'/'playback.json').write_text(json.dumps(dict(
        scope='measured_native_development_run_replay', full_task_success=False,
        source=str(folder/'trajectory.npz'), frames=len(indices), fps=fps,
        config_source=str(config_path) if config_path.exists() else 'legacy default orbits_preview',
        sample_indices=indices.tolist(), genesis_simulation_steps=0), indent=2)+'\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--stride', type=int, default=2)
    args = parser.parse_args()
    render_native(args.folder, stride=args.stride)
