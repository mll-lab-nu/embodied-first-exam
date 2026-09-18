"""Continuous-angle oracle for free passive discs; no memorized beat list."""
import numpy as np
from topogym.tasks.lock_picking._staged_lock_geometry import angle_error


def next_entry_angle(layout,state,level):
    current=state['key_deg']
    targets=([layout.endpoint_deg] if level==3 else
             [state['disc_deg'][level]+s for s in layout.slots[level]])
    targets=[current+(a-current+180)%360-180 for a in targets]
    # Physical first family is chosen to admit small wrist rotations.
    return min(targets,key=lambda a:abs(a-current))


def insertion_window(layout,state,level,safety_deg=.6):
    """Choose a direction fitting all previously engaged slots and next disc.

    Previous discs may be at a contact edge because of finite backlash. Search
    only a local continuous interval; deeper discs are not assigned new angles.
    """
    current=state['key_deg']
    choices=np.linspace(current-8,current+8,161)
    scores=[]
    for a in choices:
        margins=[layout.slot_margin(a,state['disc_deg'][i],i) for i in range(min(level+1,3))]
        if level==3:
            margins.append(layout.slot_half_deg-layout.tab_half_deg-angle_error(a,layout.endpoint_deg))
        scores.append(min(margins))
    best=int(np.argmax(scores))
    if scores[best] < safety_deg:
        raise RuntimeError(f'No safe common insertion window at level {level}: {max(scores):.3f} deg')
    return float(choices[best]),float(scores[best])
