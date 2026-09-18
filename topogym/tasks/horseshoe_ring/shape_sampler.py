"""Sample coupled shape neighborhoods with a continuous geometric certificate.

The broad proposal limits are NOT a certified Cartesian box. Only materialized
samples that pass all pairwise perturbation budgets are emitted.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from .shape_neighborhood import ShapeNeighborhood
from .shape_variants import OUTPUT, make_template
from .geometry import horseshoe_band


REFERENCE_PARAMETERS = {
    'waist_mild': [-.5, 1.05, 18.],
    'waist_ellipse': [-.5, 1.15, 18.],
    'u_mild': [.5, 1.05, 18.],
    'deep_waist': [-1., 1.05, 18.],
}


def load_references(root):
    result = {}
    parameter_file=Path(root)/'reference_parameters.json'
    parameters=json.loads(parameter_file.read_text()) if parameter_file.exists() else REFERENCE_PARAMETERS
    for name, params in parameters.items():
        folder = Path(root)/name
        if not (folder/'certificate.json').is_file():
            continue
        cert = json.loads((folder/'certificate.json').read_text())
        if not cert.get('passed'):
            continue
        path = json.loads((folder/'body_poses.json').read_text())
        band,_=horseshoe_band(path['template']['horseshoe'],1.)
        ring=path['template']['target_ring']
        bore_margin=float(np.ptp(band.bounds[:,1])/2+ring['wire_radius']-ring['centerline_radii'][0])
        expected=make_template(*params,bore_margin_mm=bore_margin)
        # Allow only floating roundoff in the fitted radii, never a mislabeled outline.
        actual_radii=path['template']['target_ring']['centerline_radii']
        if not np.allclose(expected['target_ring']['centerline_radii'],actual_radii,atol=1e-11,rtol=0):
            raise ValueError(f'{name}: ellipse parameters differ from the reference')
        expected['target_ring']['centerline_radii']=actual_radii
        if expected != path['template']:
            raise ValueError(f'{name}: reference parameters do not reproduce its template')
        result[name] = (np.asarray(params), bore_margin, ShapeNeighborhood(path, cert))
    if not result:
        raise ValueError('No certified references found; finish reference path certification first')
    return result


def propose(neighborhood, center, rng, margin_m=.00005, bore_margin_mm=.8):
    """Contract a jointly sampled parameter delta until its proof budget fits."""
    delta = rng.uniform(-1., 1., 3)*[.08, .005, .45]
    proposal = np.clip(center+delta, [-1., 1., 16.], [1., 1.35, 20.])
    delta = proposal-center
    for step in range(24):
        factor = 2.**(-step)
        params = center+factor*delta
        template = make_template(*params, bore_margin_mm=bore_margin_mm)
        assessment = neighborhood.assess(template, margin_m)
        if assessment['passed']:
            path, cert = neighborhood.materialize(template, assessment)
            return dict(parameters=dict(shape=float(params[0]), ellipse_aspect=float(params[1]),
                chain_semimajor_mm=float(params[2]), initial_phase_deg=0., bore_margin_mm=bore_margin_mm),
                proposed_parameters=proposal.tolist(), contraction=factor,
                path=path, certificate=cert)
    raise RuntimeError('No certified neighborhood point found; nothing was emitted')


def sample(output, references=OUTPUT/'references', count=12, random_seed=17, margin_m=.00005):
    if count < 1:
        raise ValueError('Count must be positive')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be new or empty; previous evidence is never overwritten')
    families = load_references(references)
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(random_seed)
    names = list(families)
    rows = []
    for i in range(count):
        # Balanced random order makes small batches include visible family changes.
        if i % len(names) == 0:
            rng.shuffle(names)
        family = names[i % len(names)]
        center, bore_margin, neighborhood = families[family]
        result = propose(neighborhood, center, rng, margin_m, bore_margin)
        path, cert = result.pop('path'), result.pop('certificate')
        name = f'{i:03d}_{family}'
        folder = output/name; folder.mkdir()
        (folder/'template.json').write_text(json.dumps(path['template'], indent=2)+'\n')
        (folder/'body_poses.json').write_text(json.dumps(path)+'\n')
        (folder/'certificate.json').write_text(json.dumps(cert, indent=2)+'\n')
        result.update(id=name, family=family, passed=True,
            minimum_clearance_lower_bound_mm=cert['minimum_clearance_lower_bound_m']*1000,
            template_sha256=cert['template_sha256'], frames_sha256=cert['frames_sha256'])
        (folder/'parameters.json').write_text(json.dumps(result, indent=2)+'\n')
        rows.append(result)
        print(f'{name}: certified {result["minimum_clearance_lower_bound_mm"]:.4f} mm; contraction {result["contraction"]:g}',flush=True)
    ranges={}
    for family in families:
        group=[r for r in rows if r['family']==family]
        if group:
            ranges[family]={key:[min(r['parameters'][key] for r in group),max(r['parameters'][key] for r in group)]
                for key in ('shape','ellipse_aspect','chain_semimajor_mm')}
    report=dict(seed=random_seed,count=count,passed=all(r['passed'] for r in rows),samples=rows,
        sampled_ranges_by_family=ranges,requested_margin_mm=margin_m*1000,
        qualification='Certified neighborhoods of solved geometric paths, not a Cartesian parameter box or robot IK guarantee',
        reference_directory=str(Path(references).resolve()),
        sampling='Balanced family order; uniform proposal then joint contraction using all ten body-pair clearance budgets',
        chain_definition='One link per span; semimajor axis in template mm; physical centerline major diameter = 2 * scale * parameter',
        scope='Initial topology, continuous actual convex/capsule clearance and full final separation; no dynamics, lab-obstacle or robot proof')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--references',type=Path,default=OUTPUT/'references')
    parser.add_argument('--count',type=int,default=12)
    parser.add_argument('--seed',type=int,default=17)
    parser.add_argument('--margin-mm',type=float,default=.05)
    args=parser.parse_args()
    sample(args.output,args.references,args.count,args.seed,args.margin_mm*.001)


if __name__=='__main__':
    main()
