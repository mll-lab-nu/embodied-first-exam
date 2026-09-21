"""Inspect recorded meshes and estimate achieved end-cap rotation independently."""
import argparse
import json
from pathlib import Path

import numpy as np


def review(source):
    import pymeshlab

    report = json.loads((source/'report.json').read_text())
    preparation = report.get('preparation') or {}
    with np.load(source/'physical_trace.npz') as archive:
        trace = {name: archive[name] for name in archive.files}
    counts = []
    for positions in trace['positions']:
        meshes = pymeshlab.MeshSet()
        meshes.add_mesh(pymeshlab.Mesh(positions.astype(float), trace['faces']))
        meshes.compute_selection_by_self_intersections_per_face()
        counts.append(meshes.current_mesh().selected_face_number())
    intersections = dict(
        method='MeshLab triangle self-intersection selection',
        scope='All recorded particle-mesh frames; not a continuous collision certificate',
        frames=len(counts), maximum_intersecting_faces=max(counts),
        intersecting_frames=[i for i, count in enumerate(counts) if count], counts=counts)
    (source/'self_intersection_review.json').write_text(json.dumps(intersections, indent=2)+'\n')
    print('Recorded frames:', len(counts), 'maximum intersecting faces:', max(counts))

    before_name = ('prepared_longitudinal_gather.npz'
                   if preparation.get('construction') == 'longitudinal_gather'
                   else 'prepared_longitudinal_2.npz')
    before_path = source/before_name
    after_path = source/('prepared_axial_bunching.npz' if (source/'prepared_axial_bunching.npz').exists()
                        else 'prepared_whole_bundle_twist.npz')
    if before_path.exists() and after_path.exists():
        before, after = np.load(before_path)['positions'], np.load(after_path)['positions']
        parameters = next(stage for stage in report['preparation']['sequence']
                          if stage['name'] == 'whole_bundle_twist')['parameters']
        axis = np.array(parameters['axis'])
        basis = np.eye(3)[np.argmin(np.abs(axis))]
        basis -= axis*np.dot(basis, axis)
        basis /= np.linalg.norm(basis)
        plane = np.column_stack((basis, np.cross(axis, basis)))
        q = before@axis
        q = (q-q.min())/np.ptp(q)
        cap = parameters['end_fraction']
        ends = []
        for label, mask in [('low', q <= cap), ('high', q >= 1-cap)]:
            a, b = before[mask]@plane, after[mask]@plane
            a -= a.mean(axis=0)
            b -= b.mean(axis=0)
            angle = np.arctan2(np.sum(a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0]), np.sum(a*b))
            rotate = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
            ends.append(dict(end=label, particles=int(mask.sum()), rotation_deg=float(np.degrees(angle)),
                             radial_fit_rms_m=float(np.sqrt(np.mean(np.sum((a@rotate.T-b)**2, axis=1))))))
        twist = dict(
            measured_after=after_path.name,
            method='2D rigid rotation fit of corresponding material points in each end cap about the commanded fixed axis',
            limitation='Approximate shape statistic; cap deformation and angle wrapping prevent an exact torsion measurement',
            commanded_relative_twist_deg=parameters['angle_deg'], ends=ends,
            approximate_relative_turn_deg=ends[1]['rotation_deg']-ends[0]['rotation_deg'])
        (source/'twist_review.json').write_text(json.dumps(twist, indent=2)+'\n')
        print('Approximate relative end turn:', twist['approximate_relative_turn_deg'], 'degrees')
    if report.get('success'):
        release = preparation.get('release_seconds', 0.)
        accepted = next(event['seconds'] for event in report['events']
                        if event['phase'] == 'initial_state_accepted')
        assert accepted-release >= 2.4-1e-9
        passive = report.get('initial_stability_evidence') or report['final_evidence']
        if report.get('mode') == 'stability' or report.get('initial_stability_evidence'):
            assert passive.get('passive_seconds', 0) >= 10-1e-9
        print('Post-release acceptance:', accepted-release, 's; passive:', passive.get('passive_seconds', 'separate stability run required'), 's')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    review(parser.parse_args().source.resolve())
