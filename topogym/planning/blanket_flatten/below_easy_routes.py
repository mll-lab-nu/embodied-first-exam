"""Corner-fold route candidates; qualification belongs to each measured run.

Use the same local PBD grasp patch, robot approach and native terminal predicate
as the existing gathered routes. No coloured corner cues are needed: the
privileged reference locates grasp points in the frozen material coordinates.
"""

VERY_EASY = dict(
    max_strain_ratio=1.3,
    check_contact_ik=True,
    settle_s=20.,
    stages=(dict(
        grasp_uv=dict(right=(.282, -.222)),
        segments=(
            dict(name="lift_corner", duration_s=1.5, by=dict(right=(0., 0., .055))),
            dict(name="turn_corner", duration_s=3., to=dict(right=(.025, .05, .15))),
            # Release before pulling the whole attached patch taut. The first
            # measured run already covered 97% while approaching this region;
            # an additional outward pull crossed the unchanged 1.3 guard.
            dict(name="lay_corner", duration_s=3., to=dict(right=(.085, -.01, .025))),
        ),
    ),),
)

EASIER = dict(
    max_strain_ratio=1.3,
    check_contact_ik=True,
    settle_s=30.,
    fold_layout=dict(settle_s=5., deviation_m=.03, corner_radius_m=.15, min_particles=25),
    stages=(
        # Begin on the exposed two-layer portion. Pinching above the four-layer
        # corner caused a strain failure in an underlying, unheld layer.
        dict(grasp_uv=dict(left=(-.17, .06)), segments=(
            dict(name="lift_half", duration_s=1.5, by=dict(left=(0., 0., .07))),
            dict(name="turn_half", duration_s=4., to=dict(left=(-.21, .21, .15))),
            dict(name="lay_half", duration_s=4., to=dict(left=(-.305, .21, .04))),
        )),
        VERY_EASY["stages"][0],
        dict(grasp_uv=dict(right=(.282, .222)), segments=(
            dict(name="lift_edge", duration_s=1.5, by=dict(right=(0., 0., .07))),
            dict(name="spread_edge", duration_s=4., to=dict(right=(.146, .372, .08))),
            dict(name="lay_edge", duration_s=3., to=dict(right=(.146, .372, .03))),
        )),
    ),
)
