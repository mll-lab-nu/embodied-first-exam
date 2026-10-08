"""One fixed ring and two posts: the smallest complete recursive Orbits fixture."""
from topogym.tasks.base import merge_parameters
from .below_easy import OrbitsBelowEasyTask


class OrbitsEasierTask(OrbitsBelowEasyTask):
    variation_id = 'orbits_easier'
    family_id = 'single_ring_two_posts'
    difficulty = 'easier'
    # Resized for the standard solution (user, 2026-10-07): a gripper reaches down through the ring hole to the bight
    # around the ring's support post, lifts it up through the hole and over the ball onto the ball post; the loop then
    # passes around the whole ring. Posts 165 mm apart and a 220 mm aperture leave 138 mm between the support-side rim
    # and the ball, where a pinch on the 70 mm bight's deepest point clears the ring, posts and ball by 19.6 mm in the
    # nominal MuJoCo IK check (10 mm at 135 mm spacing, where the real gripper met the ring). A 1.25 m cord loop goes
    # around the unchanged ring: the MuJoCo reference run of the whole solution with weld-driven links came off with the
    # middle tie within 0.6 mm; 1.05 m caught on the ring (7.3 mm), and a ring 3 cm larger caught even with 1.35 m.
    # Values before the 0.85 scale.
    variant_parameters = merge_parameters(OrbitsBelowEasyTask.variant_parameters, {
        'cord_profile': 'easier_ring_hole_v2',
        'geometry': {'post_spacing_m': .165/.85, 'ring_radius_m': .11/.85+.008, 'base_length_m': .36/.85,
                     'base_width_m': .26/.85, 'bight_radius_m': .07/.85},
    })
    defaults = merge_parameters(OrbitsBelowEasyTask.defaults, variant_parameters)
