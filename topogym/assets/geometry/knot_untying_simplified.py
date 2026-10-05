"""Open single-bight layouts, at the existing easy rope/table scale.

These are authored crossing diagrams, not claims about closed-knot invariants.
Both keep the easy template's 80 mm loop radius and two free graspable tails.
"""
import numpy as np
from scipy.interpolate import CubicSpline


def simplified_centerline(layout):
    if layout.family not in {"single_overlap_loop", "alternating_overlap_loop"}:
        raise ValueError(f"Unsupported simplified loop: {layout.family}")
    scale = layout.planar_scale_m / .032
    theta = np.linspace(np.deg2rad(-117), np.deg2rad(-423), 1001)
    circle = np.column_stack((.08*np.cos(theta), .08*np.sin(theta)))
    if layout.family == "single_overlap_loop":
        controls = np.array([circle[0], [-.018, -.103], [.028, -.150],
                             [.090, -.220], [.145, -.278]])
        end_direction = [.69, -.73]
    else:
        # Same planar neck as easy; the second overlap reverses its layering.
        controls = np.array([circle[0], [-.018, -.103], [.035, -.145],
                             [-.01, -.195], [-.10, -.255], [-.145, -.278]])
        end_direction = [-.89, -.455]
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(controls, axis=0), axis=1))]
    direction = [-np.sin(theta[0]), np.cos(theta[0])]
    left = CubicSpline(arc, controls, bc_type=((1, direction), (1, end_direction)))(
        np.linspace(0, arc[-1], 1001))
    right = left * [-1., 1.]

    # Solve each symmetry-axis crossing on the dense planar curve. Compact C2
    # height bumps lift only the strand that goes OVER at that crossing, with
    # zero elevation and slope at the bight and free ends.
    edges = np.flatnonzero(left[:-1, 0]*left[1:, 0] < 0)
    expected = 1 if layout.family == "single_overlap_loop" else 2
    if len(edges) != expected:
        raise ValueError("Simplified neck has an unexpected crossing count")
    heights = [np.zeros(len(left)), np.zeros(len(right))]
    for crossing, i in enumerate(edges):
        t = -left[i, 0]/(left[i+1, 0]-left[i, 0])
        center_y = left[i, 1]+t*(left[i+1, 1]-left[i, 1])
        offset = np.clip((left[:, 1]-center_y)/.040, -1., 1.)
        heights[crossing % 2] += 2*layout.crossing_height_m*(.5+.5*np.cos(np.pi*offset))**2
    left = np.column_stack((left*scale, heights[0]))
    right = np.column_stack((right*scale, heights[1]))
    circle = np.column_stack((circle*scale, np.zeros(len(circle))))
    raw = np.vstack((left[:0:-1], circle, right[1:]))
    raw[:, 2] += layout.rope_radius_m+layout.table_clearance_m
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(raw, axis=0), axis=1))]
    samples = np.linspace(0, arc[-1], int(np.ceil(arc[-1]/layout.segment_length_m))+1)
    points = np.column_stack([np.interp(samples, arc, raw[:, k]) for k in range(3)])
    if layout.handedness == "left":
        points[:, 0] *= -1
    return points
