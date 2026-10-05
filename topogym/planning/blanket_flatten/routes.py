"""Two-hand material routes for the frozen gathered Blanket representatives.

A route is a sequence of stages. Each stage names two material grasp points
(rest UV, metres) and piecewise-linear patch targets; a segment without `to`
holds the hands still. Targets are world XY and height above the table top of
the held patch centre. Both hands release at the end of every stage; the next
stage regrasps on the live cloth. The virtual-hand witness and the robot oracle
read the same route; the robot adds its TCP offset above the pinched patch.

The robot runner passes PATCH to the assist's SoftGraspTarget, so the witness
pins what the real assist would hold, not an idealised whole edge.

`settle_s` bounds how long the robot waits, hands withdrawn, for the Task's own
settled predicate after the last release (10 s unless a route needs longer).
`max_strain_ratio` is the assist's material-edge guard for the route. The
default 1.3 is kept wherever a route stays below it. A route that must carry
the cloth's weight on two pinches declares a higher value explicitly; see the
proof README for the trade-off.
"""

PATCH = dict(spatial_radius_m=.018, material_radius_m=.018)
# Routes target the current frozen states (gathered_archive_v2). The accepted proofs ran on gathered_scene_v1, where
# the cloth differs by up to 19 mm; their routes are in each run's source_snapshot. On v2 three pinches were covered
# by another layer, so each moved to the nearest exposed point and, for absolute targets, its hand's targets moved
# by the same offset.
DEFAULT_STRAIN_GUARD = 1.3

# easy / gathered_scene_v1 / seed 0: pleats run along X and gather the width
# from 0.48 m to about 0.31 m. Pinch both corners of the far long edge
# (v = +0.24 side, 2 cm inset), lift 10 cm and drag outward so that the near
# edge stays anchored by table friction while tension opens the pleats; stop
# short of a taut sheet, then finish the spread while lowering. A full hang
# (0.5 m lift) also flattens but carries the whole weight on two patches
# (peak edge ratio about 1.5 near the pinch, above the assist's 1.3 guard).
EASY = dict(
    max_strain_ratio=DEFAULT_STRAIN_GUARD,
    stages=(dict(
        grasp_uv=dict(left=(-.27, .234), right=(.28, .22)),   # v1: left (-.28, .22)
        segments=(
            dict(name="lift", duration_s=1.5, to=dict(left=(-.395, .304, .10), right=(.135, .28, .10))),
            dict(name="drag", duration_s=6., to=dict(left=(-.405, .404, .10), right=(.145, .39, .10))),
            dict(name="lower", duration_s=3., to=dict(left=(-.405, .454, .015), right=(.145, .44, .015))),
        ),
    ),),
)

# medium / seed 0: the partly relaxed twist leaves the far edge on the far side
# along its length, but the last ~8 cm of the far-left edge is tucked under
# (only its fold crest, v = +0.16, passes the assist's exposure test) and the
# far-right corner is folded. Folds left on the table keep jittering under PBD
# self-contact, so the Task's settled gate never holds; the route must lay
# every edge out. Pinch the left crest and the exposed far-right point, drag
# outward past the flat position at 10 cm so the tucked strip hangs below the
# left hand, then lower while moving that hand back: the hanging strip lands
# outward instead of under. Two end-of-lowering spikes at the left pinch were
# removed: the V-shaped crest patch is released 3 cm above the table (pressing
# its lower layer into the table drove the edge ratio to ~1.7), and the hand
# moves back only 3 cm (a longer move stretches the strip once friction holds
# it on the table: 1.51 in a robot run). The laid-out edge keeps relaxing for
# ~20 s after release before the sheet comes to rest. Over-pulling the far
# edge still loads the pinch slightly past the default guard (about 1.31),
# hence the declared 1.5.
MEDIUM = dict(
    max_strain_ratio=1.5,
    settle_s=40.,
    stages=(dict(
        grasp_uv=dict(left=(-.27, .156), right=(.26, .20)),   # v1: left (-.27, .16)
        segments=(
            dict(name="lift", duration_s=1.5, to=dict(left=(-.407, .251, .10), right=(.115, .249, .10))),
            dict(name="drag", duration_s=6., to=dict(left=(-.407, .476, .10), right=(.115, .46, .10))),
            dict(name="lower", duration_s=3., to=dict(left=(-.407, .446, .03), right=(.115, .50, .03))),
        ),
    ),),
)

# hard / seed 0: a band with about one full (+360 deg) twist; both ends lie face
# down, the middle face up. Wrist rotation is limited, so the twist is removed
# without turning a wrist: stage A turns each end over like a page about the
# long axis (left end +180 deg: its far-side edge is lifted over toward the
# robot; right end -180 deg: its near-side edge is lifted over away from it),
# with a low 9 cm arc to keep the pinch load down. The corners themselves are
# under other layers, so each pinch sits on the lifted edge 4 cm from its
# corner, where the patch is exposed, flat and complete. The untwisted
# sheet then lies diagonally with its right end still gathered; stage B pulls
# the far-left side outward and the near-right side toward the robot (a
# rotation couple, grasp-relative) to open both ends, and the sheet relaxes
# flat over ~40 s after release. As in medium, patches are released 3 cm
# above the table so that pinned particles are never pressed into it. The
# left page turn lands short of the mirrored position (y -0.04, not -0.12):
# carrying the flipped end further pulls it taut over the hinge and drove the
# edge ratio at that pinch to ~1.48.
# oraclefix 11 (lab, 2026-10-04): on lab's runs stage B leaves the far-left corner folded; its crest jitters under PBD
# self-contact (E24: spikes up to 0.22 m/s in 5.6 % of 2.5 ms ticks 20 s after the last action, all on that crest), so
# the settled window never completes and the coverage stays at 0.942. After stage B and a `fold_layout` settle, the
# robot measures the sheet and lays out the largest folded corner with one hand (robot_oracle.fold_stage); the relay
# before the measurement ends as soon as the sheet is quiet (cap fold_layout.settle_s), the final settle at success.
HARD = dict(
    max_strain_ratio=1.5,
    settle_s=60.,
    fold_layout=dict(settle_s=25., deviation_m=.03, corner_radius_m=.15, min_particles=25),
    stages=(
        dict(
            grasp_uv=dict(left=(-.29, -.20), right=(.28, .20)),
            segments=(
                dict(name="lift", duration_s=1.5, to=dict(left=(-.335, .248, .054), right=(.066, .073, .054))),
                dict(name="over", duration_s=3.5, to=dict(left=(-.35, .06, .09), right=(.075, .21, .09))),
                dict(name="down", duration_s=3.5, to=dict(left=(-.35, -.04, .03), right=(.08, .35, .03))),
            ),
        ),
        dict(
            grasp_uv=dict(left=(-.24, .10), right=(.228, -.108)),   # v1: right (.24, -.12)
            segments=(
                dict(name="lift", duration_s=1.5, by=dict(left=(0., 0., .08), right=(0., 0., .08))),
                dict(name="pull", duration_s=6., by=dict(left=(-.0155, .0264, .08), right=(.0357, -.0609, .08))),
                dict(name="lower", duration_s=3., by=dict(left=(-.0182, .0311, .03), right=(.0420, -.0716, .03))),
            ),
        ),
    ),
)

ROUTES = dict(easy=EASY, medium=MEDIUM, hard=HARD)
