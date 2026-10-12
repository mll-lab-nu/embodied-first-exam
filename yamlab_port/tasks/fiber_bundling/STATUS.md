# fiber_bundling -> YAMLab: status

Updated 2026-10-12, final (agent: fiber_bundling task agent).

## State (final, 2026-10-12)

| tier | task | goal check | oracle | replay | nop | naive | evidence |
|---|---|---|---|---|---|---|---|
| very_easy | DONE (`FiberBundling-VeryEasy-v0`, 47 links) | old predicate, thresholds unchanged | SUCCESS step 2921 (97.4 s sim, 49 s wall) | succeeds at the same step; bit-identical to the oracle run and between 2 replays | fails (300 s) | no-comb: fiber_gripper_contact; 12 mm off-axis feed: no success (jacket blocked) | `out/vef*` |
| easier | DONE (`FiberBundling-Easier-v0`, 57 links) | same | SUCCESS step 3808 (127.0 s sim, 70 s wall) | same (bit-identical x2) | fails (300 s) | same two failures | `out/eaf*` |

Video: not rendered (RTX crashes on vast). Lead: run `render_on_rtx.sh <yamlab clone> <outdir>` on ws/ws3.

## How to reproduce (vast, see README)

`R=/workspace/yamlab_port/runs/fiber_bundling`: build assets (`tools/build_assets.py --tier <tier> --tx 0.25 --ty -0.01`),
`install.sh $R/yamlab $R/assets`, then `checks.sh <prefix> FiberBundling-VeryEasy-v0` (or `-Easier-v0`) runs oracle,
nop, 2 replays and 2 naive variants into `$R/out/<prefix>*`. The final evidence is `vef*` and `eaf*`. Their
`actions.npy` replay bit-identically with `tools/replay.py`, whatever the oracle code version.

Note: after vef/eaf the oracle's feed was changed for the easy tier (it now re-aligns on the axis while backing off
10 mm before advancing). With the new code, easier still succeeds (`ea5`: step 3875, 129.2 s, metrics in `out/ea5`);
very_easy has not been re-run with it.

## Easy tier (4 strands): NOT done, stopped by the wrap-up order

Ready:
- `FiberBundling-Easy-v0` is registered (yaml, cfg, manager, install.sh); `assets/easy/` is built (67 links,
  strands fanning -x, up, +x, down).
- The oracle runs end to end on it.

Results:
- `es1`: combing works. Six presses take all four strands to 8.0 mm, i.e. straight, at the root radius.
  The feed then failed (`fiber_gripper_contact`, step 5037). After the last re-centre the hand lagged its command
  by 3.9 mm, so the sheath stayed about 7 mm off axis while the combed tips sat ~9 mm before the ring plane. The
  first feed move pushed the tips into the ring tube; the strands spread to 30-60 mm, folded back and touched
  the fingers.
- `es2`: feed now aligns while backing off 10 mm. The strands still spread while the jacket advances from
  -87 mm to -45 mm. Two strands go from 8 to 19-31 mm, with small contact forces of 2-5 mN, i.e. strands
  touching each other or the ring. The run ended with the same `fiber_gripper_contact` (step 5170).

Missing: an easy oracle success, replay, nop and naive runs.

Best next ideas:
1. After the final press, stay at the slide position, re-centre with the integral feedback on, and feed
   directly at 5 mm/s without the -45 mm station, keeping the combed tips moving only forward along the axis.
2. Log which bodies the strands touch (add a ring/strand filtered sensor) to tell strand-strand contact from
   strand-ring contact.
3. If the strands repel each other, comb with the final press direction chosen so all four lie in one sector
   (the old SECTOR combs), or raise the strand damping further, e.g. 5e-2, and document it.
 `/workspace/yamlab_port/runs/fiber_bundling/out/{vef,eaf}*`, copies in `out/`)

| run | success | failed / reason | steps | sim s | wall s | notes |
|---|---|---|---|---|---|---|
| vef oracle | yes (2921) | - | 2922 | 97.4 | 48.7 | 3 comb presses; front +19.3 mm past the ring plane, axis offset 0.07 mm, strand max radius 14.6 / 15.4 mm, max bend 6.7 deg, gripper-strand force 0 |
| vef_replay1/2 | yes (2921) | - | 2922 | | 46 / 55 | bit-identical to vef states; hash chain 681f013a0b84964e... |
| vef_nop | no | - | 8990 | 299.7 | 123 | |
| vef_naive_nocomb | no | fiber_gripper_contact (step 1221) | 1222 | 40.7 | 23 | fanned strands hit the ring face and fold back onto the fingers |
| vef_naive_off12 | no | - (script end) | 3034 | 101.1 | 60 | combed, fed 12 mm off axis: jacket stops on the ring face, strands not through, bend 50 deg |
| eaf oracle | yes (3808) | - | 3809 | 127.0 | 69.6 | 5 comb presses; front +19.3 mm, axis offset 0.07 mm, strand max radius 9.7 / 8.0 / 10.5 mm, max bend 7.0 deg, force 0 |
| eaf_replay1/2 | yes (3808) | - | 3809 | | 56 / 62 | bit-identical; hash chain 2f0bacfc8a1cfaab... |
| eaf_nop | no | - | 8990 | 299.7 | 130 | |
| eaf_naive_nocomb | no | fiber_gripper_contact (step 1221) | 1222 | 40.7 | 19 | |
| eaf_naive_off12 | no | - (script end) | 3921 | 130.7 | 67 | jacket blocked |

Clearance (`tools/jacket_clearance.py`): while the jacket passes the ring plane its axis stays within 0.18 mm
(vef) / 0.16 mm (eaf) of the ring axis; minimum radial jacket-ring gap 1.297 / 1.318 mm of the nominal 1.479 mm,
so the jacket never touches the ring. A 3 mm off-axis feed still succeeded in an earlier test (the rounded tube
front funnels the jacket in and the friction grasp complies), hence the 12 mm naive offset.

Oracle phases: approach (collision-checked) -> grasp 110 mm behind the face, lift the trunk 35 mm out of the U
cradle, release -> regrasp 70 mm behind the face (tool pitch 45-60 deg, gripper target -0.0105, ~3 N) -> comb
loop (old stages(): press the strand farthest from the sheath axis against the ring's outer surface, slide off,
until all within 11.5 mm; d_press 31/30/29 mm; after the last press re-centre directly) -> feed along the ring
axis with an integral correction of the measured front point -> hold until the 0.5 s window latches.

## Re-layout (old table frame mm -> YAMLab world m)

`p_world = Rz(+90 deg) @ (p_table_mm / 1000) + (0.25, -0.01, 0.7517)`

i.e. `x_w = 0.25 - y_old/1000`, `y_w = x_old/1000 - 0.01`, `z_w = 0.7517 + z_old/1000`. Rigid transform of the whole
scene (terminal box, lead, cradle, trunk, strands, ring, ring mount); no part moved relative to another, no
length changed (the 830 mm slack lead is kept whole).

Why: the old scene spans 916 mm along the cable direction (terminal box far edge x = -509 mm to ring
outer edge x = +407 mm), more than the 70 cm table depth, so the cable now runs along world +y (across the
table): terminal box at y -0.52..-0.27 (in front of the right arm, x 0.57..0.75), U cradle at y 0.046, ring at
(0.50, 0.376, 0.9917), i.e. in front of the left arm. The trunk axis sits at x = 0.50 (measured YAM reach: a
pitched tool reaches x 0.41..0.57 over y 0.13..0.36 at the 0.9917 m axis height; a vertical tool does not
reach that height because joint4 hits its -90 deg limit above z ~0.955). The axis height (240 mm above the
table) is unchanged.

Resulting world positions (very_easy): ring centre (0.500, 0.3757, 0.9917), ring normal +y; trunk front face
(0.500, 0.2657, 0.9917); strand tips (0.4689 / 0.5311, 0.3390, 0.990 / 0.993); terminal root (gland) at
(0.660, -0.294, 0.9917).

## Physics model (measured)

- Cable = one fixed-base PhysX articulation, 47 links / 138 DOF (very_easy): root `terminal` (terminal box
  colliders + lead_00, welded as in the old MJCF), lead_01..20, trunk_00..05, fiber_SS_KK. Every bend is a
  free 3-DoF ball (USD D6, translations locked), zero stiffness, damping strand 2e-2 (old 2e-5, see deviations),
  trunk/lead 0.02 N m s/rad (old) and armature (1e-8 / 1e-6 kg m^2); Isaac reads them back exactly. Gravity disabled on all cable
  links (old model: gravity compensation 1.0). Density 1100 kg/m^3 (strand link 0.048 g, trunk link 27 g).
- Colliders: capsules (exact radii) for lead/trunk/strands; trunk_05 = sphere + 64-gon convex cylinder (flat
  front face, as the old cylinder geom); ring = 64 capsules r 4 mm on a 17.5 mm centreline (exact old compound;
  polygonal aperture 13.479 mm, radial clearance to the 12 mm jacket 1.479 mm). Contact offset 0.5 mm, rest
  offset 0 on cable and ring.
- Stability: at rest, max link drift 0.0006 mm over 5 s; 1090 physics steps/s cable-only, ~55-60 control
  steps/s with the robot (CPU, 1 env).
- Strand-gripper contact sensor (20 strand links x 6 gripper bodies, every substep) works: an early
  approach that swept the hand through the strands failed at once (0.093 N, latched).

## Intermediate very_easy evidence (run `ve9`, strand damping 2e-3, superseded by vef; vast `out/ve9*` only)

| run | success | failed / reason | steps | sim s | wall s | notes |
|---|---|---|---|---|---|---|
| ve9 oracle | yes (step 2851) | - | 2852 | 95.1 | 46.3 | final: front face +19.3 mm past the ring plane, front axis offset 0.08 mm, strand max radius 14.6 / 11.9 mm, max bend 6.5 deg, strand-gripper force 0 |
| ve9_replay1 / 2 | yes (step 2851) | - | 2852 | | 42 / 36 | open-loop replay of `actions.npy`; bit-identical to the oracle states and to each other (hash chain bf4d00cdfda5ead2...) |
| ve9_nop | no | - (time out) | 4490 | 149.7 | 60 | cable unchanged |
| ve9_naive_nocomb | no | fiber_gripper_contact (step 1219) | 1220 | 40.7 | 18 | feeding the fanned strands: they hit the ring face and fold back onto the fingers |
| ve9_naive_off12 | no | - (time out) | 2964 | 98.8 | 54 | combed, fed 12 mm off axis: jacket stops on the ring (front -4 mm), strands not through |

Key physics numbers: during the feed the jacket axis stays within 0.22 mm of the ring axis; minimum radial jacket-ring
gap at the ring plane 1.257 mm (nominal 1.479) -> no jacket-ring contact (`tools/jacket_clearance.py`). A 3 mm off-axis
feed still succeeded (the rounded tube front funnels the jacket in and the friction grasp complies; front offset 3.2 ->
0.9 mm), so the off-axis negative uses 12 mm. Grasp: friction only, gripper target -0.0105 (pads touch at -0.012, ~3 N).
Oracle phases: lift trunk out of the cradle (grasp 110 mm behind the face, +35 mm, release) -> regrasp 70 mm behind the
face (pitch 45-60 deg tool) -> comb loop (3 presses here: strand 0, 1, 0; d_press 31 mm) -> feed on the axis with an
integral correction of the measured front point -> hold until the 0.5 s window latches.

## Oracle log (very_easy)

- v1: joint-space move home -> pre-grasp swept the fingers through the strands -> latched strand-contact
  failure at step 90 (the fail check works). Fix: collision-checked approach (coarse gripper boxes vs
  cable spheres; home -> sampled mid -> ready in joint space, then Cartesian pre-grasp -> grasp).
- v5: grasp good (front-face radial offset 0.18 mm after closing). Combing failed: offsetting the sheath
  63 mm sideways while trunk_00..02 still lie in the U cradle (walls 2 mm above the jacket top, 4 mm
  side gap) jams; the hand lagged its command by up to 22 mm and the friction grasp slipped 30 mm; the
  strands were swept around the ring tube instead of combed. Fix (v6): first grasp the trunk just in
  front of the cradle, lift it 35 mm clear of the walls, let go, then regrasp behind the strand roots.

- v6/v7: strands drifted 30+ mm (in the trunk frame) while the arm held the jacket with an 8 mm squeeze, with
  no contact on any strand (net contact force 0). Cable-only and in-env tests with an external PD wrench show no
  drift, so it comes from the stiff gripper pinch through the reduced-coordinate chain. A gentle squeeze
  (target -0.0105) cut it to ~5 mm; strand joint damping 2e-3 instead of 2e-5 cut it further and made combing
  converge (v7b: tips 22.7 / 10.0 mm after one press each vs 54 / 39 mm in v7). More solver iterations (64/4)
  did not help.
- v8: + comb loop (old stages(): comb the farthest strand until all within 11.5 mm, at most 3 combs per strand)
  -> first success; ve9 = same with pre-reset state logging (final evaluated step kept in states.npz).

- ea1-ea3 (easier, damping 2e-3): each press combs the strands to 8-12 mm, but they creep apart again while the
  sheath moves or is held (no contact on any strand; e.g. 9.6/8.0/9.6 -> 16/16/18 mm after re-centring) and
  the feed then catches a strand. Strand damping 2e-2 (ea4) keeps them at 8-9 mm; very_easy also succeeds with it
  (ve11), so 2e-2 is the final value for both tiers. Final evidence runs: vef / eaf.

## Deviations from the old task

- Robot: YAM (left arm) instead of the old single Panda; no grasp weld (friction grasp only).
- Fixed base articulation root replaces the old fixed MJCF terminal body (same effect).
- Goal evaluated once per control step (30 Hz, interpolated crossings within a step as in the old
  advance_passage) instead of every physics tick; the strand-contact failure still covers every substep.
- PhysX default friction (0.5) on cable and ring (old MJCF geom friction 0.35).
- Strand joint damping 2e-2 N m s/rad instead of the old 2e-5 (PhysX-dependent, see v6/v7, ea3/ea4 below; still
  zero stiffness, passive). Trunk/lead damping unchanged (0.02).
- Episode length 300 s (YAMLab default 180 s; the easier oracle needs 127 s, very_easy 97 s).
- Oracle pre-step: the trunk is lifted out of the U cradle before combing (with the old weld grasp the arm just
  dragged it; a friction grasp slips instead).

## Blockers

None. Open: the video (lead renders with `render_on_rtx.sh`); tiers easy/medium/hard not attempted (out of scope);
easy+ has 4+ strands (67+ links) and denser fans.
