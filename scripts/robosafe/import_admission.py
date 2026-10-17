#!/usr/bin/env python3
"""Import exact-candidate native admission evidence, without inferring missing seeds or cameras."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_identity as CI
REQUIRED_GATES = frozenset(('reference', 'nop', 'nop_unattempted', 'comply_harms', 'negatives', 'trivial',
    'replay', 'contact_bump', 'contact_reference', 'static_reference', 'static_strike', 'body_reference',
    'damage_reference', 'blind', 'unseen_without_look', 'attempt', 'reference_end'))


def same_commit(full, short):
    return isinstance(short, str) and len(short) >= 7 and full.startswith(short)


def member_name(row):
    return row['member'] + ('/' + row['evidence'] if row.get('evidence') else '')


def installed_image_matches(native, image_id, commit):
    return (native.get('image_id', '').removeprefix('sha256:') == image_id.removeprefix('sha256:')
        and native.get('source_commit') == commit and native.get('image_revision_label') == commit
        and native.get('installed_package_only') is True
        and '/site-packages/robosafebench/' in native.get('package_path', '')
        and native.get('process_environment', {}).get('PYTHONPATH') == ''
        and native.get('provenance_matches') is not False)


def complete_reference_scope(native, row):
    expected = native.get('expected_member_tiers')
    if not isinstance(expected, list) or not expected or not all(isinstance(t, dict) and isinstance(t.get('member'), str) for t in expected):
        return False
    expected_ids = [(t['member'], t.get('evidence')) for t in expected]
    references = [case for case in native.get('cases', []) if case.get('strategy') == 'reference']
    observed = [(c.get('key', {}).get('member'), c.get('key', {}).get('evidence')) for c in references]
    if len(set(expected_ids)) != len(expected_ids) or len(set(observed)) != len(observed) or set(observed) != set(expected_ids):
        return False
    defaults = {'interface': 'skill', 'clock': 'paused', 'movers': 'scripted'}
    return all(all(case.get('key', {}).get(k, defaults.get(k)) == row.get(k, defaults.get(k))
                   for k in ('family', 'robot', 'seed', 'interface', 'clock', 'movers', 'cameras')) for case in references)


def accepted_rows(rows, commit, evidence_root, image_id=None, variant=None, clock='paused', candidate=None):
    """Check the raw native gates and exact reference case, not only the summary's booleans."""
    cache, accepted = {}, []
    for row in rows:
        if (row.get('variant') or None) != variant:
            continue
        if not (same_commit(commit, row.get('source_commit')) and row.get('interface') == 'control'
                and row.get('clock', 'paused') == clock and row.get('all_required_gates') is True
                and row.get('reference_pass') is True
                and (row.get('allowed_in_frozen_tree') is True or row.get('provenance_matches') is True)):
            continue
        path = Path(row['native_record'])
        if not path.is_absolute():
            path = evidence_root / path
        if path not in cache:
            data = path.read_bytes()
            cache[path] = (json.loads(data), hashlib.sha256(data).hexdigest())
        native, sha = cache[path]
        if (native.get('visual_assets') or {}).get('asset_profile') == 'realism_v3' and candidate is None:
            continue
        if candidate is not None and (not CI.native_matches(native, candidate)
                or candidate['source_commit'] != commit
                or candidate['image_id'] != (image_id or '').removeprefix('sha256:')):
            continue
        if row.get('allowed_in_frozen_tree') is not True:
            # The combined-image schema does not claim frozen-tree eligibility. Independently
            # reconstruct its complete executed scope instead of inventing that summary field.
            if (not image_id or not installed_image_matches(native, image_id, commit)
                    or native.get('source_commit') != commit or native.get('status') != 'complete'
                    or row.get('image_id', '').removeprefix('sha256:') != image_id.removeprefix('sha256:')
                    or not complete_reference_scope(native, row)):
                continue
        if (native.get('variant') or None) != variant:
            continue
        if variant:
            scope = native.get('variant_scope')
            if (not image_id or not isinstance(scope, dict) or scope.get('schema') != 1
                    or row['member'] not in scope.get('variant_members', ())
                    or native.get('source_commit') != commit or native.get('status') != 'complete'
                    or row.get('image_id', '').removeprefix('sha256:') != image_id.removeprefix('sha256:')):
                continue
            if any(case.get('admission_variant') != variant or
                   case.get('admission_control') is not (case.get('key', {}).get('member') in scope.get('control_members', ())) or
                   (case.get('key', {}).get('variant') or None) != (None if case.get('admission_control') else variant)
                   for case in native.get('cases', [])):
                continue
            expected = native.get('expected_member_tiers')
            variant_members = native.get('expected_variant_members')
            if not isinstance(expected, list) or not expected or not isinstance(variant_members, list):
                continue
            if not all(isinstance(tier, dict) and isinstance(tier.get('member'), str) for tier in expected):
                continue
            expected_ids = [(tier['member'], tier.get('evidence')) for tier in expected]
            expected_members = {tier['member'] for tier in expected}
            if (set(variant_members) != set(scope.get('variant_members', ()))
                    or set(scope.get('control_members', ())) != expected_members - set(variant_members)
                    or len(set(expected_ids)) != len(expected_ids)):
                continue
            if not complete_reference_scope(native, row):
                continue
        elif any(case.get('admission_variant') or case.get('key', {}).get('variant') for case in native.get('cases', [])):
            continue
        if image_id and (not installed_image_matches(native, image_id, commit)
                         or native.get('status') != 'complete' or not complete_reference_scope(native, row)):
            continue
        if not (same_commit(commit, native.get('source_commit')) and native.get('admitted') is True
                and all(native.get(gate) is True for gate in REQUIRED_GATES)):
            continue
        matches = [case for case in native.get('cases', []) if case.get('strategy') == 'reference'
            and case.get('pass') is True and case.get('key', {}).get('clock', 'paused') == clock
            and all(case.get('key', {}).get(k) == row.get(k)
                for k in ('family', 'robot', 'member', 'seed', 'evidence', 'cameras', 'interface', 'variant'))]
        if matches:
            accepted.append({**row, 'native_sha256': sha})
    return accepted


def build_families(index, rows, robot, selected, variant=None, clock='paused'):
    updates = {}
    for family in index.values():
        fid = family['rsb']
        if fid not in selected:
            continue
        variants = defaultdict(set)
        for key in family['instances'].values():
            if key.get('robot', family['robot']) == robot and (key.get('variant') or None) == variant:
                variants[member_name(key)].add(key.get('cameras'))
        if not variants:
            continue
        evidence = [r for r in rows if r['family'] == fid and r['robot'] == robot and (r.get('variant') or None) == variant
                    and r.get('clock', 'paused') == clock]
        allowed, holds = {}, {}
        for member, cameras in sorted(variants.items()):
            per_camera = [{r['seed'] for r in evidence if member_name(r) == member and r.get('cameras') == camera}
                          for camera in cameras]
            seeds = sorted(set.intersection(*per_camera))
            if seeds:
                allowed[member] = seeds
            else:
                holds[member] = 'exact-candidate full admission missing or failed for an offered camera condition'
        updates[fid] = {'ok': bool(allowed), 'fail': [] if allowed else ['exact-candidate full admission pending or failed'],
            'serve': sorted(allowed), 'allowed_seeds': allowed, 'holds': holds,
            'admitted_keys': [CI.key_identity(r) for r in evidence],
            'evidence_status': 'native full required gates and matching passing reference; every offered camera required',
            'evidence': [{'member': member_name(r), 'seed': r['seed'], 'cameras': r.get('cameras'),
                'source': r['native_record'], 'sha256': r['native_sha256']} for r in evidence]}
        if variant:
            updates[fid]['variant'] = variant
    return updates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--members', type=Path, required=True)
    parser.add_argument('--commit', required=True, help='full immutable simulator candidate commit')
    parser.add_argument('--image-id', required=True, help='require raw gates from this exact installed candidate image')
    parser.add_argument('--variant', help='import only this exact request variant into its independent admission entry')
    parser.add_argument('--clock', choices=('paused', 'realtime'), default='paused', help='independent clock admission; realtime never borrows paused evidence')
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--families', required=True, help='comma-separated family ids; other admissions stay unchanged')
    parser.add_argument('--out', type=Path, required=True, help='reviewable admission files; use the benchmark directory to apply')
    parser.add_argument('--candidate', type=Path, help='strict immutable source/image/digest/visual identity receipt for a new freeze')
    args = parser.parse_args()
    if len(args.commit) != 40 or any(c not in '0123456789abcdef' for c in args.commit):
        raise SystemExit('--commit must be a full 40-character commit')
    index = json.loads((HERE / 'families.json').read_text())['families']
    selected = set(args.families.split(','))
    unknown = selected - {family['rsb'] for family in index.values()}
    if unknown:
        raise SystemExit(f'Unknown families: {sorted(unknown)}')
    image = args.image_id.removeprefix('sha256:')
    if len(image) != 64 or any(c not in '0123456789abcdef' for c in image):
        raise SystemExit('--image-id must be a full 64-character image id')
    candidate = CI.load(args.candidate) if args.candidate else None
    registry_candidate = json.loads((HERE / 'families.json').read_text()).get('candidate_identity')
    if registry_candidate is not None and candidate != registry_candidate:
        raise SystemExit('--candidate must match the new frozen registry identity')
    rows = accepted_rows(json.loads(args.members.read_text()), args.commit, args.evidence_root, args.image_id, args.variant, args.clock, candidate)
    args.out.mkdir(parents=True, exist_ok=True)
    for source in sorted(HERE.glob('admission_*.json')):
        original = json.loads(source.read_text())
        updates = build_families(index, rows, original['robot'], selected, args.variant, args.clock)
        if not updates:
            continue
        provenance = {'commit': args.commit, 'members': str(args.members),
            'image_id': args.image_id,
            'members_sha256': hashlib.sha256(args.members.read_bytes()).hexdigest(),
            'required_gates': sorted(REQUIRED_GATES), 'families': sorted(updates)}
        for fid, update in updates.items():
            update.update(candidate_source_commit=args.commit, candidate_image_id=args.image_id, clock=args.clock)
            if candidate is not None:
                update['candidate_identity'] = candidate
            family = original['families'].setdefault(fid, {})
            parent = family.setdefault('variants', {}) if args.variant else original['families']
            key = args.variant or fid
            previous = parent.get(key, {})
            if args.clock == 'realtime':
                previous.setdefault('clocks', {})['realtime'] = update
                parent[key] = previous
            else:
                # Refresh one clock without erasing the independently checked other dimensions.
                for name in ('variants', 'clocks'):
                    if previous.get(name):
                        update[name] = previous[name]
                parent[key] = update
        original.setdefault('candidate_admission_imports', {})[(args.variant or 'default') + '/' + args.clock] = provenance
        target = args.out / source.name
        tmp = target.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(original, indent=1) + '\n')
        tmp.replace(target)
        print(f'{source.name}: {len(updates)} exact-candidate family updates')


if __name__ == '__main__':
    main()
