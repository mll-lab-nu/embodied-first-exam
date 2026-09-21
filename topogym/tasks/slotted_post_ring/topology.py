"""Observe ordered hole crossings along the measured cord.

The chain representation follows the idea in Cabalar and Santos, Formalising
the Fisherman's Folly puzzle, Figure 4. This geometric monitor supplements,
and cannot replace, continuous contact and stretch checks.
"""
import numpy as np

from .physics import node_positions
from .geometry import SlottedPostLayout


def cord_chain(model, data, layout=SlottedPostLayout()):
    points = node_positions(model, data)
    events = []
    for name, axis, radius in [('target_ring',2,layout.ring_inner_radius), ('bead_left',2,layout.bead_hole_radius_m),
                                ('bead_right',2,layout.bead_hole_radius_m), ('post',1,0.)]:
        body = model.body(name).id
        local = (points-data.xpos[body])@data.xmat[body].reshape(3,3)
        a, b = local[:-1], local[1:]
        for i in np.flatnonzero(a[:,axis]*b[:,axis] < 0):
            u = -a[i,axis]/(b[i,axis]-a[i,axis])
            crossing = a[i]*(1-u)+b[i]*u
            if name == 'post':
                half_width=layout.slot_width_m/2
                z = np.clip(crossing[2], layout.slot_bottom_m+half_width, layout.slot_top_m-half_width)
                inside = np.hypot(crossing[0],crossing[2]-z) < half_width
            else:
                inside = np.linalg.norm(np.delete(crossing,axis)) < radius
            if inside:
                events.append(dict(segment=int(i), fraction=float(u), hole=name,
                                   sign=1 if b[i,axis]>a[i,axis] else -1))
    events.sort(key=lambda e:e['segment']+e['fraction'])
    return events


def reduced_chain(events):
    result=[]
    for event in events:
        if result and result[-1]['hole']==event['hole'] and result[-1]['sign']==-event['sign']:
            result.pop()
        else:
            result.append(event)
    return result
