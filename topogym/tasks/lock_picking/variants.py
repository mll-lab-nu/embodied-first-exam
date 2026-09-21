"""Versioned seed -> fixed mechanism + bounded perturbations -> geometry/IK instance.

No physics steps, H5 writer or video dependency. The shared named RNG and
EpisodeSpec are reused; physical execution remains a separate qualification.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import os

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf

from topogym.generation.episode_spec import EpisodeKey, EpisodeSpec, TaskLayout, TaskVariant, ScenePreset, ExecutionProfile
from topogym.generation.variant_episode import build_variant_episode
from topogym.generation.variant_rng import VARIANT_RNG_VERSION, VariantRng
from ._staged_lock_geometry import LockGeometry, variant_geometry
from .certificate import certificate

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT/'assets/tasks/lock_picking/seed_families_v1/catalog.json'
VERSION = 'lock_picking_seed_v1'
FAMILIES = ('F1', 'F2', 'F3')
ANCHORS = {'S': (65., 150.), 'M': (80., 150.), 'L': (95., 180.)}
PALETTES = {
    'purple_blue': [[.46,.28,.66], [.20,.43,.60], [.72,.34,.22]],
    'teal_plum': [[.15,.49,.46], [.53,.27,.47], [.27,.37,.58]],
    'slate_rust': [[.31,.39,.49], [.68,.31,.24], [.32,.46,.33]],
}
RANGES = {'radius_fraction': (0.,1.), 'pitch_fraction': (0.,1.),
          'dx_m': (-.005,.005), 'dy_m': (-.005,.005), 'dz_m': (-.002,.002),
          'roughness': (.35,.6), 'metallic': (.2,.55)}
SHAPE_PATHS = {'radius_fraction','pitch_fraction','dx_m','dy_m','dz_m'}


def plain(value):
    return OmegaConf.to_container(value, resolve=True) if OmegaConf.is_config(value) else value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def catalog():
    return json.loads(CATALOG.read_text())


def prototype(family):
    if family not in FAMILIES:
        raise ValueError(f'Unknown family: {family}')
    return deepcopy(next(x for x in catalog()['families'] if x['family_id']==family))


def derive(task):
    """Pure task hook: load a fixed mechanism, then derive coupled dimensions."""
    p, flags = task['randomization'], task['generator']
    row = deepcopy(plain(task['generator_prototype'])) if task.get('generator_prototype') is not None else prototype(str(p['family_id']))
    if row['family_id'] != str(p['family_id']):
        raise ValueError('Prototype identity differs from selected family')
    task['generator_prototype'] = row
    if task.get('generator_ik_reference') is None:
        task['generator_ik_reference'] = catalog()['ik_reference']
    previous = task.get('derived_variant', {})
    pool_digest = previous.get('pool_sha256') or sha(CATALOG)
    g = deepcopy(row['geometry'])
    if flags['shape']:
        radius = 65.+30.*float(p['radius_fraction'])
        lower = max(150., 150.*radius/80.)
        pitch = lower+(180.-lower)*float(p['pitch_fraction'])
    else:
        if flags['anchor'] not in ANCHORS:
            raise ValueError('Unknown size anchor')
        radius, pitch = ANCHORS[flags['anchor']]
    g.update(disc_radius=radius/1000., pitch=pitch/1000., grip_offset=(3*pitch+45)/1000.)
    for field, offset in [('first_x','dx_m'), ('center_y','dy_m'), ('axis_z','dz_m')]:
        g[field] += float(p[offset]) if flags['position'] else 0.
    palette = str(p['palette_id']) if flags['appearance'] else 'purple_blue'
    if palette not in PALETTES:
        raise ValueError('Unknown palette')
    task['geometry'] = g
    task['rotor_stops'] = row['rotor_stops']
    task['variant'] = 'aligned_entry'  # Preserve the resolved family geometry.
    task['visual']['disc_colors'] = PALETTES[palette]
    task['visual']['plate_finish'] = dict(
        roughness=float(p['roughness']) if flags['appearance'] else .45,
        metallic=float(p['metallic']) if flags['appearance'] else .35)
    task['derived_variant'] = dict(family_id=row['family_id'],
        prototype_id=row['family_id']+'_fixed_angles_v1', required_retreats=row['necessary_retreats'],
        reset_angles_deg=row['reset_angles_deg'], generator_version=VERSION,
        pool_sha256=pool_digest, prototype_sha256=fingerprint(row),
        radius_mm=radius, pitch_mm=pitch, palette_id=palette,
        parameter_space='geometry_ik_candidates', physics='not_run')


def validate_parameters(task):
    p = task['randomization']
    for name, (lo,hi) in RANGES.items():
        v = float(p[name])
        if not np.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f'{name} outside generator domain')
    if str(p['palette_id']) not in PALETTES:
        raise ValueError('Unknown palette')
    expected = OmegaConf.create(plain(task))
    derive(expected)
    for key in ('geometry','rotor_stops','variant','visual','derived_variant'):
        if canonical(plain(expected[key])) != canonical(plain(task[key])):
            raise ValueError(f'Resolved {key} does not match the fixed prototype and parameters')
    g = LockGeometry.from_config(task['geometry'])
    if not 65.-1e-8 <= g.disc_radius*1000 <= 95.+1e-8:
        raise ValueError('Disc radius outside 65..95 mm')
    if not max(.150, 1.875*g.disc_radius)-1e-10 <= g.pitch <= .180+1e-10:
        raise ValueError('Pitch violates visibility or maximum size constraint')


def base_config():
    with initialize_config_dir(config_dir=str(ROOT/'configs'), version_base='1.3'):
        return compose(config_name='lock_picking_variants')


def sample(seed, *, family=None, representative=False, anchor='M', shape=True,
           position=True, appearance=True, attempt=0, config=None):
    """Seeded resolved config + complete EpisodeSpec; no IK or output files yet."""
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise ValueError('attempt must be a nonnegative integer')
    if family is not None and family not in FAMILIES:
        raise ValueError('Unknown family')
    if anchor not in ANCHORS:
        raise ValueError('Unknown anchor')
    cfg = OmegaConf.create(plain(base_config() if config is None else config))
    OmegaConf.set_struct(cfg, False)
    for field in ('generator_prototype','generator_ik_reference','derived_variant','instance_id'):
        cfg.task.pop(field,None)
    cfg.task.generator = dict(shape=bool(shape and not representative),
        position=bool(position and not representative), appearance=bool(appearance and not representative), anchor=anchor)
    directives = plain(cfg.task.variation)
    for d in directives:
        path = d.get('path','')
        if family is not None and path=='randomization.family_id':
            d['values']=[family]
        # Retrying only structural/layout axes preserves family and appearance.
        # Keep public seed identity and the shared RNG's named retry semantics.
        leaf=path.split('.')[-1]
        if attempt and d['kind']=='uniform' and leaf in SHAPE_PATHS:
            value=float(VariantRng(seed).stream('lock_picking/'+path, retry=attempt).uniform(d['lo'],d['hi']))
            d.clear();d.update(kind='choice',path=path,values=[value])
    cfg.task.variation=directives
    cfg,spec=build_variant_episode(cfg,'lock_picking',int(seed),variant_id=VERSION)
    cfg.task.seed=int(seed)
    # Match textured colors in both rasterizer assets and Nyx material rules.
    for rule in cfg.env.appearance:
        name=str(rule.pattern)
        if name in ('lock_disc_1','lock_disc_2','lock_disc_3'):
            rule.color=cfg.task.visual.disc_colors[int(name[-1])-1]
            rule.metallic=cfg.task.visual.plate_finish.metallic
            rule.roughness=cfg.task.visual.plate_finish.roughness
    # Diagnostic face cameras track the actual aperture positions.
    g=LockGeometry.from_config(cfg.task.geometry)
    for i,name in enumerate(('disc1_face','disc2_face','disc3_face','endpoint_face')):
        if name in cfg.env.cameras:
            cfg.env.cameras[name].pos=[g.disc_x(i)-.07,g.center_y,g.axis_z]
            cfg.env.cameras[name].lookat=[g.disc_x(i),g.center_y,g.axis_z]
    identity=dict(version=VERSION,rng_version=VARIANT_RNG_VERSION,seed=int(seed),attempt=attempt,
        pool_sha256=sha(CATALOG),task=plain(cfg.task),env=plain(cfg.env),robot_control=plain(cfg.robot_control))
    identity['task'].pop('variation',None)
    instance_id=fingerprint(identity)
    cfg.task.instance_id=instance_id
    key=replace(spec.key,variant_id=VERSION+'_'+instance_id[:20])
    spec=replace(spec,key=key,variant=replace(spec.variant,key=key,
        parameters=dict(spec.variant.parameters,instance_sha256=instance_id,
            generator_version=VERSION,rng_version=VARIANT_RNG_VERSION,attempt=attempt)),
        layout=TaskLayout(task_id='lock_picking',layout_id=instance_id,
            objects=dict(geometry=plain(cfg.task.geometry),rotor_stops=plain(cfg.task.rotor_stops)),
            metadata=plain(cfg.task.derived_variant)),
        execution_profile=ExecutionProfile(profile_id='aligned_geometry_ik_candidate',
            parameters=dict(physics_qualified=False,full_pickup_release=False)),
        resolved_config=plain(cfg))
    return cfg,spec


def check_geometry(cfg):
    from .inverse_variants import analytic_route_check
    validate_parameters(cfg.task)
    g=LockGeometry.from_config(cfg.task.geometry)
    if variant_geometry(g,str(cfg.task.variant),int(cfg.task.seed)) != g:
        raise ValueError('Scene mode changes generated geometry')
    row=plain(cfg.task.generator_prototype)
    proof=json.loads(canonical(certificate(g,cfg.task.rotor_stops)))
    if proof['minimum_required_decoupling_retreats'] != row['necessary_retreats'] or not proof['unique_shortest_branch_sequence']:
        raise ValueError('Fixed family identity changed')
    check=analytic_route_check(g,cfg.task.rotor_stops,row['keyframes'])
    radial_gap=.083*g.disc_radius/.08-g.slot_radius
    if radial_gap <= 0:
        raise ValueError('Support frame intersects aperture region')
    return dict(status='passed',certificate=proof,coaxial_route=check,
        frame_aperture_radial_gap_m=radial_gap,tab_count=3,
        retreat_distance_m=g.pitch,route_sha256=fingerprint(row['keyframes'])),row['keyframes']


def check_ik(cfg, keyframes):
    from .inverse_variants import ArmIK
    arm=ArmIK(cfg,[plain(cfg.task.generator_ik_reference)])
    frames,report=arm.route(LockGeometry.from_config(cfg.task.geometry),keyframes)
    # Reject discontinuous IK branches, even when each isolated target is reachable.
    if report['maximum_adjacent_arm_joint_change_rad'] > .15:
        raise ValueError('IK branch discontinuity')
    return dict(status='passed',**report),frames


def generate(seed, *, max_attempts=8, **options):
    """Validated candidate or explicit rejection; no physically qualified claim."""
    if isinstance(max_attempts,bool) or not isinstance(max_attempts,int) or not 1 <= max_attempts <= 100:
        raise ValueError('max_attempts must be in 1..100')
    rejected=[]
    for attempt in range(max_attempts):
        cfg,spec=sample(seed,attempt=attempt,**options)
        try:
            geometry,keyframes=check_geometry(cfg)
            ik,frames=check_ik(cfg,keyframes)
        except (ValueError, RuntimeError, AssertionError) as exc:
            rejected.append(dict(attempt=attempt,parameters=plain(cfg.task.randomization),reason=str(exc)))
            continue
        return dict(schema_version=1,instance_id=cfg.task.instance_id,spec=asdict(spec),
            validation=dict(geometry=geometry,ik=ik,robot_scene_collision=dict(status='not_run'),
                physics=dict(status='not_run'),visibility=dict(status='not_run')),
            keyframes=keyframes,ik_frames=frames,rejected_attempts=rejected,
            accepted_attempt=attempt,classification='geometry_and_ik_candidate',dataset_created=False)
    error=RuntimeError(f'No accepted lock variant for seed {seed} in {max_attempts} attempts')
    error.rejections=rejected
    raise error


def write_instance(instance, output, *, assets=True):
    """Portable scene/route package; file hash manifest excludes itself."""
    output=metadata_path(output)
    output.mkdir(parents=True,exist_ok=False)
    save(output/'instance.json',instance)
    cfg=OmegaConf.create(instance['spec']['resolved_config'])
    OmegaConf.save(cfg,output/'scene_config.yaml',resolve=True)
    save(output/'prototype.json',plain(cfg.task.generator_prototype))
    save(output/'implementation.json',dict(generator_version=VERSION,
        rng_version=VARIANT_RNG_VERSION,source_sha256={
            str(p.relative_to(ROOT)):sha(p) for p in (
                Path(__file__),Path(__file__).with_name('inverse_variants.py'),
                Path(__file__).with_name('_staged_lock_geometry.py'),
                Path(__file__).with_name('certificate.py'),
                ROOT/'topogym/generation/variant_rng.py')}))
    if assets:
        from .inverse_variants import export_assets
        export_assets(LockGeometry.from_config(cfg.task.geometry),cfg.task.rotor_stops,cfg,output/'assets')
        for p in (output/'assets').rglob('*.urdf'):
            tree=ET.parse(p)
            for mesh in tree.findall('.//mesh'):
                f=Path(mesh.get('filename'))
                if f.is_absolute():mesh.set('filename',os.path.relpath(f,p.parent))
            tree.write(p,encoding='unicode')
        for p in (output/'assets').rglob('aperture_outline.json'):
            data=json.loads(p.read_text())
            for key in ('source_visual','outlined_visual'):
                data[key]=os.path.relpath(data[key],p.parent)
            save(p,data)
    manifest=dict(schema_version=1,instance_id=instance['instance_id'],
        files={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    save(output/'manifest.json',manifest)
    return output


def load_instance(path):
    path=Path(path)
    manifest=json.loads((path/'manifest.json').read_text())
    if not {'instance.json','scene_config.yaml','prototype.json','implementation.json'} <= set(manifest['files']):
        raise ValueError('Incomplete instance manifest')
    for relative,digest in manifest['files'].items():
        f=(path/relative).resolve()
        if not f.is_relative_to(path.resolve()) or sha(f)!=digest:
            raise ValueError('Instance package checksum mismatch: '+relative)
    instance=json.loads((path/'instance.json').read_text())
    if instance['instance_id']!=manifest['instance_id']:
        raise ValueError('Instance identity mismatch')
    spec=instance['spec']
    key=EpisodeKey(**spec['key'])
    restored=EpisodeSpec(key=key,preset=ScenePreset(**spec['preset']),
        variant=TaskVariant(**{**spec['variant'],'key':key}),layout=TaskLayout(**spec['layout']),
        execution_profile=ExecutionProfile(**spec['execution_profile']),resolved_config=spec['resolved_config'])
    cfg=OmegaConf.create(restored.resolved_config)
    # No resampling or dependence on mutable prototype files during restore.
    LockGeometry.from_config(cfg.task.geometry)
    if cfg.task.variant!='aligned_entry' or cfg.task.instance_id!=instance['instance_id']:
        raise ValueError('Restored scene mode or identity mismatch')
    validate_parameters(cfg.task)
    return cfg,restored,instance


def metadata_path(path):
    path=Path(path).resolve()
    if ROOT/'demos' in path.parents or path==ROOT/'demos':
        raise ValueError('Instance metadata/assets must not be written into demos/')
    return path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',type=int,required=True)
    p.add_argument('--family',choices=FAMILIES)
    p.add_argument('--representative',action='store_true')
    p.add_argument('--anchor',choices=tuple(ANCHORS),default='M')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-attempts',type=int,default=8)
    p.add_argument('--no-assets',action='store_true')
    a=p.parse_args()
    a.output=metadata_path(a.output)
    try:
        result=generate(a.seed,family=a.family,representative=a.representative,anchor=a.anchor,max_attempts=a.max_attempts)
    except RuntimeError as exc:
        a.output.mkdir(parents=True,exist_ok=False)
        save(a.output/'rejection.json',dict(seed=a.seed,status='rejected',reasons=getattr(exc,'rejections',[])))
        raise
    write_instance(result,a.output,assets=not a.no_assets)
    print(result['instance_id'],result['spec']['layout']['metadata']['family_id'],flush=True)


if __name__=='__main__':
    main()
