"""Verified release of multiple temporary Genesis welds.

The installed Genesis delete kernel moves only eq_type when removing a
non-tail dynamic equality; its object IDs and frame data are not moved.
Remove our constraints in reverse registration order to avoid that branch,
and read the solver's actual constraints instead of trusting a Python flag.
"""

import numpy as np


def active_grasps(solver, body_links):
    constraints = solver.get_weld_constraints(as_tensor=True, to_torch=True)

    def values(x):
        return np.asarray(
            x.detach().cpu().numpy() if hasattr(x, "detach") else x
        ).ravel()

    return [
        [int(a), int(b)]
        for a, b in zip(values(constraints["link_a"]), values(constraints["link_b"]))
        if a >= 0 and b >= 0 and (a in body_links or b in body_links)
    ]


def release_grasps(solver, registration_order):
    body_links = {b for _, b in registration_order}
    before = active_grasps(solver, body_links)
    if {tuple(p) for p in before} != set(registration_order):
        raise RuntimeError(f"Unexpected grasp constraints before release: {before}")
    for a, b in reversed(registration_order):
        solver.delete_weld_constraint(a, b)
    after = active_grasps(solver, body_links)
    if after:
        raise RuntimeError(f"Grasp constraints remain after release: {after}")
    return dict(
        before=before,
        deletion_order=[list(p) for p in reversed(registration_order)],
        after=after,
        verification="solver.get_weld_constraints, not a controller flag",
    )
