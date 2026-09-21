"""Reproducible generator audit; writes validation evidence, never a dataset."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import platform
import subprocess
import sys
import time

from . import variants as v


def audit(output, count=256, *, resume=False):
    output = v.metadata_path(output)
    output.mkdir(parents=True, exist_ok=resume)
    if (output/'report.json').exists():
        raise FileExistsError('Do not overwrite a completed audit')
    base = v.base_config()
    rows, failures, representatives, packages = [], [], [], []
    start = time.monotonic()
    for family in v.FAMILIES:
        for anchor in v.ANCHORS:
            instance = v.generate(0, config=base, family=family, representative=True, anchor=anchor)
            representatives.append(dict(family=family, anchor=anchor, instance_id=instance['instance_id'],
                geometry=instance['validation']['geometry'], ik=instance['validation']['ik']))
            if anchor == 'M':
                folder=output/'representatives'/f'{family}_M'
                if folder.exists() and resume:
                    _,_,saved=v.load_instance(folder)
                    if v.canonical(saved)!=v.canonical(instance):
                        raise ValueError('Representative changed during resume')
                else:
                    v.write_instance(instance, folder)
    with (output/'seeds.jsonl').open('w', buffering=1) as log:
        for seed in range(count):
            try:
                instance = v.generate(seed, config=base)
            except RuntimeError as exc:
                failures.append(dict(seed=seed, error=str(exc), attempts=getattr(exc,'rejections',[])))
                log.write(json.dumps(failures[-1])+'\n')
                continue
            cfg = instance['spec']['resolved_config']['task']
            row = dict(seed=seed, instance_id=instance['instance_id'], accepted_attempt=instance['accepted_attempt'],
                family=cfg['derived_variant']['family_id'], geometry=cfg['geometry'], visual=cfg['visual'],
                parameters=cfg['randomization'], ik=instance['validation']['ik'],
                rejected_attempts=instance['rejected_attempts'])
            rows.append(row)
            log.write(json.dumps(row)+'\n')
            if len(packages) < 3 and row['family'] not in [r['family'] for r in packages]:
                folder = output/'random_examples'/f'seed_{seed}'
                if not (resume and folder.exists()):
                    v.write_instance(instance, folder)
                loaded, spec, restored = v.load_instance(folder)
                if v.canonical(asdict(spec)) != v.canonical(instance['spec']) or v.canonical(restored) != v.canonical(instance):
                    raise ValueError('Saved instance changed during restore')
                v.check_geometry(loaded)
                packages.append(dict(seed=seed, family=row['family'], directory=str(folder.relative_to(output))))
            if seed % 16 == 0:
                print(json.dumps(dict(seed=seed, accepted=len(rows), rejected=len(failures), elapsed_s=time.monotonic()-start)), flush=True)
    # Fresh processes and reversed submission order verify scheduling independence.
    selected = [rows[i] for i in sorted(set([0,len(rows)//2,len(rows)-1]))] if rows else []
    def fresh(row):
        code = ('from topogym.tasks.lock_picking.variants import sample; '
                f'print(sample({row["seed"]},attempt={row["accepted_attempt"]})[0].task.instance_id)')
        return subprocess.check_output([sys.executable,'-c',code],text=True).strip()
    with ThreadPoolExecutor(max_workers=2) as pool:
        repeated = list(pool.map(fresh, reversed(selected)))
    if repeated != [r['instance_id'] for r in reversed(selected)]:
        raise ValueError('Cross-process seed reproduction failed')
    report = dict(schema_version=1, generator_version=v.VERSION, rng_version=v.VARIANT_RNG_VERSION,
        seed_range=[0,count-1], accepted=len(rows), failed=failures,
        family_counts=dict(Counter(r['family'] for r in rows)),
        attempt_counts=dict(Counter(r['accepted_attempt'] for r in rows)),
        unique_geometries=len({v.canonical(r['geometry']) for r in rows}),
        unique_appearances=len({v.canonical(r['visual']) for r in rows}),
        min_pitch_mm=min(r['geometry']['pitch']*1000 for r in rows),
        radius_range_mm=[min(r['geometry']['disc_radius']*1000 for r in rows),max(r['geometry']['disc_radius']*1000 for r in rows)],
        maximum_position_error_m=max(r['ik']['max_position_error_m'] for r in rows),
        maximum_rotation_error_rad=max(r['ik']['max_rotation_error_rad'] for r in rows),
        maximum_adjacent_joint_change_rad=max(r['ik']['maximum_adjacent_arm_joint_change_rad'] for r in rows),
        cross_process_reproduction=dict(passed=True,seeds=[r['seed'] for r in selected],workers=2),
        saved_examples=packages, representative_checks=representatives,
        runtime=dict(python=platform.python_version(),elapsed_s=time.monotonic()-start),
        evidence_sha256={'seeds.jsonl':v.sha(output/'seeds.jsonl'), 'catalog.json':v.sha(v.CATALOG)},
        physics='not_run', robot_scene_collision='not_run', dataset_created=False, h5_created=False)
    v.save(output/'report.json', report)
    print(json.dumps({k:x for k,x in report.items() if k not in ('representative_checks','failed')},ensure_ascii=False), flush=True)
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--count',type=int,default=256)
    p.add_argument('--resume',action='store_true',help='Reuse verified instance packages from an incomplete audit')
    a=p.parse_args()
    if a.count < 3: p.error('--count must be at least 3')
    result=audit(a.output,a.count,resume=a.resume)
    if result['failed']: raise SystemExit('Some seeds exhausted their retries; see report.json')
