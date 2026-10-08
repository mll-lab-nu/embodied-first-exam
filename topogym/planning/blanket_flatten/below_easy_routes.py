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
    # Lifting a patch off the stacked corner loads the layer under the pinch to 1.29-1.33 (2026-10-07); like
    # medium / hard, easier declares the 1.5 guard.
    max_strain_ratio=1.5,
    check_contact_ik=True,
    # Every grasp lands on two or three stacked layers. Commanded 1.5 mm above the patch, a right pinch reached 4.9 mm
    # into the stack (its TCP 2.2 mm low, the fingertips 4.2 mm beyond the modelled extension) and stretched the lower
    # layer to 1.50 (2026-10-07); the contact feedback lowers from 8 mm until the assist admits each hand.
    fingertip_gap_m=.008,
    # The first admitted hand of the two-hand page turn kept sinking 2 mm after its command stopped and pressed its
    # held patch into the lower layer (1.46, then lost) while the other hand descended (2026-10-07): hold it at the
    # measured height of its admission instead.
    hold_admitted_height=True,
    settle_s=30.,
    # Up to three measured fold layouts after the route: each lays out the then largest folded corner.
    fold_layout=dict(settle_s=5., deviation_m=.03, corner_radius_m=.15, min_particles=25, max_stages=3),
    stages=(
        # Undo the authored folds in reverse order. The far half lies folded
        # over the near half, which stays on its own footprint, so no stage
        # moves the packet.
        # A held patch keeps its orientation while the hand turns a layer over,
        # so the turned layer leaves it on the far side and wraps back around
        # it; carried to the mirrored position, the wrap pulls the patch rim
        # taut (1.50 laying this corner 1 cm short, 2026-10-07). As in hard's
        # page turns: a low arc, land short, release 3 cm above the table, and
        # spread the layer afterwards with fresh grasps.
        # 1. The upper layer's turned corner lies on top: its fold carries this
        #    grasp, 14 mm from the tip so that the tip is inside the patch, from
        #    (-0.004, 0.078) to (0.152, -0.078) in the table frame, 11 cm each
        #    side of the fold line; land 7 cm past it. The flipped patch is left
        #    for the fold layouts.
        dict(grasp_uv=dict(right=(.29, .23)), segments=(
            dict(name="lift_corner", duration_s=1.5, by=dict(right=(0., 0., .054))),
            dict(name="turn_corner", duration_s=3.5, by=dict(right=(.078, -.078, .09))),
            dict(name="lay_corner", duration_s=3.5, by=dict(right=(.125, -.125, .03))),
        )),
        # 2. Both hands turn the upper layer back over the crease (y = 0.15).
        #    The arms are mirror images about x = -0.136 and reach top-down only
        #    9-11 cm past it (measured 2026-10-07), so each holds the free edge
        #    on its own side, on its last particle row but one (6 mm in) and
        #    8 cm from its corner: (-0.356, -0.084) and (0.084, -0.084), 23.4 cm
        #    from the crease, land at y = 0.33, 18 cm past it. (Held 19 cm from
        #    the corners, the outer strips folded back onto the layer; held 2 cm
        #    in, the 2 cm beyond the flipped patches folded back along the whole
        #    edge like a hem and cost 8 % coverage, 2026-10-07.)
        dict(grasp_uv=dict(left=(-.22, .234), right=(.22, .234)), segments=(
            dict(name="lift_page", duration_s=1.5, by=dict(left=(0., 0., .054), right=(0., 0., .054))),
            dict(name="turn_page", duration_s=4., to=dict(left=(-.356, .15, .12), right=(.084, .15, .12))),
            dict(name="lay_page", duration_s=4., to=dict(left=(-.356, .33, .03), right=(.084, .33, .03))),
        )),
        # 3. Between the flipped patches the upper layer now lies face up: pinch
        #    it there, 7 cm inside them and 4 cm in from the free edge, and pull
        #    it out to 1 cm short of its flat place (y = 0.35), the near half
        #    held by table friction, as easy spreads. (A pinch on a strip folded
        #    back is a second page turn: its rim reached 1.50, 2026-10-07.)
        dict(grasp_uv=dict(left=(-.15, .20), right=(.15, .20)), segments=(
            dict(name="lift_edge", duration_s=1.5, by=dict(left=(0., 0., .05), right=(0., 0., .05))),
            dict(name="spread_edge", duration_s=4., to=dict(left=(-.286, .34, .05), right=(.014, .34, .05))),
            dict(name="lay_edge", duration_s=2., to=dict(left=(-.286, .34, .03), right=(.014, .34, .03))),
        )),
    ),
)
