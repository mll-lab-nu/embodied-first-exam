"""Geometric diagnostics for measured cord states; no screenshot inference."""
import numpy as np
from .geometry import winding_numbers


def threading_signature(points,layout):
    points=np.asarray(points)
    # The two terminal eyes are joined by the wooden handle. Its internal
    # chord closes the curve for linking-number diagnostics.
    closed=np.vstack([points,points[0]])
    a,b=closed[:-1],closed[1:]
    half=(len(points)-1)//2
    crossings=[]
    for x,z in zip(layout.ring_x,layout.ring_z):
        ids=np.flatnonzero((a[:,2]-z)*(b[:,2]-z)<0)
        if len(ids):
            t=(z-a[ids,2])/(b[ids,2]-a[ids,2])
            hit=a[ids]+t[:,None]*(b[ids]-a[ids])
            ids=ids[np.linalg.norm(hit[:,:2]-[x,0],axis=1)<layout.ring_radius_m]
        crossings.append([dict(segment=int(i),direction=int(np.sign(b[i,2]-a[i,2])),half=int(i>=half)) for i in ids])
    return dict(planar_post_winding=np.round(winding_numbers(points,layout.post_x),6).tolist(),
                ring_disk_crossings=crossings,
                ring_linking_numbers=[sum(c['direction'] for c in group) for group in crossings],
                closure='straight chord inside the connected wooden handle',
                scope='diagnostic only; planar winding and disk counts are not a solution certificate')
