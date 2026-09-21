"""Volumetric FEM cord for the existing MuJoCo puzzle.

The material is Saint Venant--Kirchhoff, not a chain of edge constraints.
The straight reference mesh is compiled first; a keyframe supplies the bent
assembly at initialization. No reference matrices or positions change at run
time. Material constants are authored candidates, not measured rope data.
"""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from .geometry import SlottedPostLayout, centerline
from .physics import PhysicsSettings, build_model as build_legacy_model, values


@dataclass(frozen=True)
class FEMSettings:
    integrator: str = 'Euler'
    dt: float = .0001
    segment_m: float = .006
    radial_segments: int = 8
    young_pa: float = 1.e5
    poisson: float = .3
    density_kg_m3: float = 700.
    rayleigh_s: float = .00001
    mass_damping_rate_s_inv: float = 2.
    friction: float = .35
    contact_time_s: float = .0003
    solver_tolerance: float = 1e-10
    solver_iterations: int = 100

    def validate(self):
        if self.integrator not in ('Euler', 'discrete'):
            raise ValueError('Use Euler or discrete for the audited volumetric model')
        for name in ('dt', 'segment_m', 'young_pa', 'density_kg_m3', 'contact_time_s', 'solver_tolerance'):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if not isinstance(self.radial_segments, int) or self.radial_segments < 6:
            raise ValueError('At least six vertices per circumference required')
        if not isinstance(self.solver_iterations, int) or self.solver_iterations < 1:
            raise ValueError('Positive solver iteration budget required')
        if not 0 <= self.poisson < .5:
            raise ValueError('Poisson ratio must lie in [0, .5)')
        if not np.isfinite(self.rayleigh_s) or self.rayleigh_s < 0:
            raise ValueError('Nonnegative finite Rayleigh damping required')
        if not np.isfinite(self.mass_damping_rate_s_inv) or self.mass_damping_rate_s_inv < 0:
            raise ValueError('Nonnegative finite mass-proportional damping required')
        if not np.isfinite(self.friction) or self.friction < 0:
            raise ValueError('Nonnegative finite friction required')
        return self


def signed_volumes(vertices, elements):
    p = vertices[elements]
    return np.einsum('ij,ij->i', p[:, 1]-p[:, 0],
                     np.cross(p[:, 2]-p[:, 0], p[:, 3]-p[:, 0]))/6


def native_moduli(young, poisson):
    """Map physical Lamé constants to MuJoCo's full-flex convention.

    The 3D edge metric in 3.13 uses mu*tr(E²)+lambda*tr(E)²,
    rather than mu*tr(E²)+lambda/2*tr(E)². Keep mu and halve
    the input lambda; the assembled force is then standard StVK.
    Both XML input and physical parameters are archived. A force-based
    constitutive check below rejects engines with different semantics.
    Reference: MuJoCo src/user/user_mesh.cc, MetricTensor/ComputeStiffness.
    """
    native_nu=poisson/(2*(1-poisson))
    return young*(1+native_nu)/(1+poisson), native_nu


def check_constitutive_response(model, mesh, settings):
    """Check homogeneous axial/shear stresses, without gravity or contacts."""
    rest=mesh['rest'];d=mujoco.MjData(model)
    indices=np.array([[model.joint(f'fem_{i}_{a}').dofadr[0] for a in range(3)]
                      for i in range(len(rest))])
    qindices=np.array([[model.joint(f'fem_{i}_{a}').qposadr[0] for a in range(3)]
                       for i in range(len(rest))])
    left=np.isclose(rest[:,0],rest[:,0].min(),rtol=0,atol=1e-10)
    area=mesh['reference_volumes'].sum()/np.ptp(rest[:,0])
    E=settings.young_pa;nu=settings.poisson
    lame=E*nu/((1+nu)*(1-2*nu));mu=E/(2*(1+nu))
    gravity=model.opt.gravity.copy();flags=model.opt.disableflags
    result={}
    try:
        model.opt.gravity[:]=0
        model.opt.disableflags|=int(mujoco.mjtDisableBit.mjDSBL_CONTACT)|int(mujoco.mjtDisableBit.mjDSBL_EQUALITY)
        for name,F in [('axial',np.diag([1.01,1.,1.])),
                       ('shear',np.array([[1.,0,0],[.01,1.,0],[0,0,1.]]))]:
            mujoco.mj_resetData(model,d)
            d.qpos[qindices]=(rest@F.T-rest)
            mujoco.mj_forward(model,d)
            strain=(F.T@F-np.eye(3))/2
            stress=F@(lame*np.trace(strain)*np.eye(3)+2*mu*strain)
            expected=area*stress[:,0]
            measured=d.qfrc_passive[indices][left].sum(axis=0)
            error=float(np.linalg.norm(measured-expected)/np.linalg.norm(expected))
            result[name]=dict(expected_force_n=expected.tolist(),measured_force_n=measured.tolist(),
                              relative_error=error,passed=error<1e-6)
    finally:
        model.opt.gravity[:]=gravity;model.opt.disableflags=flags
    if not all(r['passed'] for r in result.values()):
        raise RuntimeError(f'MuJoCo FEM material convention failed analytical check: {result}')
    return result


def tube_tetrahedra(points, radius, sides=8):
    """Conforming three-tet triangular prisms; center nodes remain observable."""
    from topogym.world.rope import parallel_transport_frames

    points = np.asarray(points, dtype=float)
    _, normals, binormals = parallel_transport_frames(points)
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    theta = np.arange(sides)*2*np.pi/sides
    cross = np.vstack([np.zeros(2), radius*np.column_stack([np.cos(theta), np.sin(theta)])])
    count = sides+1
    rest = np.concatenate([np.column_stack([np.full(count, s), cross]) for s in arc])
    spawn = np.concatenate([p+cross[:, :1]*n+cross[:, 1:]*b
                            for p, n, b in zip(points, normals, binormals)])
    elements = []
    for i in range(len(points)-1):
        for j in range(sides):
            a, b, c = sorted([i*count, i*count+j+1, i*count+(j+1)%sides+1])
            aa, bb, cc = np.array([a, b, c])+count
            elements.extend([[a, b, c, cc], [a, b, bb, cc], [a, aa, bb, cc]])
    elements = np.asarray(elements, dtype=np.int32)
    negative = signed_volumes(rest, elements) < 0
    elements[negative, 1], elements[negative, 2] = elements[negative, 2].copy(), elements[negative, 1].copy()
    vol = signed_volumes(rest, elements)
    ratio = signed_volumes(spawn, elements)/vol
    if np.min(vol) <= 0 or np.min(ratio) <= .2:
        raise ValueError(f'Invalid reference/spawn tetrahedra; minimum J={ratio.min()}')
    masses = np.zeros(len(rest))
    np.add.at(masses, elements.ravel(), np.repeat(vol/4, 4))
    return dict(rest=rest, spawn=spawn, elements=elements, nodal_volumes=masses,
                center_indices=np.arange(len(points))*count, reference_volumes=vol,
                initial_volume_ratios=ratio)


def build_model(output, settings=FEMSettings(), layout=SlottedPostLayout(), robot=False):
    settings.validate()
    output = Path(output).resolve()
    # Reuse the audited bored rigid geometry and terminal sites, then remove
    # the entire old cord and its length equality before compiling the FEM.
    _, _, spec = build_legacy_model(output, PhysicsSettings(dt=settings.dt,
        segment_m=settings.segment_m, rope_density=settings.density_kg_m3,
        friction=settings.friction,contact_time_s=settings.contact_time_s), layout=layout, robot=robot)
    tree = ET.parse(output/'scene.xml')
    root = tree.getroot(); root.set('model', 'slotted_post_ring_volumetric_fem_v1')
    root.find('option').set('integrator', settings.integrator)
    # CG exhausted 100 iterations on every late contact step; Newton converges
    # on the same observed states in 9--26 iterations.
    root.find('option').set('solver', 'Newton')
    root.find('option').set('tolerance', str(settings.solver_tolerance))
    root.find('option').set('iterations', str(settings.solver_iterations))
    root.find('option/flag').set('autoreset', 'disable')
    # With these full-flex nodes, 3.13's Euler implicit-joint-damping path
    # inverts tets even at half dt. Explicit damping is safe for alpha*dt
    # << 1 and is audited by independent main/half-step episodes.
    root.find('option/flag').set('eulerdamp', 'disable')
    world = root.find('worldbody'); equality = root.find('equality')
    for body in list(world.findall('body')):
        if body.get('name', '').startswith('cord_'):
            world.remove(body)
    equality.remove(equality.find("flex[@name='cord_lengths']"))
    root.remove(root.find('deformable'))
    points = centerline(layout, settings.segment_m)
    mesh = tube_tetrahedra(points, layout.rope_radius_m, settings.radial_segments)
    center_lookup = {int(v): i for i, v in enumerate(mesh['center_indices'])}
    body_names = []
    for i, (point, volume) in enumerate(zip(mesh['rest'], mesh['nodal_volumes'])):
        name = f'cord_{center_lookup[i]}' if i in center_lookup else f'fem_vertex_{i}'
        body_names.append(name)
        body = ET.SubElement(world, 'body', name=name, pos=values(point))
        for axis in range(3):
            ET.SubElement(body, 'joint', name=f'fem_{i}_{axis}', type='slide',
                          axis=values(np.eye(3)[axis]),
                          damping=str(volume*settings.density_kg_m3*settings.mass_damping_rate_s_inv))
        ET.SubElement(body, 'inertial', pos='0 0 0', mass=str(volume*settings.density_kg_m3),
                      diaginertia='1e-12 1e-12 1e-12')
        if i in center_lookup:
            j = center_lookup[i]
            ET.SubElement(body, 'site', name=f'cord_node_{j}' if j < len(points)-1 else 'cord_tip',
                          pos='0 0 0', size='.001', group='4')
    flex = ET.SubElement(ET.SubElement(root, 'deformable'), 'flex', name='cord', dim='3',
                        radius='0', body=' '.join(body_names), element=values(mesh['elements']),
                        rgba='.90 .88 .80 1', flatskin='false')
    native_E,native_nu=native_moduli(settings.young_pa,settings.poisson)
    ET.SubElement(flex, 'elasticity', young=str(native_E), poisson=str(native_nu),
                  damping=str(settings.rayleigh_s))
    # No inversion-prevention contacts: volume inversion is audited and fails
    # the run, rather than altering the material response to hide it.
    ET.SubElement(flex, 'contact', selfcollide='auto', internal='false', condim='3',
                  friction=f'{settings.friction} .002 .00005', solref=f'{settings.contact_time_s} 1',
                  solimp='.999 .9999 .001 .5 2')
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
    data = mujoco.MjData(model)
    for i, delta in enumerate(mesh['spawn']-mesh['rest']):
        for axis in range(3):
            data.qpos[model.joint(f'fem_{i}_{axis}').qposadr[0]] = delta[axis]
    if robot:
        data.qpos[:16] = [0, -.96, 1.16, 0, -.3, 0, .037, .037]*2
    # This keyframe is part of the reloadable model, so the straight stress
    # reference and the assembled initial state are both explicit in XML/MJB.
    keyframe = root.find('keyframe')
    if keyframe is None:
        keyframe = ET.SubElement(root, 'keyframe')
    ET.SubElement(keyframe, 'key', name='assembled', qpos=values(data.qpos))
    tree.write(output/'scene.xml', encoding='unicode')
    model = mujoco.MjModel.from_xml_path(str(output/'scene.xml'))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key('assembled').id)
    if robot:
        data.ctrl[:] = data.qpos[model.jnt_qposadr[model.actuator_trnid[:, 0]]]
    mujoco.mj_forward(model, data)
    constitutive=check_constitutive_response(model,mesh,settings)
    mujoco.mj_saveModel(model, str(output/'scene.mjb'))
    np.savez_compressed(output/'fem_mesh.npz', **mesh)
    spec.update(settings=asdict(settings), rope_model='3D tetrahedral Saint Venant-Kirchhoff FEM',
                material_calibrated=False, material_reference='straight untwisted tube',
                initialization_keyframe='assembled', length_equality_constraints=False,
                constitutive_checks=constitutive,
                native_elasticity_input=dict(young=native_E,poisson=native_nu,
                    convention='preserve physical shear modulus and halve native volumetric Lame coefficient'),
                fem=dict(vertices=len(mesh['rest']), tetrahedra=len(mesh['elements']),
                    minimum_initial_volume_ratio=float(mesh['initial_volume_ratios'].min()),
                    mass_kg=float(mesh['nodal_volumes'].sum()*settings.density_kg_m3),
                    endpoint_connection='center vertex to disc anchor; free-pivot, two-way constraint',
                    material_parameters_are_authored=True))
    (output/'model_spec.json').write_text(json.dumps(spec, indent=2)+'\n')
    return model, data, spec
