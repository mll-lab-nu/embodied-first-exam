"""Direction-aware acceptance for the permanently connected cable task."""
import numpy as np

from .contact_guard import FAILURE_REASON

CONTRACT_REVISION = "front_jacket_entry_all_fines_final_v3"


def plane_crossings(points, center):
    relative = np.asarray(points)-center
    crossings=[]
    for i,(a,b) in enumerate(zip(relative[:-1],relative[1:])):
        # Half-open segments count a vertex on the plane only once.
        if (a[0] < 0 <= b[0]) or (b[0] < 0 <= a[0]):
            p=a+(b-a)*(-a[0]/(b[0]-a[0]))
            crossings.append((i,float(np.linalg.norm(p[1:])),bool(b[0]>a[0])))
    return crossings


class AnchoredThreadingVerifier:
    """Observe every step; forbidden entry/anchor movement invalidates the episode.

    Full passage of a cable attached to a fixed terminal is not a valid goal.
    The distal jacket and all fine strands pass while the terminal remains near.
    """
    def __init__(self,layout,ring_center,terminal_origin,connector,ring_quat):
        self.layout=layout
        self.center=np.asarray(ring_center).copy()
        self.terminal=np.asarray(terminal_origin).copy()
        self.connector=np.asarray(connector).copy()
        self.ring_quat=np.asarray(ring_quat).copy()
        self.reasons=set()
        self.first_entry=None
        self.started=False
        self.max_anchor_error=0.
        self.first_forbidden_contact=None

    def update(self,*,coarse,fibers,terminal_pos,terminal_quat,ring_pos,ring_quat,
               forbidden_contact=None):
        if forbidden_contact is not None:
            self.reasons.add(FAILURE_REASON)
            if self.first_forbidden_contact is None:
                self.first_forbidden_contact=dict(forbidden_contact)
        arrays=(coarse,fibers,terminal_pos,terminal_quat,ring_pos,ring_quat)
        if not all(np.isfinite(a).all() for a in arrays):
            self.reasons.add("non_finite_state")
            return dict(success=False,failed=True,terminated=True,invalid_reasons=sorted(self.reasons),
                        first_forbidden_contact=self.first_forbidden_contact)
        coarse,fibers=np.asarray(coarse),np.asarray(fibers)
        error=max(float(np.linalg.norm(np.asarray(terminal_pos)-self.terminal)),
                  float(np.linalg.norm(coarse[0]-self.connector)))
        self.max_anchor_error=max(error,self.max_anchor_error)
        if error>5e-5 or abs(float(np.asarray(terminal_quat)@[1.,0.,0.,0.]))<1-1e-6:
            self.reasons.add("fixed_terminal_or_attachment_moved")
        if np.linalg.norm(np.asarray(ring_pos)-self.center)>5e-5 or abs(float(np.asarray(ring_quat)@self.ring_quat))<1-1e-6:
            self.reasons.add("fixed_ring_moved")
        crossings=plane_crossings(coarse,self.center)
        if not self.started:
            if max(coarse[:,0].max()+self.layout.trunk_radius_m,
                   fibers[:,:,0].max()+self.layout.fiber_radius_m)>=self.center[0]-self.layout.ring_tube_radius_m:
                self.reasons.add("invalid_reset_not_entirely_on_entry_side")
            self.started=True
        if crossings and self.first_entry is None:
            # Direction is determined by the first COARSE segment entering.
            # Fine tips may enter before or after the distal jacket while
            # contacts keep shaping them. Only their final full passage is
            # required; demanding every tip first is an extra ordering rule.
            legal=(len(crossings)==1 and crossings[0][0]==len(coarse)-2 and crossings[0][2]
                and crossings[0][1]+self.layout.trunk_radius_m<self.layout.minimum_aperture_radius)
            self.first_entry="head_first" if legal else "forbidden"
            if not legal:self.reasons.add("rear_or_loop_first_or_bypass_entry")
        if any(r+self.layout.trunk_radius_m>self.layout.minimum_aperture_radius+.0003 for _,r,_ in crossings):
            self.reasons.add("coarse_cable_bypassed_aperture")
        exit_plane=self.center[0]+self.layout.ring_tube_radius_m
        full_fibers=bool((fibers[:,:,0].min(axis=1)-self.layout.fiber_radius_m>exit_plane).all())
        # At least 30 mm of the working jacket, rather than its tip alone.
        front_jacket=bool(coarse[-1,0]-exit_plane>.030 and coarse[-2,0]<coarse[-1,0])
        path_through_hole=(len(crossings)==1 and crossings[0][2]
                          and crossings[0][1]+self.layout.trunk_radius_m<self.layout.minimum_aperture_radius)
        checks=dict(terminal_and_ring_unchanged=not any("moved" in r for r in self.reasons),
            head_first_entry=self.first_entry=="head_first",all_fine_strands_beyond=full_fibers,
            front_jacket_inserted=front_jacket,single_forward_aperture_crossing=bool(path_through_hole),
            trailing_end_stays_near=bool(coarse[0,0]<self.center[0]-self.layout.ring_tube_radius_m),
            no_gripper_fine_contact=FAILURE_REASON not in self.reasons,
            valid_history=not self.reasons)
        success=all(checks.values())
        return dict(success=success,failed=bool(self.reasons),terminated=bool(self.reasons) or success,
                    contract_revision=CONTRACT_REVISION,
                    checks=checks,invalid_reasons=sorted(self.reasons),
                    first_forbidden_contact=self.first_forbidden_contact,
                    first_coarse_entry=self.first_entry,max_attachment_error_m=self.max_anchor_error,
                    coarse_plane_crossings=crossings)
