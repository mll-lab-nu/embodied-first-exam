"""Grasp fixture using the shared FEM rope recipe; baseline is kept separately."""
import json
from pathlib import Path
import numpy as np
from topogym.assets.materials import rope_fem_parameters, rope_ipc_parameters
from topogym.assets.geometry.rope_volume import write_rope_volume, RADIAL_SEGMENTS

PROFILES = ('baseline', 'v13_material_mesh')


def historical_rope_asset(folder, center, length):
    """Short straight specimen of the production rope, without extra damping."""
    from topogym.utils.geometry.rope import write_obj
    folder = Path(folder)
    line = np.array([[-length/2, 0, 0], [length/2, 0, 0]])+center
    volume = write_rope_volume(folder/'volume.npz', line, .004)
    surface = folder/'rope.obj'
    with np.load(volume) as data:
        rest, elements = data['rest'], data['elements']
        corners = rest[elements]
        det = np.linalg.det(corners[:, 1:]-corners[:, :1])
        # Boundary indices refer to the preserved TetGen input vertices.
        faces = data['surface_faces']
        write_obj(surface, data['spawn'][:int(faces.max())+1], faces)
        stations = data['material_s_m'][data['surface_ring_indices'][:, 0]]
        metadata = dict(profile='v13_material_mesh', material=rope_fem_parameters(),
            length_m=length, diameter_m=.008, axial_spacing_m=float(stations[1]-stations[0]),
            radial_segments=RADIAL_SEGMENTS, tetgen_switches=str(data['tetgen_switches']),
            vertices=len(rest), tetrahedra=len(elements),
            max_actual_tet_volume_m3=float(abs(det).max()/6),
            contact_d_hat_m=rope_ipc_parameters()['contact_d_hat'],
            historical_deformation_damping_rate_s_inv=20.,
            applied_deformation_damping_rate_s_inv=0.,
            scope='shared production material and mesh on a short grasp fixture; no historical damping or controller')
    (folder/'rope_profile.json').write_text(json.dumps(metadata, indent=2)+'\n')
    return surface, volume
