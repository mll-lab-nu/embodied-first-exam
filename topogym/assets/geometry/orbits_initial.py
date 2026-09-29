"""Pure initial cord construction from the video-v2 archive, without its old engine."""
import numpy as np
from scipy.interpolate import PchipInterpolator

def resample(points, spacing=.006):
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    samples = np.linspace(0., arc[-1], int(np.ceil(arc[-1]/spacing))+1)
    return np.column_stack([np.interp(samples, arc, points[:, i]) for i in range(3)])

def working_cord(layout, spacing=.006):
    """Legacy folded slack used by the recorded development probes.

    This doubles back beyond the handle. New bimanual scenes use
    natural_working_state instead; retain this shape for old probe/fixture parity.
    """
    if layout.ring_count != 4:
        raise ValueError('Legacy folded slack is authored only for four rings')
    l = layout
    z = l.base_height_m+l.cord_radius_m+.0015
    control = np.array([[l.post_x[-1], l.bight_radius_m, z],
                        [.185, .012, z], [.215, .04, .005],
                        [.265, .14, .005], [.42, .16, .005],
                        [.54, .10, .005], [.52, .025, .005],
                        [.39, .015, .005],
                        [l.eyes[1, 0]+.012, l.eyes[1, 1], l.handle_height_m+.014],
                        [l.eyes[1, 0], l.eyes[1, 1], l.handle_height_m+.010],
                        [l.eyes[1, 0], l.eyes[1, 1], l.handle_height_m*.55]])
    arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(control,axis=0),axis=1))]
    positive=PchipInterpolator(arc,control,axis=0)(np.linspace(0,arc[-1],700))
    negative=positive.copy();negative[:,1]*=-1
    theta=np.linspace(-np.pi/2,-3*np.pi/2,80)
    bend=np.column_stack([l.post_x[-1]+l.bight_radius_m*np.cos(theta),
                          l.bight_radius_m*np.sin(theta),np.full(len(theta),z)])
    # Each half uses identical material sampling so the true bight is a vertex.
    left=resample(np.vstack([negative[::-1],bend[1:41]]),spacing)
    right=left[::-1].copy();right[:,1]*=-1
    left[-1,1]=right[0,1]=0.
    return np.vstack([left,right[1:]])

def natural_working_state(layout, *, handle_x_m=.60, cord_length_m=None,
                          spacing=.0075):
    """Lay one open oval around the last post, with the free handle at its far end.

    Slack bows outward on either side; neither leg doubles back past its eye.
    Four-ring length defaults to the legacy working cord. Reduced fixtures
    require an explicit length so old four-ring slack is not silently reused.
    Returned points describe the rest shape, not positions driven during motion.
    """
    from dataclasses import replace
    from scipy.optimize import brentq
    from .orbits import cord_centerline
    l = layout
    if not np.isfinite([handle_x_m, spacing]).all() or spacing <= 0:
        raise ValueError('Handle position and spacing must be finite; spacing positive')
    placed = replace(l, handle_x_m=float(handle_x_m)).validate()
    if cord_length_m is None:
        if l.ring_count != 4:
            raise ValueError('Reduced-ring initialization requires explicit cord_length_m')
        old = working_cord(l, spacing)
        cord_length_m = float(np.linalg.norm(np.diff(old, axis=0), axis=1).sum())
    if not np.isfinite(cord_length_m) or cord_length_m <= 0:
        raise ValueError('Cord length must be positive and finite')
    dense = cord_centerline(placed)
    half = dense[len(dense)//2:].copy()
    half = np.vstack([[l.post_x[-1]-l.bight_radius_m, 0, half[0, 2]], half])
    t = np.clip((half[:, 0]-l.post_x[-1]) /
                (placed.eyes[1, 0]-placed.handle_bend_radius_m-l.post_x[-1]), 0, 1)
    samples = int(np.ceil(cord_length_m/(2*spacing)))+1

    def shaped(width):
        points = half.copy()
        points[:, 1] += width*np.sin(np.pi*t)**2
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
        query = np.linspace(0, arc[-1], samples)
        return np.column_stack([np.interp(query, arc, points[:, i]) for i in range(3)])

    def excess(width):
        return 2*np.linalg.norm(np.diff(shaped(width), axis=0), axis=1).sum()-cord_length_m

    if excess(0) > 1e-10:
        raise ValueError('Cord too short to reach the requested handle position')
    width = brentq(excess, 0, cord_length_m/2, xtol=1e-12)
    positive = shaped(width)
    negative = positive[::-1].copy(); negative[:, 1] *= -1
    points = np.vstack([negative, positive[1:]])
    handle = np.array([handle_x_m, 0, l.handle_height_m/2+l.clearance_m])
    return points, handle
