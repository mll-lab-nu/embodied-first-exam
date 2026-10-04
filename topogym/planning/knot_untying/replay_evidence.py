"""Attach the shared numerical evidence writer to native Knot replay ticks.

The observer never advances the world, changes actions, resets it, or changes
the native success result. Recording failures propagate; incomplete evidence
cannot be presented as a qualified physical replay.
"""
from __future__ import annotations

from pathlib import Path
import shutil

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.recording import RecordingSession
from topogym.recording.encoding import probe
from topogym.simulator.rollout_simulation.evidence import SegmentEvidence
from topogym.utils.arrays import to_numpy
from topogym.utils.io import sha256_file, write_json_atomic
from .collision_audit import rigid_cover_vertices


def export_geometry(env, folder, initial):
    """Save actual collision meshes in authored link frames and the actual FEM asset."""
    world = env._world
    source = env._asset_build.root/'rope_volume.npz'
    shutil.copy2(source, folder/'rope_volume.npz')
    meshes, metadata = {}, []
    entries = [(name, link, geom) for name, entity in world.entities.items()
               if not hasattr(entity, 'material_coordinates') and name in initial['world']['articulations']
               for link in entity.links for geom in link.geoms]
    solver = world.scene.sim.rigid_solver
    indices = [int(geom.idx) for _, _, geom in entries]
    positions = to_numpy(solver.get_geoms_pos(indices, relative=False)).reshape(-1, 3)
    quaternions = to_numpy(solver.get_geoms_quat(indices, relative=False)).reshape(-1, 4)
    turns = Rotation.from_quat(quaternions[:, [1, 2, 3, 0]])
    # geom.get_verts() updates the solver's vertex caches. Read immutable local
    # vertices and copied native world poses instead, as ReleaseGeometry does.
    for (name, link, geom), position, turn in zip(entries, positions, turns, strict=True):
        pose = initial['world']['articulations'][name]['links'][link.name]
        rotation = Rotation.from_quat(np.asarray(pose['quaternion_wxyz'])[[1, 2, 3, 0]])
        vertices = turn.apply(np.asarray(geom.init_verts))+position
        local = rotation.inv().apply(vertices-np.asarray(pose['position_m']))
        key = f'geom_{int(geom.idx)}'
        meshes[key+'_vertices'] = local
        meshes[key+'_faces'] = np.asarray(geom.init_faces, np.int32)
        cover_kind = None
        data = np.asarray(getattr(geom, 'data', []))
        if name in {'robot', 'table'}:
            cover, cover_kind = rigid_cover_vertices(geom.type.name, data, geom.init_verts)
            meshes[key+'_cover_vertices'] = rotation.inv().apply(turn.apply(cover)+position-np.asarray(pose['position_m']))
        metadata.append(dict(key=key, entity=name, link=link.name, link_index=int(link.idx),
                             geom_index=int(geom.idx), native_type=geom.type.name,
                             primitive_position_in_link_m=rotation.inv().apply(position-np.asarray(pose['position_m'])).tolist(),
                             native_convex=bool(geom.is_convex), native_data=data.tolist(), cover_kind=cover_kind))
    np.savez_compressed(folder/'rigid_collision_meshes.npz', **meshes)
    pairs = to_numpy(world.scene.sim.rigid_solver.collider._valid_collision_pairs).reshape(-1, 2)
    write_json_atomic(folder/'collision_model.json', dict(
        schema_version=2, meshes=metadata, native_valid_geometry_pairs=pairs.tolist(), table_height_m=env._task.table_height_m,
        rope_volume_sha256=sha256_file(folder/'rope_volume.npz'),
        rigid_meshes_sha256=sha256_file(folder/'rigid_collision_meshes.npz'),
        frame='authored link-local collision vertices; pose from each recorded articulation',
        extraction='immutable native local vertices and relative=False geom pose readouts; no geometry-cache updates',
        scope='tick-end geometry and native rigid contact summaries; no IPC contact-force or continuous CCD coverage'))


class ReplayCapture:
    def __init__(self, session, folder, *, geometry_exporter=export_geometry,
                 minimum_free_bytes=10 * 1024**3, disk_usage=shutil.disk_usage, record_video=False):
        self.session, self.folder = session, Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.writer = SegmentEvidence(self.folder, session.env, deduplicate_arrays=True)
        self.unsubscribe = None
        self.unsubscribe_frames = None
        self.video = None
        self.last_tick = None
        self.first_state = None
        self.error = None
        self.minimum_free_bytes, self.disk_usage = minimum_free_bytes, disk_usage
        try:
            initial = session.env.tick_record()
            geometry_exporter(session.env, self.folder, initial)
            self.tick(initial)
            self.unsubscribe = session.env.add_state_sink(self.tick)
            if record_video:
                self.video = RecordingSession(self.folder/'recording', fps=30, metadata=dict(
                    scope='same native replay as adjacent full-tick numerical evidence',
                    instance_sha=session.instance_sha, physical_collision_audit_passed=False))
                self.video.__enter__()
                self.frame(session.env.sensor_frame())
                self.unsubscribe_frames = session.env.add_frame_sink(self.frame)
        except BaseException as error:
            self.close(error=f'{type(error).__name__}: {error}')
            raise

    def tick(self, record):
        try:
            state = record['state']
            tick = int(state['physics_step'])
            if tick % 32 == 0 and self.disk_usage(self.folder).free < self.minimum_free_bytes:
                raise OSError('Insufficient free disk for complete physics evidence (10 GiB reserve)')
            if self.first_state is None:
                # Session.replay resets by rewinding S0, which creates a fresh,
                # nonzero branch. Only a branch change *during* this pass is invalid.
                if tick != 0 or not isinstance(state['branch_id'], int) or state['branch_id'] < 0:
                    raise ValueError('Physics evidence must begin at the frozen episode birth')
                self.first_state = dict(state)
            elif (tick != self.last_tick+1 or state['episode_id'] != self.first_state['episode_id']
                  or state['branch_id'] != self.first_state['branch_id'] or state['parent_state_id'] != self.last_state_id):
                raise ValueError('Gap, rewind or cross-episode tick in replay evidence')
            self.writer.tick(record, segment_id=1)
            self.last_tick, self.last_state_id = tick, state['state_id']
        except Exception as error:
            self.error = f'{type(error).__name__}: {error}'
            raise

    def action(self, action, requested_ticks, result):
        self.writer.policy_event('native_replay_action', segment_id=1,
            state_ref=dict(episode_id=self.first_state['episode_id'], state_id=self.last_state_id),
            action_index=self.session.n_steps, submitted_action=np.asarray(action),
            requested_ticks=requested_ticks, executed_ticks=self.session.last_step_ticks,
            episode_end=self.session.episode_end, ended=bool(result))

    def frame(self, frame):
        if (frame.episode_id != self.first_state['episode_id']
                or frame.branch_id != self.first_state['branch_id']
                or frame.state_id != self.last_state_id or frame.physics_step != self.last_tick):
            raise ValueError('Video and numerical evidence refer to different physical states')
        if len(frame.rgb) != 4:
            raise ValueError('Knot ALOHA replay requires all four frozen RGB cameras')
        self.video.append(frame)

    def close(self, result=None, error=None):
        if self.unsubscribe is not None:
            self.unsubscribe()
            self.unsubscribe = None
        if self.unsubscribe_frames is not None:
            self.unsubscribe_frames()
            self.unsubscribe_frames = None
        self.writer.close()
        complete = bool(result is not None and error is None and self.error is None
                        and self.last_tick == self.session.physics_steps
                        and self.writer.ticks == self.last_tick+1)
        video_checks, video_error = None, None
        if self.video is not None:
            try:
                if complete:
                    self.video.append_final(self.session.env.sensor_frame())
                    self.video.finish(dict(native_result=result, physical_collision_audit_passed=False))
                self.video.close(commit=complete)
                if complete:
                    video_checks = {}
                    for name in self.video.writers:
                        check = probe(self.video.output/'videos'/f'{name}.mp4', decode=True)
                        if check['frames'] != self.video.frame_count:
                            raise ValueError('Decoded video count differs from shared frame map')
                        video_checks[name] = check
                    write_json_atomic(self.video.output/'validation.json', video_checks)
            except Exception as exc:
                complete = False
                video_error = exc
                error = f'{type(exc).__name__}: {exc}'
            finally:
                self.video.close(commit=False)
        write_json_atomic(self.folder/'capture.json', dict(
            complete=complete, native_result=result, error=error or self.error,
            last_physics_tick=self.last_tick, **self.writer.statistics(),
            evidence_scope='initial state plus every committed physics tick of one native replay',
            native_safety=self.session.safety(episode=True) if hasattr(self.session, 'safety') else None,
            video_requested=self.video is not None, video_validation=video_checks,
            physical_collision_audit_passed=False))
        if video_error is not None:
            raise video_error


def install_physics_capture(tooling, output, *, capture_factory=ReplayCapture, max_passes=None, record_video=False):
    """Wrap native replay/reset/step calls only to observe them; one folder per pass."""
    native_reset, native_step, native_replay = tooling.Session.reset, tooling.Session.step, tooling.Session.replay
    output = Path(output)
    if max_passes is not None and (type(max_passes) is not int or max_passes < 1):
        raise ValueError('Physical capture pass limit must be a positive integer')
    serial = 0

    def reset(session, *args, **kwargs):
        result = native_reset(session, *args, **kwargs)
        folder = getattr(session, '_knot_capture_pending', None)
        if folder is not None:
            session._knot_capture = capture_factory(session, folder, **({'record_video': True} if record_video else {}))
            del session._knot_capture_pending
        return result

    def step(session, action, **kwargs):
        result = native_step(session, action, **kwargs)
        capture = getattr(session, '_knot_capture', None)
        if capture is not None:
            capture.action(action, kwargs.get('_physics_steps'), result)
        return result

    def replay(session, actions, **kwargs):
        nonlocal serial
        if getattr(session, '_knot_capture', None) is not None:
            raise RuntimeError('Nested physical evidence replay')
        serial += 1
        if max_passes is not None and serial > max_passes:
            return native_replay(session, actions, **kwargs)
        session._knot_capture_pending = output/f'physics_replay_{serial:02d}'
        result, error = None, None
        try:
            result = native_replay(session, actions, **kwargs)
            return result
        except BaseException as exc:
            error = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            capture = getattr(session, '_knot_capture', None)
            if capture is not None:
                capture.close(result, error)
                del session._knot_capture
            if hasattr(session, '_knot_capture_pending'):
                del session._knot_capture_pending

    tooling.Session.reset, tooling.Session.step, tooling.Session.replay = reset, step, replay
