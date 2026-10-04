"""Read-only, full-tick contact/interior-overlap audit; native rules own task success."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from itertools import islice
import multiprocessing
from pathlib import Path

import numpy as np
import psutil
from scipy.spatial.transform import Rotation

# This reader has no Claws semantics: it decodes the shared writer's array schema,
# validates shape/dtype and confines references to the capture's arrays folder.
from topogym.planning.interlocked_claws.evidence import decode_record
from topogym.utils.io import sha256_file, write_json_atomic
from .collision_audit import VolumeCheck
from .contact_geometry import MeasuredCollider, RESOLUTION_M, surface_cell_owners, surface_solid_contacts


class PhysicsAudit:
    def __init__(self, folder):
        folder = Path(folder)
        model = json.loads((folder/'collision_model.json').read_text())
        if model.get('schema_version') != 2:
            raise ValueError('Unknown collision evidence model')
        for name, key in (('rope_volume.npz', 'rope_volume_sha256'),
                          ('rigid_collision_meshes.npz', 'rigid_meshes_sha256')):
            if sha256_file(folder/name) != model[key]:
                raise ValueError(f'Collision geometry hash mismatch: {name}')
        with np.load(folder/'rope_volume.npz', allow_pickle=False) as data:
            self.volume = VolumeCheck(data['rest'], data['elements'])
            self.faces = data['surface_faces'].copy()
            self.surface_owners = surface_cell_owners(self.volume.elements, self.faces)
        self.meshes, self.omitted = {}, []
        with np.load(folder/'rigid_collision_meshes.npz', allow_pickle=False) as data:
            for entry in model['meshes']:
                if entry['entity'] not in {'robot', 'table'}:
                    self.omitted.append(entry)
                    continue
                index = int(entry['geom_index'])
                if index in self.meshes:
                    raise ValueError('Repeated collider index')
                required = {'MESH': 'convex_hull_of_native_mesh', 'BOX': 'analytic_box_corners',
                            'SPHERE': 'circumscribed_native_sphere_mesh'}
                if entry.get('native_type') not in required or entry.get('cover_kind') != required[entry['native_type']]:
                    raise ValueError('Collision evidence does not cover the native primitive')
                key = entry['key']
                self.meshes[index] = dict(entry, collider=MeasuredCollider(entry, data[key+'_vertices'],
                    data[key+'_faces'] if key+'_faces' in data else None, data[key+'_cover_vertices']))
        if {m['entity'] for m in self.meshes.values()} != {'robot', 'table'}:
            raise ValueError('Collision evidence must include robot and table')
        self.pairs = [(int(a), int(b)) for a, b in model['native_valid_geometry_pairs']
                      if a in self.meshes and b in self.meshes]
        if not self.pairs:
            raise ValueError('Missing native robot collision pair coverage')
        self.link_pairs = {tuple(sorted((self.meshes[a]['link_index'], self.meshes[b]['link_index'])))
                           for a, b in self.pairs}

    def measure(self, record):
        world = record['world']
        points = np.asarray(world['fem']['rope']['position_m'])
        volumes = self.volume.measure(points)
        findings, diagnostics, contacts = [], [], 0
        if world['ipc']['native_valid'] is not True:
            findings.append(dict(kind='native_ipc_invalid', severity='failure'))
        if volumes['nonpositive_cells']:
            diagnostics.append(dict(kind='nonpositive_fem_volume', **volumes))
        self_contact = surface_solid_contacts(points, self.volume.elements, self.faces, self.surface_owners)
        contacts += self_contact['boundary_contacts']
        if self_contact['penetrating_cells'] is not None:
            findings.append(dict(kind='rope_volume_interpenetration', severity='penetration',
                                 cells=self_contact['penetrating_cells']))
        colliders = {}
        for index, mesh in self.meshes.items():
            pose = world['articulations'][mesh['entity']]['links'][mesh['link']]
            quaternion = np.asarray(pose['quaternion_wxyz'], float)
            if quaternion.shape != (4,) or not np.isclose(np.linalg.norm(quaternion), 1., atol=1e-8):
                raise ValueError('Invalid measured link quaternion')
            matrix = Rotation.from_quat(quaternion[[1, 2, 3, 0]]).as_matrix()
            colliders[index] = mesh['collider'].placed(matrix, pose['position_m'])
        corners = points[self.volume.elements]
        bounds = corners.min(1), corners.max(1)
        for index, collider in colliders.items():
            relation = collider.against_tets(corners, bounds)
            contacts += relation['contacts']
            if relation['penetrating_cell'] is not None:
                findings.append(dict(kind='rope_collider_interior_overlap', severity='penetration', cell=relation['penetrating_cell'],
                                     geom_index=index, entity=self.meshes[index]['entity'], link=self.meshes[index]['link']))
            if relation['unresolved']:
                findings.append(dict(kind='unresolved_rope_collider_contact', severity='unresolved',
                                     geom_index=index, cells=relation['unresolved']))
        for a, b in self.pairs:
            relation = colliders[a].against(colliders[b])
            contacts += int(relation == 'contact')
            if relation in {'penetrating', 'unresolved'}:
                findings.append(dict(kind='rigid_interior_overlap' if relation == 'penetrating' else 'unresolved_rigid_contact',
                                     severity='penetration' if relation == 'penetrating' else 'unresolved', geometry_pair=[a, b],
                                     links=[self.meshes[i]['link'] for i in (a, b)]))
        contact = world.get('contacts') or {}
        maximum_penetration = 0.
        if contact:
            aa, bb, depths = [np.asarray(contact[k]).reshape(-1) for k in ('link_a', 'link_b', 'penetration')]
            if len({len(aa), len(bb), len(depths)}) != 1 or not np.isfinite(depths).all():
                raise ValueError('Invalid native rigid contact readout')
            for a, b, depth in zip(aa, bb, depths, strict=True):
                if tuple(sorted((int(a), int(b)))) in self.link_pairs:
                    maximum_penetration = max(maximum_penetration, float(depth))
            if maximum_penetration > 0:
                diagnostics.append(dict(kind='native_rigid_contact_penetration_reported', depth_m=maximum_penetration))
        return dict(physics_step=record['state']['physics_step'], findings=findings,
                    diagnostics=diagnostics, boundary_contacts=contacts,
                    maximum_native_rigid_penetration_m=maximum_penetration, **volumes)


_WORKER_AUDITOR = None


def _prepare_worker(folder):
    global _WORKER_AUDITOR
    _WORKER_AUDITOR = PhysicsAudit(folder)


def _measure_worker(record):
    if psutil.virtual_memory().percent >= 90:
        raise RuntimeError('System memory reached 90%; stopped only this audit')
    return _WORKER_AUDITOR.measure(record)


def _measure_records(stream, folder, digest, auditor, workers):
    """Decode/hash in order, bound pending records, and retain ordered measurements."""
    def records():
        for line in stream:
            if psutil.virtual_memory().percent >= 90:
                raise RuntimeError('System memory reached 90%; stopped only this audit')
            digest.update(line)
            yield decode_record(json.loads(line), folder/'private', digest=digest)

    decoded = records()
    if workers == 1:
        for record in decoded:
            yield record, auditor.measure(record)
        return
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn'),
                             initializer=_prepare_worker, initargs=(str(folder),)) as pool:
        while batch := list(islice(decoded, 2*workers)):
            # Executor.map retains tick order. At most 2*workers records are
            # materialized, so a long capture cannot fill an unbounded queue.
            for record, row in zip(batch, pool.map(_measure_worker, batch), strict=True):
                yield record, row


def audit_capture(folder, output, *, workers=1):
    """Stream every stored tick; malformed/missing evidence fails closed."""
    if type(workers) is not int or workers < 1:
        raise ValueError('workers must be a positive integer')
    folder, output = Path(folder).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256()
    count, last, first, issues, minimum = 0, None, None, 0, None
    unresolved = contact_ticks = volume_ticks = volume_streak = longest_volume_streak = 0
    native_success, complete, error = False, False, None
    try:
        capture = json.loads((folder/'capture.json').read_text())
        if capture.get('complete') is not True:
            raise ValueError('Physics capture is not complete')
        native_success = capture['native_result'].get('success') is True
        auditor = PhysicsAudit(folder)
        dt = float(json.loads((folder/'config.json').read_text())['physics_dt_s'])
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError('Invalid frozen physics time step')
        with (folder/'private/physics_states.jsonl').open('rb') as stream, (output/'findings.jsonl').open('x') as findings:
            for record, row in _measure_records(stream, folder, digest, auditor, workers):
                state = record['state']
                if (state['physics_step'] != count or not isinstance(state['branch_id'], int) or state['branch_id'] < 0
                        or abs(float(state['sim_time_s'])-count*dt) > 1e-8
                        or record['world']['physics_step'] != count):
                    raise ValueError('Missing, repeated or mistimed physics tick')
                if last is not None and (state['parent_state_id'] != last['state_id']
                                         or state['branch_id'] != first['branch_id']
                                         or state['episode_id'] != first['episode_id']):
                    raise ValueError('Broken tick lineage or changed episode')
                first = first or state
                minimum = row['minimum_volume_ratio'] if minimum is None else min(minimum, row['minimum_volume_ratio'])
                if row['findings'] or row['diagnostics']:
                    findings.write(json.dumps(row, allow_nan=False)+'\n')
                    findings.flush()
                issues += int(any(f['severity'] in {'failure', 'penetration'} for f in row['findings']))
                unresolved += int(any(f['severity'] == 'unresolved' for f in row['findings']))
                contact_ticks += int(row['boundary_contacts'] > 0)
                volume_ticks += int(row['nonpositive_cells'] > 0)
                volume_streak = volume_streak+1 if row['nonpositive_cells'] else 0
                longest_volume_streak = max(longest_volume_streak, volume_streak)
                last, count = state, count+1
                if count % 20 == 0:
                    write_json_atomic(output/'progress.json', dict(ticks_checked=count, ticks_with_findings=issues,
                                                                 last_physics_step=state['physics_step']))
                    if psutil.virtual_memory().percent >= 90:
                        raise RuntimeError('System memory reached 90%; stopped only this audit')
        complete = (count == capture['tick_records'] == capture['last_physics_tick']+1
                    and capture['native_result']['physics_steps'] == capture['last_physics_tick'])
        if not complete:
            raise ValueError('Captured tick count does not match native replay result')
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        complete = False
    result = dict(complete=complete, physical_checks_passed=complete and issues == 0 and unresolved == 0,
        qualified=complete and issues == 0 and unresolved == 0 and native_success, native_success=native_success,
        contact_ticks=contact_ticks, unresolved_ticks=unresolved, penetration_or_native_failure_ticks=issues,
        nonpositive_volume_ticks=volume_ticks, maximum_nonpositive_volume_streak_ticks=longest_volume_streak,
        volume_policy='native Session R2 owns duration/failure; per-tick anomalies retained as diagnostics',
        capture=str(folder), workers=workers, ticks_checked=count, ticks_with_findings=issues, minimum_volume_ratio=minimum,
        evidence_sha256=digest.hexdigest(), error=error,
        source_sha256={p.name: sha256_file(p) for p in (Path(__file__), Path(__file__).with_name('collision_audit.py'),
                                                      Path(__file__).with_name('contact_geometry.py'))},
        scope=dict(times='initial state and every committed physics tick; no between-tick CCD claim',
                   fem='nonincident surface contacts refined against their adjacent filled cells; boundary contact allowed',
                   rope_rigid='native convex solids, analytic spheres and closed concave mesh narrow phase',
                   rigid_rigid='native enabled pairs; unsupported narrow phases explicitly unresolved',
                   geometry_resolution_m=RESOLUTION_M,
                   overlap_semantics='contact / interior overlap / unresolved are distinct; outer covers only select work',
                   excludes='incident-face self-folds, complete self-containment without surface contact, other environment objects, disabled rigid pairs, IPC contact forces'))
    write_json_atomic(output/'audit.json', result)
    return result
