# Knot untying: the placement problem (design packet for pingyue)

**What we need from you:** two answers, as sketches or waypoint lists in the task frame defined below.

- **(a) A placement motion plan.** Given an untied rope lying mostly outside its goal strip, how should the robot lay it into the strip? Give grasp points (as arc length along the rope), lift heights, paths, releases, one hand or two, and the order of ropes a and b.
- **(b) Should the region or curb design change** so placement is legal and reasonable without making the task trivial? If so, which tiers does it apply to?

Agents will implement your answers. Everything you need is in this folder. Start with `viewer.html`: open it in a browser, drag to rotate, wheel to zoom, right-drag to pan. Then look at `figs/` and read this file. `params.json` holds every number.

---

## 1. The task: knot_untying (the redesign)

A rope lies on a table, tied into a knot around fixtures. Its start end (arc length s = 0) is clamped to the table under a staple and stays clamped. The robot must untie it, lay it inside a goal region, and let go.

**The goal predicate**, checked by the simulator every step, ends the episode in success once it has held for 0.5 s:

| term | rule |
|---|---|
| planar clear | In the top view, no crossings, overlaps, collapsed segments or exact fold-backs. Nonlocal centre-line segments must stay at least one rope diameter (8 mm) apart. Changing over/under order alone does not count. |
| on the table | Centre line no more than 1 mm below the table and no higher than 11 mm above it (one diameter + 3 mm). **A strand resting on the 4.5 cm curb fails this.** |
| in region | **Every** centre-line point of a rope lies inside its region polygon. |
| between ropes (hard) | The two ropes stay at least 8 mm apart in the top view. |
| quiet | Every point moves at most 1 mm/s, and at most 1 mm over the 0.5 s confirmation. |
| released | Grippers open, assisted grasp disengaged, at least 1 mm clearance between the rope and any moving robot part. |
| intact | Rope volume not inverted or collapsed. |

**Task frame** (all coordinates here): metres, z = 0 at the table top. +x points toward the right arm, -y is the front. A rope's arc length s runs from 0 at its clamp to L at its free end. Rope radius is 4 mm everywhere.

**Fixtures:**
- **Curb:** a 4.5 cm tall, 4 cm thick, 60-70 cm long wall along one long side of the goal strip.
- **Posts:** 16 cm tall cylinders, 1.1-1.2 cm radius. The knot is tied around them.
- **Clamps:** the staple plates holding each rope's start end. Each sits inside its rope's region near one end.

**Tiers** (instance names with lengths and regions; full geometry in `params.json`):

| tier | ropes (length) | goal region (x range, y range) | fixtures | crossings at start |
|---|---|---|---|---|
| very_easy | rope 1.63 m | none | clamp | 4 |
| easier_v8 / easier_loose | rope 1.79 / 1.97 m | back strip x -0.42..0.30, y 0.155..0.33 (0.72 x 0.175) | curb in front of the strip (y 0.115..0.155), 2 posts | 4 |
| easy_v8 / easy_loose / easy | rope 2.29 / 2.46 / 2.54 m | back strip x -0.43..0.32, y 0.155..0.31 | curb, 2 posts | 6 |
| medium_v81 / _b81 / _loose | rope 1.76 / 1.91 / 1.43 m | front-left box x -0.44..0.02, y -0.32..0.01 | N-S curb at x ~ -0.2 (y -0.09..0.31), post_eye (8 cm), post_back | 4-8 |
| hard_nostop | a 1.54 m, b 0.92 m | a: front strip x -0.44..0.30, y -0.33..-0.175; b: back strip x -0.30..0.42, y 0.17..0.32 | **front curb** x -0.28..0.32, y -0.175..-0.135 (on a's strip edge), 2 posts | 7 |
| hard | a 1.54 m, b 1.28 m | as hard_nostop | as hard_nostop | 10 |

Variants made today as "robot-access" tweaks: births and knots unchanged, only the fixtures or regions moved.
- `_ra`: hard_nostop's curb 2 cm further from the knot (y -0.195..-0.155) with strip a 2 cm lower. medium_loose with bigger loops and a thinner eye post.
- `_rw`: regions widened. Strips reach y 0.37 (back) or -0.37 (front) and are about 2 cm longer each way. medium's box reaches x 0.06 and y -0.37.

**Every tier except very_easy has a goal region.** Only very_easy is solved end to end so far.

## 2. The robot

- **Arms:** bimanual ALOHA, two 6-DOF arms with bases at (-0.469, -0.019) (left) and (+0.469, -0.019) (right). Control is 40 Hz absolute joint targets. Joint speed is capped at 3.14 rad/s per joint; a faster command is slowed, never failed.
- **Gripper:** parallel jaws. They open up to 30 mm (the "pre-shape" / approach width), open 16 mm on release, and hold the 8 mm rope at an 8 mm gap. Every pinch the oracle makes is vertical (top-down), with the fingers closing across the rope. The jaw yaw is therefore set by the rope's local direction at the pinch. Two grippers cannot pinch closer than about 12 cm apart along a rope, because their finger bars clash.
- **Reach** (planar distance from an arm's base at which a vertical pinch is still solvable): 0.585 m up to 3 cm above the table, 0.55 m up to 11 cm, 0.50 m higher. The figures and the viewer draw both rings. The middle of a back strip's far edge is at the limit for both arms; for example (0, 0.30) is 0.567 m from either base.
- **Assisted grasp** (`contact_weld_v1`): when both fingers touch one rope link and the jaws close, a weld binds that link to the pads. The weld lets go if:
  - the link drifts more than 2.5 cm from the pads,
  - the link turns more than 0.15 rad relative to the pads,
  - or the jaws open.
  - It holds about 1-3 N steadily, and briefly 6-8 N.
  - In practice: dragging a long rope over the curb faster than about 6 cm/s, or **turning a held piece by about 0.9 rad** (to align it with a target direction), loses the grip.
- **The rope:** a MuJoCo chain of about 340 to 440 links. It drags on the table with friction and catches on the curb's top edge and on posts.

## 3. What the oracle does today, and where it fails

**Stage 1, untie: largely works now.** The oracle repeats these moves until no crossing is left:
- **delete:** pin the over-strand, then pull the free-end side out from under it, near the crossing.
- **clear_tail:** lay the freed tail aside.
- **lift_over_post:** where needed, lift a strand over a post.

Many runs on the final instances now reach 0 crossings: hard_nostop in more than 7 runs, easier_v8, easier_loose, and others. A run takes 300-600 s of simulated time, 12-24 thousand control rows.

**Stage 2, placement: fails every time so far.** Two finishes exist today:
1. **Region layout.** A fixed serpentine path inside the region (red dotted in the figures) is laid hand over hand from the clamp outward. Stations 14 cm apart are each pinched, lifted 5-8 cm, carried to their point on the path, and lowered, with the other hand pinning the previous station.
2. **Fix-up.** Each contiguous run of rope outside the region is pinched at its middle and carried to the nearest point of the shrunk region box, up to 4 passes.

**The numbers at untied states:**
- hard_nostop (the `hnnp` and `hnc` lines on the original curb):
  - Right after untying, rope **a is 91-94 % outside** its front strip. Most of it lies north of the curb, in the middle of the table. Rope **b is 24 % outside**.
  - Both ropes are planar clear and on the table, and they are 30-45 mm apart. **The only failing term is in-region.**
  - The fix-up brings **b to 0-2.7 % outside, with no crossing.** For **a** it ends **62-65 % outside, re-crossed** (1-4 crossings), with a strand **lying on the curb at z = 36 mm**.
- easier_v8, untied: rope 52 % outside. The fix-up made it 45 % with 2 crossings. The region layout re-tangled it from 0 to 5 crossings at its first placement.
- The region layout re-tangled hard_nostop from 0 to 3 crossings in several runs.

**Why, as far as we can tell:**
- The layout path runs along the region's **near side first**, the side facing where the loose rope lies. Every later leg is further in, so the rest of the rope must be dragged **across the placed leg** to reach it.
- Long outside runs dragged by one point sweep across the rope's own body.
- The curb is 4.5 cm tall. Rope carried low snags on it and is left lying on top, which breaks the on-table term.
- Reach and grip limits:
  - The strip's far edge is at the reach limit.
  - A held piece cannot be turned much, because the weld releases at 0.15 rad of relative turn.
  - A pinch close to the clamp cannot be lifted high: the clamped strand goes taut and the weld drops at about 7.8 N.

**What we are trying right now** (agents, today; no result yet on untied ropes):
1. A serpentine whose **first leg runs along the far side**, each next leg one gap nearer, so the loose rope never has to cross a placed leg. Green dashed in the figures.
2. **Two-hand lays per leg.** Pinch the leg's two end stations, lift 3 cm (9 cm where a hand's path crosses the curb), carry both together in straight lines, lower, and release at the approach width.
3. Stations chosen so the pinch's own yaw already holds at the target, so no wrist turn is needed while holding.
4. Ropes under 35 % outside, such as b, get only the fix-up.

## 4. The pictures and data

- `viewer.html`: interactive 3D view of the snapshots with toggles: ropes, regions, curb/posts/clamps, reach rings, the far-side-first goal shape, and today's layout path. A height slider exaggerates z. Three.js loads from cdnjs; the data is inlined, nothing is uploaded.
- `figs/<snapshot>_{top,oblique,side}.png`:
  - **top:** plan view with the goal regions (green), curb, posts, clamps (black square = clamped end), arm bases and reach rings, the rope now (solid), one feasible goal shape (green dashed), and today's layout path (red dotted).
  - **oblique:** 3D view with heights x3.
  - **side:** rope height against y, with the curb and the 11 mm on-table line.
- Snapshots:
  - `hard_nostop_untied`: a real untied state on the original curb, 6 s after the last deletion. It comes from a different run than the 91 % numbers above; here a is 60 % outside and b 23 %, and a strand crosses the curb top at about 4.9 cm.
  - `hard_nostop_birth` and `easier_v8_birth`: the start states (knotted), to show the scenes.
  - An **easier_v8 untied** snapshot (the state our placement lab starts from) will be added here as `easier_v8_untied` when it is captured (by ~14:45 today).
- `params.json`: frame, goal tolerances, robot, gripper and grasp limits, and all tiers' ropes, regions and fixtures.
- `data/snapshots.json`: each snapshot's rope centre lines (task-frame xyz, clamped end first), plus today's layout paths. `data/plans.json` holds our current far-side-first shapes.

## 5. The questions, in detail

**(a) Placement motion plan.** Starting from an untied rope (use `hard_nostop_untied`, and `easier_v8_untied` when it lands), how should the robot get every centre-line point into the strip, flat on the table (at most 11 mm up, so not on the curb), with no crossing, and let go?
- Which points to grasp (arc length s from the clamp), with one or two hands.
- Lift heights. The curb is 4.5 cm. Reach shrinks above 3 cm. A held piece can't be turned more than about 0.15 rad.
- The path for each hand, and where to lower and release.
- For hard: the order of ropes a and b, and whether b needs anything beyond the fix-up.
- What the final shape inside the strip should be. A 1.54 m rope in a 0.74 x 0.155 m strip needs about three legs. Is a U, an S, or something else better?

**(b) Region and curb design.**
- Is placement as posed legal and reasonable?
  - legal: a fitting final shape exists;
  - reasonable: a bimanual robot with these limits can do it without heroics.
- If not, what would you change, and for which tiers? For example:
  - strip size or position;
  - which side the curb is on, its height, or a gap in it;
  - the clamp position relative to the strip;
  - whether a region is needed at all for the single-rope tiers.
- The change must not make the task trivial. The rope must still be untied, and the region should still demand a deliberate placement.

**Answer format:** a sketch in the task frame, or a waypoint list like:

```json
[{"op": "grasp", "hand": "left", "rope": "a", "s": 0.62},
 {"op": "grasp", "hand": "right", "rope": "a", "s": 1.10},
 {"op": "lift", "hands": ["left", "right"], "dz": 0.03},
 {"op": "move", "to": {"left": [-0.20, -0.30, 0.03], "right": [0.25, -0.30, 0.03]}, "speed": 0.05},
 {"op": "move", "to": {"left": [-0.20, -0.30, 0.005], "right": [0.25, -0.30, 0.005]}, "speed": 0.04},
 {"op": "release", "hands": ["left", "right"], "width": 0.03}]
```

The fields:
- `s`: arc length from the clamped end.
- `move`: the pads' contact point, in metres, with z above the table. All hands listed move together in straight lines.
- A waypoint list for a snapshot can be written against `data/snapshots.json`.

## 6. Running a waypoint list yourself (optional)

Our runs live on a shared GPU box and a cluster. If you'd rather not touch them, just send the list and an agent will run it. For reference:
- The placement lab (`scripts/robotangle/redesign/knot_untying/robot/place_lab.py` in the repo) keeps a process sitting at an untied snapshot.
- A try is a JSON file dropped into its queue: `{"func": "waypoints", "params": {"ops": [...]}}`, run with the strategy file `topogym/planning/knot_untying/redesign/robot_place.py`.
- It comes back in minutes per lift-and-carry with the goal reading, the crossings, the rope's final plan view, and all control rows. A successful list is a complete recording.

Starting a fresh lab costs a 2-3 h replay of the untie prefix, so we keep labs alive for these snapshots: hard_nostop (`hn`, `hn_b`, `hn_c`, `hn2`) and easier_v8 (`e9`, `e9_b`, `e9_c`).
