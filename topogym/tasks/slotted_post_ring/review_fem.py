"""Independent recorded-frame FEM deformation and evidence consistency review."""
import argparse
import json
from pathlib import Path

import mujoco
import numpy as np


def review(run):
    run = Path(run)
    spec = json.loads((run/'model/model_spec.json').read_text())
    model = mujoco.MjModel.from_binary_path(str(run/'model/scene.mjb'))
    xml = mujoco.MjModel.from_xml_path(str(run/'model/scene.xml'))
    np.testing.assert_array_equal(model.flex_stiffness, xml.flex_stiffness)
    np.testing.assert_array_equal(model.key_qpos, xml.key_qpos)
    assert model.flex_dim.tolist() == [3]
    assert model.flex_edgeequality.tolist() == [0]
    with np.load(run/'states.npz') as trace, np.load(run/'model/fem_mesh.npz') as mesh:
        qpos = trace['qpos']; qvel = trace['qvel']; times = trace['time_s']
        rest = mesh['rest']; elements = mesh['elements']; volume = mesh['reference_volumes']
        centers = mesh['center_indices']
        indices = model.jnt_qposadr[model.body_jntadr[model.flex_vertbodyid]][:,None]+np.arange(3)
        # These vertex bodies are world children with three world-axis slides.
        assert np.all(model.body_parentid[model.flex_vertbodyid] == 0)
        p = rest[elements]
        inverse = np.linalg.inv(np.stack([p[:,i]-p[:,0] for i in (1,2,3)],axis=2))
        E = spec['settings']['young_pa']; nu = spec['settings']['poisson']
        mu = E/(2*(1+nu)); lame = E*nu/((1+nu)*(1-2*nu))
        result = []
        data = mujoco.MjData(model)
        for frame, positions in enumerate(qpos):
            vertices = rest + positions[indices]
            np.testing.assert_allclose(vertices[centers],trace['cord_nodes'][frame],rtol=0,atol=2e-10)
            if frame in (0,len(qpos)//2,len(qpos)-1):
                data.qpos[:] = positions
                mujoco.mj_kinematics(model,data)
                mujoco.mj_flex(model,data)
                np.testing.assert_allclose(vertices,data.flexvert_xpos,rtol=0,atol=2e-10)
            p = vertices[elements]
            F = np.stack([p[:,i]-p[:,0] for i in (1,2,3)],axis=2) @ inverse
            J = np.linalg.det(F)
            stretches = np.linalg.svd(F,compute_uv=False)
            strain = (F.transpose(0,2,1)@F - np.eye(3))/2
            density = mu*np.sum(strain**2,axis=(1,2)) + lame/2*np.trace(strain,axis1=1,axis2=2)**2
            result.append([times[frame],J.min(),J.max(),stretches.min(),stretches.max(),
                           np.dot(volume,density)])
        samples = np.asarray(result)
        interval = np.diff(times)
        report = dict(scope='independent recorded-frame review; not an every-step or CCD audit',
            sample_count=len(samples),physics_seconds=float(times[-1]),
            finite_state=bool(np.isfinite(qpos).all() and np.isfinite(qvel).all()),
            strictly_increasing_timestamps=bool(np.all(interval>0)),
            uniform_20hz_including_terminal_frame=bool(np.allclose(interval,.05,rtol=0,atol=1e-8)),
            nodal_positions_match_engine_and_recorded_centerline=True,
            xml_binary_material_and_keyframe_match=True,
            sampled_min_volume_ratio=float(samples[:,1].min()),
            sampled_max_volume_ratio=float(samples[:,2].max()),
            sampled_min_principal_stretch=float(samples[:,3].min()),
            sampled_max_principal_stretch=float(samples[:,4].max()),
            sampled_max_elastic_energy_j=float(samples[:,5].max()),
            material_calibrated=False,large_strain_material_response_validated=False,
            limitations=['Principal stretches are diagnostic; the isotropic StVK law is uncalibrated',
                         'Every-step acceptance remains in report.json; frame sampling can miss extrema'])
    np.savez_compressed(run/'sampled_fem_review.npz',samples=samples,
                        columns=['time_s','min_J','max_J','min_stretch','max_stretch','elastic_energy_J'])
    (run/'sampled_fem_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    review(p.parse_args().run)
