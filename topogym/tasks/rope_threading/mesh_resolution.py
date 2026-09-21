"""Choose a strictly finer comparison mesh relative to the production mesh."""


def refinement_settings(geometry, mesh):
    return dict(rope_subdivisions=int(geometry['rope_subdivisions']) + 2,
                radial_segments=int(geometry['radial_segments']) + 4,
                maxvolume=float(mesh['maxvolume']) / 2.)
