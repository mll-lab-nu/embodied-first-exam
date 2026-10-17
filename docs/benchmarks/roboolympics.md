# RoboOlympics

Fifty single-robot sports for a humanoid, in their official settings: one Unitree G1 or H1-2 sprints 50 m, hurdles,
jumps, takes a penalty against a keeper, serves over a 2.43 m net, shoots at a 3.05 m ring, returns a real table-tennis
serve, puts a 7.26 kg shot, bowls for a strike, swings a giant on the high bar. A referee decides from the simulator's
state whether it did the sport: events that must happen in order, geometric conditions, which body part may touch
what. Nothing is scaled to the robot and nothing is softened so that a reference solution exists: the benchmark is
meant to find the ceiling of coding agents, and most of its tasks have no known solution. The agent may use the
robot's built-in walking (and, on the G1, running) policy, drive every joint itself, and, unlike in every other
benchmark here, search for and download public tools and pretrained controllers.

**Name.** Until 2026-10-14 this benchmark was RoboFunOlympics (`robofunolympics-<family>-i00-<mode>`,
`scripts/robofunolympics/`); the owner renamed it RoboOlympics (board 0107, E7). The tasks, instances, referees and
oracles are the same; the image keeps its name (`eai-robofunolympics`), as do the internal module names (`rfo/`,
`rcb_rfo.py`). The earlier RoboOlympics tasks of this repository (three standard-realtime matches on its 2.3 adapter,
`roboolympics-{tabletennis,badminton,airhockey}-match-i00-standard-realtime`, `scripts/roboolympics/` at the time,
image `eai-olympiad:0.2.0`) were removed on the same day.

**Two parts.** (1) The 50 single-robot sports families above and below, generated here (`scripts/roboolympics/`,
privileged and standard). (2) Eight tasks RoboOlympics exports itself with its own service inside (PROTOCOL §4c):
matches against a scripted opponent in standard-realtime mode and two skill-engineering tasks in standard mode, listed in
`scripts/roboolympics/exported.toml` and described in "Tasks exported by RoboOlympics" at the end of this page. The two
parts never share a family name: the families here are dashed English event names (`table-tennis-return`,
`penalty-kick`), the exported tasks are the sport's RoboOlympics id and a format (`tabletennis-match`,
`soccerssl-match`, `tabletennis-hitskill`, `badminton-actskill`); a new family here may not take a `<sport>-match` or
`<sport>-<x>skill` name, and `gen_tasks.py check` fails a name that is both rendered and exported. The
standard-realtime twins of part (1)'s dynamic families (board 0112) are `roboolympics-<family>-i00-standard-realtime`
and cannot meet part (2)'s names either.

| | |
|---|---|
| origin | built here on the simulator of [RoboOlympics](https://github.com/CHIGUI0/roboolympics) (MIT; private): its robot library `bodies/` (the Unitree G1 at revision g1-4 and the Unitree H1-2 at h1-4, the one limit and servo path, the joint-group arbiter, and, since image 0.2.0, the G1's optional FALCON and AGILE walking policies) and its athletics running policy, commit `7df999b`, unchanged, in the image. Parts of single families come from RoboOlympics' sports (the athletics start procedure and hurdle, the bowling lane and oil zones, the tennis ball's fitted lift, DeepMind's system-identified table-tennis ball and table and the serve library). The list of sports follows the owner's survey of humanoid sports tasks (2026-10-11) |
| simulator | MuJoCo 3.3.7 on the CPU (1 ms physics, 10 ms control), OSMesa rendering, no GPU; sunlight with shadows, a painted sky, procedural materials on the venues' surfaces, patterned balls, and round each venue perimeter boards, stepped grandstands with a seated crowd, a roof, floodlight towers, a scoreboard and a line of trees, merged into one mesh per colour (`shared/rfo/looks.py`, after the venues of RoboOlympics' throws and beach volleyball: looks only, no effect on the physics or the state hash; owner, 2026-10-12: the first scenes looked like cartoons; 2026-10-13: adopt RoboOlympics' scenery); air at sea-level density (drag and Magnus lift on balls and implements); `simulator = "mujoco"` |
| robots | `unitree-g1` (1.32 m, 33 kg, 29 joints; three walking policies and a running policy) and `unitree-h1-2` (1.78 m, 67 kg, 27 joints; a walking policy) where the official venue needs an adult-size body; real joint, speed and torque limits, motor torque-speed curves (the H1-2's are estimates), self-collision; fist pads with a switchable grip |
| actions | views of one sim row per control step: `stand`, `walk`, `joints`, `lowcmd` (Unitree's LowCmd: q, dq, tau, kp, kd per joint), and on the G1 `run`, `run_arms`; every row ends with `grip_left`, `grip_right` |
| score | the referee's verdict: every stage latched in order, no rule broken, within the time limit; binary. `progress` (stages reached) and the family's metrics (a distance, a speed, a count) are reported beside it |
| tasks | 50 families × 2 modes: `tasks/roboolympics-<family>-i00-privileged` and `-standard` (`eai-standard/2.1`), 100 task directories. No standard-realtime mode yet (owner, 2026-10-11). Plus the 8 tasks RoboOlympics exports itself (below), 100 task directories;, the 13 dynamic families' `-standard-realtime` twins (`eai-standard/2.3`, since 2026-10-14), 113 in all |
| image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.1.0`, | image | `ghcr.io/mll-lab-nu/eai-robofunolympics:0.2.1` (0.2.1 = 0.2.0 + libglvnd's EGL loader, the NVIDIA EGL manifest, for the realtime twins' GPU rendering) (`images/robofunolympics/`, about 600 MB) |
| generator | `scripts/roboolympics/gen_tasks.py render` / `check` from `families.json`, `instances/`, `shared/`, `templates/`, `oracles/`; a family is one module, `shared/rfo/tasks/<family>.py` (`scripts/roboolympics/AUTHORING.md`, `FAMILIES.md`) |
| oracle | full on the families that have a real controller in the official setting, none on the rest (table below), with a referee test and human review |
| agent budget | 7200 s in both modes (each task's own `[agent] timeout_sec`; owner, 2026-10-12; PROTOCOL D8: the tasks ask the agent to find, download and adapt controllers, or to build one, which an hour does not hold; results are grouped by this budget); standard mode: 50 resets, the last attempt graded (owner, 2026-10-12) |
| network | open (owner, 2026-10-11): PROTOCOL §2.11 exception, below |

## Owner decisions (2026-10-11) and what they made

| decision | what follows from it |
|---|---|
| 50 tasks, one robot each, each with a success check; an oracle where there is one, none otherwise | `oracle = "full"` only where a real controller succeeds in the official setting, `"none"` + human review elsewhere (PROTOCOL D2, §2.7); every family has a referee test with a positive example and negative controls |
| both modes | every family as `-privileged` and `-standard` on one frozen instance |
| the agent may go online and download ready-made policies, and is encouraged to look for tools | open egress and the benchmark's own `## External material` paragraph (PROTOCOL §2.11 exception); the action interface takes what public humanoid controllers produce: Unitree's SDK joint order, `lowcmd` rows with per-joint gains and feed-forward torques at 100 Hz |
| no standard-realtime mode for now | none generated; the adapter is the `rcb_service.Sim` contract, which `rcb_realtime.py` runs unchanged, should the mode be added |
| the simulator is RoboOlympics' | the image holds RoboOlympics' robot library and running policy unchanged (`images/robofunolympics/roboolympics/SOURCE.md`, sha256 manifest); the venues, the action layer and the referees are this benchmark's own code, in the task directories |
| **real settings, not an easy one** (after the first version, whose venues and success lines were scaled to the G1 so that reference solutions existed) | official rule-book dimensions, equipment masses and ball physics in every family; a family names its rule book and lists each deviation with its reason (RoboOlympics' convention), and a deviation is never "easier"; a success line is the rule book's (a goal, a legal serve, a strike, a cleared bar) or a named human school / club mark, never what a controller reaches |
| all humanoid; the bigger H1-2 where the G1 cannot reach the official size | `Task.robot`; 20 families on the G1, 30 on the H1-2 |
| single actions, not matches | one attempt of one skill per episode; a feeder, a server or a keeper is scripted and deterministic |
| 2026-10-12: standard reset budget 50; agent budget 2 h; the track events are the indoor 50 m and 50 m hurdles (four hurdles), not 100 m and 110 m: "we are not the Olympics in full, we show what a robot can do" | `RESET_BUDGET` and `CUTOFF_SEC` in `gen_tasks.py`; `sprint.py`, `hurdles.py`. Where an official event is long only by repetition, the family takes its shortest official form |
| 2026-10-13: every task keeps the 2-hour limit; "pre-install frameworks like FALCON and AGILE for the model" (they are released weights, no training needed); "put them all in, the H1 may use them too"; adopt RoboOlympics' scenery ("pingyue's backgrounds are very good") | image 0.2.0 with FALCON's and AGILE's G1 policies (from RoboOlympics' robot library, unchanged, with their licences), the `walk_falcon` / `walk_agile` action types on the G1; on the H1-2 the G1 policies were tried and do not walk it (reported, not offered); the grandstands of `looks.py` rebuilt after RoboOlympics' venues |
| 2026-10-13: "use pingyue's method" (RoboOlympics' throws: whole-body key poses searched offline by CMA-ES) for reference solutions | `search_technique.py` (offline, not run by CI): reference solutions for `shot-put`, `discus`, `javelin`, `volleyball-serve`, `volleyball-bump` and `volleyball-set` (the last two: arm key poses on the walking policy, the bump after a walk), each open loop on its frozen start |

<!-- families:begin -->
## The 50 families

12 with a reference controller (`oracle = "full"`), 38 without (`oracle = "none"`, human review). Every family's rule book, its deviations and every number are in its task's instruction and README; the stages are the events its referee requires, in order.

| # | family | robot | task | rule book | stages | oracle (success after) |
|---|---|---|---|---|---|---|
| | **Track and jumps** | | | | | |
| 1 | `sprint` | G1 | Run the 50 m: wait for the starter's gun, then sprint down your lane until your torso reaches the finish line. | World Athletics Competition and Technical Rules, 2024 edition | start → finish | full: 19.59 s of 34.2 s |
| 2 | `hurdles` | H1-2 | Run the 50 m hurdles: go over all four hurdles in your lane, never beside one or under its top, and bring your torso to the finish line. | World Athletics Competition and Technical Rules, 2024 edition | hurdle 1 → hurdle 2 → hurdle 3 → hurdle 4 → finish | none |
| 3 | `shuttle-run` | G1 | Run the 4 x 10 m shuttle: to the far line, back to the start line, to the far line again and back through the start line, putting a foot on the ground beyond the line at each turn, as fast as you can. | The 4 x 10 m shuttle run of school fitness test batteries (the speed-agility test of the ALPHA-Fitness battery) | turn 1 → turn 2 → turn 3 → finish | none |
| 4 | `slalom` | G1 | Run the Illinois agility course: up the left side and round the far-left cone, back to the centre cone on the start line, weave up through the four centre cones and back down, up the right side and round the far-right cone, and back over the finish line, without touching a cone. | The Illinois Agility Test (Getchell 1979; the standard field test of agility) | far-left cone → bottom cone, first time → up 1-2 → up 2-3 → up 3-4 → top cone → down 3-4 → down 2-3 → down 1-2 → bottom cone, second time → far-right cone → finish | none |
| 5 | `high-jump` | H1-2 | Do a high jump: approach the bar, take off from one foot, go over the bar between the uprights without knocking it off its supports, and come down on the landing mat. | World Athletics Competition and Technical Rules, 2024 edition | take-off → clearance → bar stays | none |
| 6 | `long-jump` | G1 | Do a long jump: run up, take off behind the take-off line, fly over the metre of runway beyond it and land in the sand pit. | World Athletics Competition and Technical Rules, 2024 edition | take-off → landing | none |
| 7 | `standing-long-jump` | G1 | Do a standing long jump: from a standstill behind the take-off line, take off from both feet without a step, land on your feet at least your own height beyond the line, and stand. | The standing long jump (standing broad jump) of school and club fitness test batteries (Eurofit, ALPHA-Fitness, the Chinese National Student Physical Health Standard) | take-off → landing → stand | none |
| 8 | `triple-jump` | G1 | Do a triple jump: run up, hop from behind the take-off line and land on the same foot, step onto the other foot, and jump from it into the sand pit. | World Athletics Competition and Technical Rules, 2024 edition | hop → step → jump → landing | none |
| 9 | `vertical-jump` | G1 | Do a vertical jump: from a standstill, jump off both feet without a step, touch the vane above you with a hand at the top of the jump, land on your feet and stand. | The Sargent jump (the jump-and-reach vertical jump test of school and club fitness batteries; Sargent 1921) | take-off → touch → landing → stand | none |
| 10 | `pole-vault` | H1-2 | Vault over the bar with the pole you carry: plant its tip in the box, leave the ground hanging on it, go over the bar between the uprights and come down on the mat, with the bar still on its pegs. | World Athletics Competition and Technical Rules, 2024 edition | plant → take-off → clearance → bar stays | none |
| | **Football and volleyball** | | | | | |
| 11 | `penalty-kick` | G1 | Take a penalty kick: with one kick of a foot, send the ball that lies on the penalty mark into the official goal 11 m away, past the goalkeeper dummy. | IFAB Laws of the Game 2025/26 | kick → goal | none |
| 12 | `dribble-slalom` | G1 | Dribble the football through the slalom: out through the six cones, round the last one and back through them over the start line, keeping the ball within 2 m and touching no cone. | The slalom dribble of football skill tests (a line of cones, out through them, round the last and back through them, against the clock); it is a drill, not an event of the Laws | out 1 → out 2 → out 3 → out 4 → out 5 → out 6 → back 6 → back 5 → back 4 → back 3 → back 2 → back 1 → finish | none |
| 13 | `trap-ball` | H1-2 | Trap the pass: take the football that is passed along the ground past you with a foot, and bring it to rest within a metre of you inside three seconds. | IFAB Laws of the Game 2025/26 | first touch → control | none |
| 14 | `volley-shot` | H1-2 | Volley the cross: strike the football that is crossed to you from the wing with a foot before it touches the ground, into the official goal 11 m away, past the goalkeeper dummy. | IFAB Laws of the Game 2025/26 | volley → goal | none |
| 15 | `juggling` | G1 | Juggle the football: drop it from your hand and keep it in the air for ten touches in a row with your feet, legs or head, without it touching the ground or a hand again. | Keepie-uppie (ball juggling), the football skill | touch 1 → touch 2 → touch 3 → touch 4 → touch 5 → touch 6 → touch 7 → touch 8 → touch 9 → touch 10 | none |
| 16 | `header` | H1-2 | Head the cross: meet the football that is crossed to you from the wing with your head and send it into the official goal 5.5 m away, past the goalkeeper dummy. | IFAB Laws of the Game 2025/26 | header → goal | none |
| 17 | `volleyball-bump` | H1-2 | Receive the serve: pass the volleyball that is served over the net to you with your forearms, in one contact, above net height and into the setter's target at the net. | FIVB Official Volleyball Rules 2025-2028 | pass → above the net height → in the target | full: 5.81 s of 10 s |
| 18 | `volleyball-set` | H1-2 | Set the pass: with one overhead contact of your hands, send the volleyball that comes down above you at least a metre above the net and into the outside hitter's target along the net. | FIVB Official Volleyball Rules 2025-2028 | set → above the net → in the target | full: 5.87 s of 10 s |
| 19 | `volleyball-serve` | H1-2 | Serve the volleyball: from behind the end line, toss it out of your left hand and hit it with one hand or arm over the net into the opponent's court. | FIVB Official Volleyball Rules 2025-2028 | toss → hit → over the net → in the court | full: 3.28 s of 12 s |
| 20 | `volleyball-spike` | H1-2 | Spike the set: jump and strike the volleyball that comes down near the net with a hand, above the height of the net, down into the opponent's court, and land on your feet without touching the net. | FIVB Official Volleyball Rules 2025-2028 | spike → over the net → in the court → landing | none |
| | **Basketball and rackets** | | | | | |
| 21 | `free-throw` | H1-2 | Shoot a free throw: from behind the free-throw line, throw the basketball in your right hand so that it enters the basket from above. | FIBA Official Basketball Rules 2024 | release → through the ring | none |
| 22 | `catch-and-shoot` | H1-2 | Catch and shoot: catch the chest pass that comes to you from the left wing, then shoot from where you stand so that the ball enters the basket from above. | FIBA Official Basketball Rules 2024 | catch → release → through the ring | none |
| 23 | `layup` | H1-2 | Make a layup: with the basketball in your right hand take at most two steps towards the basket, jump, and let go of the ball in the air close to the ring so that it enters the basket from above. | FIBA Official Basketball Rules 2024 | approach → release in the air → through the ring | none |
| 24 | `dunk` | H1-2 | Dunk the basketball in your right hand: jump, force it down through the ring from above with your hand on it, and land on your feet. | FIBA Official Basketball Rules 2024 | dunk → stand | none |
| 25 | `basketball-dribble` | H1-2 | Dribble the basketball in your right hand from the end line across the centre line, 14 m up the court, without a dribbling or a travelling violation. | FIBA Official Basketball Rules 2024 | dribble → past the free-throw line → in the frontcourt | none |
| 26 | `tennis-return` | H1-2 | Return the serve: after the tennis ball has bounced once in your service box, hit it with the racket on your right hand back over the net so that it lands in the singles court on the far side. | ITF Rules of Tennis 2024 | bounce → racket → over the net → in | none |
| 27 | `tennis-serve` | H1-2 | Serve: from behind your baseline, release the tennis ball in your left hand, strike it with the racket on your right hand before it reaches the ground, and send it over the net into the service box diagonally opposite. | ITF Rules of Tennis 2024 | toss → strike → over the net → in | none |
| 28 | `table-tennis-return` | G1 | Return the service: after the table tennis ball has bounced once on your court, strike it with the paddle on your right hand so that it touches the opponent's court. | ITTF Handbook 2024, The Laws of Table Tennis | bounce → strike → opponent's court | none |
| 29 | `paddle-bounce` | G1 | Keep the table tennis ball that is dropped in front of you bouncing on the paddle in your right hand: 20 bounces in a row, each back up to the height the ball was dropped from. | ITTF Handbook 2024, The Laws of Table Tennis, for the equipment | bounce 1 → bounce 2 → bounce 3 → bounce 4 → bounce 5 → bounce 6 → bounce 7 → bounce 8 → bounce 9 → bounce 10 → bounce 11 → bounce 12 → bounce 13 → bounce 14 → bounce 15 → bounce 16 → bounce 17 → bounce 18 → bounce 19 → bounce 20 | full: 14.53 s of 20 s |
| 30 | `golf-putt` | G1 | Hole the 3.0 m putt: with one stroke of the putter in your right hand, roll the golf ball that lies on the green into the hole. | The Rules of Golf (R&A / USGA, 2023) | stroke → holed | full: 17.18 s of 30 s |
| | **Throwing, catching, striking** | | | | | |
| 31 | `javelin` | H1-2 | Throw the javelin in your right hand over the shoulder from behind the arc so that its head strikes the ground first, inside the sector, at least 20.0 m from the arc, then leave the runway behind the arc and stand. | World Athletics Competition and Technical Rules 2024 | release → landing → exit | full: 15.33 s of 60 s |
| 32 | `shot-put` | H1-2 | Put the shot that your right hand holds at your neck, from the shoulder with that hand alone, so that it lands inside the sector at least 6.0 m from the circle, then leave the circle from its rear half and stand. | World Athletics Competition and Technical Rules 2024 | release → landing → exit | full: 6.08 s of 60 s |
| 33 | `discus` | H1-2 | Throw the discus in your right hand from inside the circle so that it lands inside the sector at least 15.0 m from the circle, then leave the circle from its rear half and stand. | World Athletics Competition and Technical Rules 2024 | release → landing → exit | full: 8.48 s of 60 s |
| 34 | `pitch-target` | H1-2 | Pitch a strike: from the pitcher's plate on the mound, with a foot on the plate, throw the baseball in your right hand through the strike zone over home plate, on the fly. | Official Baseball Rules (MLB, 2024 edition) | release → strike | none |
| 35 | `bowling` | H1-2 | Bowl a strike: from behind the foul line, deliver the ball that hangs from your right hand down the lane so that all ten pins are knocked down. | USBC Playing Rules 2024-2025 and USBC Equipment Specifications | delivery → pins → strike | none |
| 36 | `catch` | H1-2 | Catch the fly ball: grip the baseball with a hand before it touches the ground or your body, and keep hold of it. | Official Baseball Rules (MLB, 2024 edition) | catch → hold | none |
| 37 | `juggle-three` | G1 | Juggle three balls in a cascade: throw each ball from one hand in an arc to the other, the hands in turn, until 10 catches have been made in a row. | No rule book | first catch → half way → ten catches | none |
| 38 | `wall-ball` | H1-2 | Throw the tennis ball in your right hand at the target circle on the wall and catch the rebound with a hand before it touches the ground, and keep hold of it. | No rule book | release → target → catch → hold | none |
| 39 | `boxing` | H1-2 | Punch the heavy bag once with the knuckles of your right fist, on the marked band, hard enough to give it 12.0 N s, then bring the fist back to your guard and stand. | No rule book for a bag. The punch is judged by the scoring criterion of Olympic-style boxing | strike → guard | full: 4.04 s of 15 s |
| 40 | `kick-target` | H1-2 | Kick the heavy bag once with your right foot or shin, on the marked band at trunk height, hard enough to give it 20.0 N s, then stand on both feet. | No rule book for a bag. The kick is judged by the scoring criterion of World Taekwondo's Competition Rules (a valid point is a kick delivered with a part of the foot below the ankle bone to the trunk protector, with the required level of impact) and of kickboxing (the shin also strikes), applied to a standard heavy bag (30 kg, 1.2 m, on a chain) | strike → stand | none |
| | **Parkour, apparatus, balance** | | | | | |
| 41 | `balance-beam` | G1 | Walk along the balance beam from the end you stand on to the other end and stand there, without anything touching the floor. | FIG Apparatus Norms (Fédération Internationale de Gymnastique), women's artistic gymnastics, balance beam | half way → far end → stand | none |
| 42 | `steeplechase` | H1-2 | Go over the steeplechase hurdle in front of you and over or through the water pit behind it, get out beyond the pit's far edge and stand on your feet. | World Athletics Competition and Technical Rules 2024, Technical Rule 23 (steeplechase races) | hurdle → out of the water jump → stand | none |
| 43 | `box-jump` | H1-2 | Jump from the floor onto the 0.61 m box in front of you with a two-foot take-off, land on its top with both feet, and stand up straight on it. | CrossFit's box jump movement standard | take-off → landing → stand | none |
| 44 | `vault` | H1-2 | Vault over the vault table at the end of the run-up: go over it with only your hands touching it, land on your feet on the landing mat and stand. | FIG Apparatus Norms (men's vault) | hands on the table → over the table → landing → stand | none |
| 45 | `backflip` | G1 | Do a standing backflip: jump, turn backwards through a full turn in the air, land on your feet and stand. | FIG Code of Points, floor exercise | take-off → full turn → landing → stand | none |
| 46 | `crawl` | G1 | Get under the low wires in front of you and crawl the whole course until your whole body is beyond the last wire, without touching a wire. | No federation rule book | under the first wire → half way → through | none |
| 47 | `high-bar-swing` | G1 | Hanging from the high bar by both hands, do one giant swing: take your extended body in a full circle around the bar, without letting go. | FIG Apparatus Norms, men's artistic gymnastics, horizontal bar | over the top → full circle | full: 23.62 s of 60 s |
| 48 | `toes-to-bar` | G1 | Hanging from the high bar by both hands, do five toes-to-bar: bring both feet up to touch the bar between your hands, and come back to the full hang each time, without letting go. | CrossFit Games movement standard, toes-to-bar | rep 1 → rep 2 → rep 3 → rep 4 → rep 5 | full: 7.78 s of 60 s |
| 49 | `clean-and-jerk` | H1-2 | Clean and jerk the barbell: lift it from the platform to your shoulders, then to locked arms overhead, and hold it there motionless until the down signal. | IWF Technical and Competition Rules & Regulations (International Weightlifting Federation; quoted from memory of the 2020s editions) | lift-off → clean → overhead → down signal | none |
| 50 | `balance-board` | G1 | Stay balanced on the roller board for 30.0 s: neither end of the deck nor any part of you may touch the floor. | No federation rule book | 10 s → 20 s → 30 s | none |
<!-- families:end -->

## The robot and its actions

One control step is 10 ms: ten physics steps of 1 ms, as in RoboOlympics. Every joint target is clipped into the joint's
range and moves at most the joint's speed limit per step; every motor torque goes through the robot library's output
stage (the motor's torque-speed curve, then its torque limit). A sim row is `[mode, vx, vy, wz, q × n, dq × n,
tau × n, kp × n, kd × n, grip_left, grip_right]` with n the robot's joint count (G1: 29 joints, 151 floats; H1-2: 27
joints, 141 floats); the list of sim rows is the whole record of an episode, and an action type is a view of it:

| type | the row | who drives the joints |
|---|---|---|
| `stand` | waist + arm joint targets (G1: 3 + 14; H1-2: 1 + 14) | the platform holds the legs in the stance (stand gains, gravity support); no balance controller |
| `walk` | vx, vy, wz + waist + arms | Unitree's own walking policy (unitree_rl_gym's pretrained G1 or H1-2 policy, 50 Hz) on the legs, through RoboOlympics' arbiter (the handover blend and the stability wait included): about 0.6 m/s on the G1, 0.7 m/s on the H1-2 |
| `walk_falcon`, `walk_agile` (G1 only) | as `walk` | the G1's optional walking policies of RoboOlympics' robot library: numpy ports of the released FALCON G1 policy (LeCAR-Lab, MIT; trained with arm motions and hand forces; it also adds a small wrist residual) and of NVIDIA WBC-AGILE's G1 velocity-height policy (Apache-2.0; trained while the arms and the waist moved), 50 Hz, their 12 leg targets on their own leg gains; the waist and the arms are the agent's. Both hold still and track the command better than `walk` while the arms move or carry something (RoboOlympics' comparison); AGILE barely turns on the spot below about 0.7 rad/s. They take the legs at once (no blend); straight to `stand` from them usually falls (through `walk` at rest it does not). On the H1-2 (joints matched by name) they keep the robot upright but do not walk it, so the H1-2 does not offer them |
| `run` (G1 only) | vx, vy, wz | RoboOlympics' athletics running policy (C1801SYQ/g1_running, Apache-2.0) on all 29 joints: stable to about 4 m/s. The H1-2 has no running policy |
| `run_arms` (G1 only) | vx, vy, wz + arms 14 | the running policy on the legs and the waist |
| `joints` | n joint targets | the agent; default gains |
| `lowcmd` | n × (q, dq, tau, kp, kd) | the agent: Unitree's LowCmd, the interface public G1 and H1-2 controllers are deployed through |

Neither robot has fingers to use: the G1 has rubber fists, the H1-2's Inspire hands are fixed. Each hand carries a palm
pad on its wrist mount and has a grip, the benchmark's one abstraction of a hand: while the grip is
closed, the hand holds the nearest of the task's grippable objects whose surface is within 3.5 cm of the palm point and
that moves at most 6 m/s relative to it (a weld); opened, it lets go at once. A catch is therefore a hand brought to
the ball in time, a throw an arm swing with a release instant; neither needs fingers the robot does not have. Rackets,
paddles and clubs are fixed to a hand.

What scripted motions of the robots reached while the families were written is far from most official lines, and
that is the point; the numbers are in the per-family evidence below, are not what any success line was set from, and
are not upper bounds of the hardware (a joint's speed limit bounds its targets; the motor curve lets a feed-forward
torque turn it about 1.1 times faster, and full-torque rows throw much faster than the scripted swings: see the
evidence). The G1
walks at 0.6 m/s and runs at 4 m/s (50 m in about 15 s); the H1-2 walks at 0.7 m/s and has no running policy; an
open-loop squat jump leaves the ground at 2.7 m/s on the G1 and 1.8 m/s on the H1-2; a straight-arm swing of the H1-2
releases a 0.62 kg basketball at 7.5 m/s (11 m/s with the elbow fired late), an 800 g javelin at 4.3 m/s from above the
shoulder, the 7.26 kg shot at 2.6 m/s. Whole-body techniques found offline (key poses searched by CMA-ES in the task's
own world, RoboOlympics' method: `scripts/roboolympics/search_technique.py`) put the shot at 8.1 m/s, throw the
discus at 12.9 m/s and the javelin at 15.0 m/s, serve a volleyball at 11.4 m/s, pass a serve into the setter's
target and set a toss into the hitter's: these six are reference solutions now (2026-10-13).

## The referee

Every family judges with the same toolkit (`shared/rfo/referee.py`), from the simulator's state after every physics
step:

- **Stages.** The events that must happen, in order (`kick → goal`, `take-off → landing → stand`). A stage whose
  predecessor has not latched is ignored; `success` is the last stage, and it ends the episode at that step. Success
  "at a step" rather than "at the end of the replay" (PROTOCOL §3) because a sport's success is an event: a goal
  stands whatever the striker does next. Where the sport has an end state it is a stage of its own, held for a time
  (land and stand, catch and hold, a lift held overhead).
- **Contact events, not contact frames.** A touch is one event from first contact until the parts have been apart for
  a gap; a legal touch may be bounded in duration (a bump is not a carry), and consecutive touches need the ball to fly
  in between.
- **Legal body parts.** Each task says which parts may touch the ball, the ground or the apparatus (feet and shins in
  football, forearms in a bump, the head in a header, the named fist in boxing); any other part is a foul.
- **Crossings on the physics step.** A ball through a goal mouth, down through a ring, over a net or past a line is
  found on the segment between two physics steps (1 ms), not sampled at the control rate.
- **Flight.** The robot's flight phases (nothing but what it grips touches it) are tracked with take-off support,
  air time, apex and landing contacts: a jump is a flight, a step is not.
- **Fouls end the attempt.** A fall (unless the task allows the body on the ground), a line fault, an illegal touch,
  a dislodged bar, the time limit; also a physics blow-up ("the simulation became unstable": MuJoCo's automatic
  reset is off, so a diverged world never continues under an old referee).

The referee's record (events, stages, metrics, every tracker's state) is part of the state hash, so a replay has to
reproduce the referee's decisions and not only the physics.

## Modes

| mode | the agent gets | attempts | graded |
|---|---|---|---|
| privileged | the world in its own container: the simulator and its full state, the referee's live record, this family's rules as code, unlimited resets | unlimited | `trajectory.npz` (sim rows), replayed twice in fresh processes: both must succeed and end in the same state |
| standard | a client: the robot's two head cameras (depth on the left one), joint encoders, motor torques, two IMUs, grip state, the venue's fixed camera; action chunks | 50 resets | the last attempt, recorded by the sidecar and replayed in a fresh simulator |
| standard-realtime (13 dynamic families) | as standard, on a clock that does not stop (S = 1): `submit` plans rows from step `at` and answers at once | 10 resets | as standard; the clock's record is evidence only |

**World-frame information (PROTOCOL D7).** Privileged tasks give everything through the tooling. Standard tasks give
the rule book and the venue as an athlete knows it: the equipment's dimensions and where the lines, the goal or the
hoop are relative to the start (they are fixed by the rules), and roughly where and when a ball will come; never the
robot's position during an attempt, an object's pose, or the referee's state. When an attempt ends the service gives the
referee's call (`meta["outcome"]`: `success` or the rule that ended it; `stages_reached` of `stages_total`), as an
athlete hears it: without it a reset budget teaches nothing.

**Reset budget: 50 (owner, 2026-10-12).** PROTOCOL §4.5's default is 0. A sport is attempts: a
jump or a throw is over in a second or two, ends at the first foul or fall, and the standard agent has no simulator to
practise in; HumanoidBench has 50 for the same reason. Only the last attempt is graded and a success ends the trial.
`RCB_RESET_BUDGET=0` runs one attempt; results state the budget.

**Tooling: thin.** The tooling gives the action types, the state, the referee's record, replay and rendering. It has
no skills: no kick, no throw, no jump, no catch. The walking and running policies are the robot's own controllers (a
G1 ships with a walking controller), part of the platform like its PD loop. The image also holds the robot library's
general helpers unchanged (`bodies/control/kinematics.py`: forward and inverse kinematics; `bodies/trajopt.py`:
jerk-limited joint trajectories); a privileged agent may import them, the tooling does not wrap them.

## Standard-realtime (`eai-standard/2.3`, since 2026-10-14)
The owner, 2026-10-14 (board 0107 D5, board 0112): the dynamic families (PROTOCOL §2: each task's `[metadata] dynamics`, the generator's `DYNAMIC_FAMILIES`;
a ball launched, served, thrown or released on the venue's clock, or a keeper driven after the kick) get a
`-standard-realtime` twin: catch, catch-and-shoot, header, juggle-three, paddle-bounce, penalty-kick,
table-tennis-return, tennis-return, trap-ball, volley-shot, volleyball-bump, volleyball-set, volleyball-spike.
- **Service.** The standard twin's `server.py` (`rcb_service.Sim` on `rcb_rfo.Episode`), unchanged, started by the
  shared realtime layer (`shared/realtime/rcb_realtime.py`, `rcb_client.py`: HumanoidBench's, byte for byte;
  `command: python /srv/rcb_realtime.py`). Same instance, referee, actions, observations and grading (live attempt +
  fresh replay, same final state); the clock's record goes to `reward.json` and decides nothing.
- **Rendering on the GPU.** An OSMesa frame of these venues takes about 1.6 s, which on a clock that does not stop is a
  stall of its own; the twins render with EGL on the `sim` service's GPU (`MUJOCO_GL=egl`, `graphics` capability).
  Image 0.2.1 adds `libegl1` and the NVIDIA EGL ICD manifest; everything else in it is 0.2.0's (the standard and
  privileged tasks move to 0.2.1 with it: the frozen instances rebuild to the same hashes).
- **Slowdown S = 1, resets 10, cutoff 7200 s** (the standard twin's). RTF of the service with the clock flat out
  (`RCB_SLOWDOWN=0.01`, physics only, 4 attempts each; ws-1, 4 CPUs, board 0112): catch 3.61, catch-and-shoot
  3.64, header 3.92, juggle-three 3.89, paddle-bounce 3.74, penalty-kick 3.89, table-tennis-return 4.06,
  tennis-return 3.24, trap-ball 3.03, volley-shot 2.89, volleyball-bump 2.69, volleyball-set 2.62, volleyball-spike
  1.83 (the host's load moved between 30 and 60 during the batch); PROTOCOL §4b gives S = 1 for every one (S =
  ceil(1.5 / RTF) is 1 above RTF 1.5).
- **Checked at S = 1** (board 0112): the three families with a reference solution (paddle-bounce, volleyball-bump,
  volleyball-set; `solution/oracle_plan.py` plans the privileged reference's rows at the control steps where they ran)
  succeed live and in the fresh replay, deterministic; every one of the 13 ran 3 attempts (2 resets) with a controller
  at the control rate and a camera image every 0.25 s with no stall, each graded replay deterministic; nop (no request)
  ends `timeout`, not a success.

## Network: open (PROTOCOL §2.11 exception; owner, 2026-10-11)

RoboOlympics' tasks set no `[agent]` network policy, so the agent's egress is Harbor's default: open. The
instruction says so and encourages the agent to look for existing tools, robot models and pretrained controllers and
to adapt them; it asks only not to look up a ready-made solution to the task, such as this benchmark's reference
solutions (an honour rule; reading the benchmark's installed source is allowed since 2026-10-14;
trials are reviewed). The reasons: a public G1 controller is fair equipment for a sport, as a published walking
controller is for a real G1, and whether an agent can find, vet and adapt existing work is part of what these tasks
measure. What follows:

- Every generated task declares it, `[metadata] network = "open"` (PROTOCOL Appendix H.6: the author's choice; until
  2026-10-14 three prefix lists held it), and its `## External material` paragraph is the generator's `EXTERNAL`;
  `scripts/run_agent_batch.sh` and the scheduler do not narrow these tasks' copies to the usage gateway (the model API still goes through it).
- With open egress the gateway is not the only road to a model provider (the provider key is in the agent's
  container): its token accounting and its budget (PROTOCOL §5) bind only what the harness itself sends, so these runs'
  usage is reported as harness-reported, and a trial that called a model API directly is flagged in review (moved from
  PROTOCOL §2.11 on 2026-10-14).
- Results are not comparable with a closed-network run of the same tasks and are reported as open-network results.
- Nothing an agent can reach holds a solution: the image holds the robot library and the two built-in policies; the
  reference controllers are under `solution/` only; RoboOlympics' repository and this one are private.
- Trial artifacts stay private for the same reason: an instance is frozen, so a passing `trajectory.npz` (or a
  standard run's recorded rows) is a complete solution of the privileged task and, streamed through the client, of its
  standard twin. A results site publishes scores, videos and notes, not the rows.
- The web search tools of the harness stay off in official runs (D11): the agent searches from its own shell.
- In standard mode the agent may install a simulator and a G1 model of its own to practise in; it still cannot open
  the sidecar, read the instance or the referee.

## Determinism and grading

The world is deterministic on the CPU: the same sim rows from the frozen start give the same state hash (simulator
state, controllers' memory, grips, the referee's record). Privileged: `tests/grade.py` replays the trajectory in two
fresh processes; `success` = both succeed ∧ the final hashes agree; an unreadable file or a row that is no sim row is
the agent's 0 (`bad_trajectory`), a replay that does not finish is `grader_error`. Standard: the sidecar journals every
executed sim row, the collect hook ends the episode, the service replays the last attempt in a fresh world and writes
the verdict before the video; `tests/grade.py` reads `final.json` (`success` = live ∧ replay ∧ deterministic). A crash
resumes the same attempt from the journal (`rcb_service.py`, shared with HumanoidBench, KinDER, VLABench and BiGym 2.0).

Across CPUs: the image pins the numerical kernels the policies run on (`OPENBLAS_CORETYPE`, numpy's CPU dispatch) so
that hosts with and without AVX-512 compute the same; a trial is still graded on the host it ran on. The standard
twins' reference solutions are recorded rows streamed open loop, so they depend on this.

## Evidence

Measured on 2026-10-11 on the local host (image `eai-robofunolympics:0.1.0`, built locally). No model has been run.

| check | result |
|---|---|
| referee tests (`scripts/roboolympics/tests/run_all.sh`): per family a positive example, negative controls, the do-nothing agent, the same hash on a replay | 50 / 50 pass |
| do-nothing agent (`nop_table.py` → `nop.json`) | fails in all 50 families |
| reference solutions (`make_oracles.py`): live success, replay success, the same final hash | `sprint` (50 m in 15.84 s), `paddle-bounce` (20 counted bounces, 14.53 s), `golf-putt` (holed, 17.18 s), `boxing` (16.8 N s, 4.04 s), `high-bar-swing` (one giant swing, 23.62 s), `toes-to-bar` (5 repetitions, 7.78 s); since 2026-10-13 also `shot-put` (8.20 m, 6.08 s), `discus` (15.87 m, 8.48 s), `javelin` (21.58 m, 15.33 s), `volleyball-serve` (in the court, 3.28 s), `volleyball-bump` (0.13 m from the target's centre, 5.81 s), `volleyball-set` (0.28 m from the target's centre, 5.87 s): 12 / 12 |
| Harbor oracle, separate verifier, the 6 families × 2 modes | 12 / 12 reward 1, deterministic; the six added on 2026-10-13 (image 0.2.0): 12 / 12 reward 1, deterministic |
| Harbor nop, 8 tasks (`hurdles`, `shot-put` ×2, `tennis-serve`, `penalty-kick`, `balance-board`, `free-throw`, `clean-and-jerk`) | 8 / 8 reward 0 |
| `gen_tasks.py check`, `task_conventions.py --check tasks/roboolympics-*/`, `check-dataset-manifest.sh` | no difference |
| full `ci_checks/run_all.sh` (before the review fixes; they touch only this benchmark's families) | all checks passed |
| independent review, round 1 (two fresh reviewers, 25 families each, looking for a success without the sport) | one exploit demonstrated with actions alone (`juggle-three`: balls carried hand to hand counted as throws) and one shown by injection (`high-jump`: the three plane crossings credited one at a time outside the jump; a rigid bar that carries the robot); weaker points in `long-jump` / `triple-jump` (a cavity under the ground slabs), `hurdles`, `paddle-bounce` (passive rebounds counted), the basketball families (a shuffle without a lift was not travelling), `clean-and-jerk` (overhead by height alone), `juggling`, `pole-vault`, `volleyball-spike`, `boxing` / `kick-target` (the meter's lever arm). All fixed; the reviewers' probes now fail; the tests, instances, oracles and tasks were regenerated |
| independent review, round 2 (three fresh reviewers at cc6bb8fc5: the framework and the trust boundary; 25 athletics, gymnastics and strength families; 25 ball families; each with probes in the simulator) | no success without the sport and no break of the trust boundary found (hostile rows to ±1e308, forged and oversized trajectory files, the standard sidecar's budget, crash recovery and graded episode all held). Found and fixed: `backflip` rejected a legitimate salto (330 degrees in the air demanded; now 300, measured about a horizontal axis); `triple-jump` let hops shorter than a flight cover the distance between phases (by injection; now the landing foot stays within 0.30 m); `volleyball-serve`'s 0.1 s toss grace did not exist in the referee (real tosses failed); the instructions of 7 families with preset arms named a start row that was not the one in force (`gen_tasks.py` now prints the instance's own row; the standard `/spec` carries `start_command`); smaller: a touch of the own court right after the strike was not seen (`table-tennis-return`, `tennis-return`), `tennis-serve` had no toss speed limit, rules judged but not written (`vertical-jump`, `basketball-dribble`), unlisted deviations, the grip's speed test read the step before, a success could stand in the control step of a physics blow-up, H1-2 instructions carried G1 text, the extra venue cameras were not named. Left as they are and why: `high-jump` at 1.00 m can be stepped over by a 1.78 m robot with a small one-foot hop (a legal scissors; the remedy would be a higher bar), `clean-and-jerk` accepts a wide straddle, `pole-vault`'s hang is judged by grip and plant, the `header` / `volley` strike stage can latch on a graze (the goal still decides), a robot propped on a gripped object counts as airborne (no family found where it helps) |

What this evidence does not show. Thirty-eight families have no reference solution, and their positive example is an
injection: it shows that the referee accepts the sport when it happens, not that a controller exists. For a number of
them the gap between what a scripted motion of the body reached and the official line is a factor, not a margin (the
first scripted javelin release of the H1-2 gave 4.3 m/s where 20 m needs about 13.5 m/s, and an offline search later
found a legal 15.0 m/s throw: a factor measured that way says little; the clean and jerk's 45 kg asks
34 N m of an 18 N m elbow; a gripped ball reaches 2.37 m under a 3.05 m ring). The scripted speeds are not upper
bounds: in review round 2 random full-torque rows released objects two to four times faster (a javelin at 14 m/s, a
discus at 15 m/s, a shot at 7 m/s, a baseball at 23 m/s; all within the torque limits, none of them a legal attempt).
Whether those tasks are possible on this hardware is open, and results should be read per family. Two review rounds are not a proof that no referee can be gamed: most
families' cheap exits were tried from reading the code and with trivial policies, some with probes in the simulator; no
reviewer built a full controller for a family without a reference solution. The H1-2's motor curves are RoboOlympics' estimates, and every such gap
depends on them. The rule-book article numbers in the families' texts were written from memory and have not been
checked against the books; the dimensions and masses are the standard ones. Resource numbers are estimates.

<!-- evidence:begin -->
### Per family: the positive example and the do-nothing agent

The human-review table of PROTOCOL §2.7. "By injection" means the referee test (`scripts/roboolympics/tests/test_<family>.py`) sets the simulator's state by hand so that the sport's events really happen in physics; it shows that the referee says yes to the right thing, not that a controller exists. The do-nothing agent holds the starting command to the end of the episode (`nop.json`).

| family | positive example and negative controls | do-nothing agent |
|---|---|---|
| `sprint` | the reference controller (Harbor oracle: 1 in both modes) | 0: `time` at 33.74 s |
| `hurdles` | positive by injection (the H1-2 given 2.0 m/s forward and 5.5 m/s up over each standing 1.067 m hurdle, a real walk to the line); negatives: knocked with a hand, arm or trunk, under the top, beside the hurdle, a leg beside it, left the lane, down. The H1-2's pelvis stands at 1.035 m and walks at 0.7 m/s (50 m alone is 71 s of the 140 s); nothing known lifts it over the bar | 0: `time` at 140 s |
| `shuttle-run` | positive by injection (real running on all four legs, the three about-turns set by hand: 23.0 s); negatives: turning short, a foot only on the line, two legs only, arms over the finish without the torso, down, walking. With the built-in gaits a leg takes about 6 s and an about-turn on the walking policy 3.4 s: about 33 s against the 30 s limit | 0: `time` at 30 s |
| `slalom` | positive by injection (the robot moved from waypoint to waypoint along the prescribed path inside the limit; a real walk round the whole path latches all 12 gates but takes 126.6 s); negatives: a skipped leg, the wrong side, turning back, a cone not rounded, the wrong finish half, a cone touched, down. The running policy turns at most 0.5 rad/s | 0: `time` at 60 s |
| `high-jump` | positive by injection (one foot lifted by the robot's own motors, then 1.5 m/s forward and 5.0 m/s up: over the bar at 1.00 m with 0.28 m to spare, onto the mat); negatives: walking under or round, a two-foot take-off, the bar off its supports. No jumping controller exists for the H1-2 (its open-loop squat jump leaves the ground at 1.8 m/s) | 0: `time` at 60 s |
| `long-jump` | positive by injection (at the board, 3.6 m/s forward and 2.5 m/s up: a mark of 1.50 m in the sand); negatives: running through, landing short or beside the pit, a foot over the line, a take-off beside the board, a stride with the feet pulled up, into the sand without a flight. The running policy's strides come down 0.25 m beyond the line; nothing known jumps out of a run | 0: `time` at 60 s |
| `standing-long-jump` | positive by injection (3.5 m/s forward and 2.5 m/s up from the stance, a perfect landing: a mark of 1.54 m, the stand is the robot's own); negatives: too short, a fall, a dive, a foot over the line, a step or shuffle before the take-off, a leg tuck. The published best for this robot is 0.90 m; a real open-loop push-off of ours takes off legally and lands on its head | 0: `time` at 20 s |
| `triple-jump` | positive by injection (three take-offs with the legs swapped in the air by the robot's own motors: hop 2.64 m, step 5.87 m, mark 8.65 m); negatives: a foot over the line, a two-foot hop, the hop or the step on the wrong foot, another part on the ground, the landing foot down again half a metre on (travelling between two phases), not into the sand. No single-leg take-off exists for this robot | 0: `time` at 60 s |
| `vertical-jump` | positive by injection (the arm raised by the robot's own motors, then 2.8 m/s up: the hand touches the vane 0.30 m above its standing reach, lands and stands); negatives: no touch, lifted without a jump, a step before the take-off, the stand touched, the vane touched without a jump or with another part. A balanced open-loop jump of ours raises the pelvis 0.23 m of the 0.31 m needed; an unbalanced one reaches the vane and falls | 0: `time` at 20 s |
| `pole-vault` | positive by injection (the run-up, the plant and the swing-up are injected: the robot is put on the planted pole 20 degrees short of vertical; from there it really hangs, passes 4 cm over the 2.00 m bar, lets go and lands on the mat); negatives: the bar off its pegs, the ground beyond the zero line before the clearance, a hand moved up the pole, a clearance without the planted pole, round or under the bar, a hand steadying the bar | 0: `time` at 60 s |
| `penalty-kick` | positive by injection (a real walk-up and foot contact, the ball's velocity set at the contact to 20 m/s into the corner; also a chip over the keeper); negatives: an 8 m/s shot saved by the keeper, a weak kick, wide, over the bar, a second touch, in without a kick, a body contact. Beating the keeper takes about 12 m/s to a corner; a G1 foot running into the ball at 4 m/s gives 3 to 5 m/s | 0: `time` at 15 s |
| `dribble-slalom` | positive by injection (the robot really walks the whole course in 54 s, the ball escorted 0.45 m ahead of it); negatives: the ball or the robot on the wrong side, straight back instead of weaving, the ball more than 2 m away, a cone touched, a handball. A walking kick gives the ball about 2 m/s: kick-and-chase inside the 2 m limit was not attempted | 0: `time` at 90 s |
| `trap-ball` | positive by injection (the real 8 m/s pass onto the foot of the standing robot, the ball's speed set to 0.3 m/s as it comes off); negatives: a planted foot (the ball is 7 m away after 3 s), rolling away, first touch a shin, a handball, too close before the pass. The pass arrives at 6 m/s; a still foot sends it off at 5 m/s | 0: `time` at 10 s |
| `volley-shot` | positive by injection (the real cross onto the foot, the ball's velocity set at the contact: in at 11.7, out at 18.4 m/s, into the goal); negatives: a still leg (the ball leaves slower than it came), a body contact, carried, wide, at the keeper, a second touch, too close, in without a volley | 0: `the ball touched the ground before the strike` at 5.11 s |
| `juggling` | positive by injection (a real release, then ten real head contacts with the ball sent up again at 2.6 m/s each time); negatives: passive bouncing (one counted touch), nine then the ground, rises too small, a handball, the trunk, carried, a re-grip. Nothing built in stands on one leg | 0: `time` at 30 s |
| `header` | positive by injection (the real cross onto the head, the ball's velocity set at the contact: in at 11.7, out at 14.6 m/s, into the goal); negatives: a still head (the ball leaves slower than it came), the chest, a hand, wide, a second touch, too close, in without a header. An open-loop hip lunge moves the head at 6.2 m/s | 0: `the ball touched the ground before the header` at 4.94 s |
| `volleyball-bump` | the reference controller (Harbor oracle: 1 in both modes) | 0: `the ball touched the floor before the pass` at 4.52 s |
| `volleyball-set` | the reference controller (Harbor oracle: 1 in both modes) | 0: `the ball touched the floor before the set` at 4.65 s |
| `volleyball-serve` | the reference controller (Harbor oracle: 1 in both modes) | 0: `the serve was not hit in time` at 8 s |
| `volleyball-spike` | positive by injection (a real arm, the real set onto the fist at 2.69 m, a 3.2 m/s ghost jump, the ball's velocity set, a softened landing); negatives: a leg tuck or a lift without a jump, a still fist in a jump, from the floor, before the apex, upward, into the net, long, the antenna, a second touch, a net touch, the centre line. No jump or landing controller exists for the H1-2 | 0: `the ball touched the floor before the spike` at 4.63 s |
| `free-throw` | positive by injection (a real underhand swing and release at 7.4 m/s, the ball's velocity set to 8.1 m/s at 58 degrees: a real flight and ring); negatives: not released in 5 s, the floor, touched again, the line, the semi-circle, from below, a fall. The shot needs 8.06 m/s at 58 degrees; the arm reaches 11 m/s with the elbow fired late, and about 400 search evaluations came within 0.37 m of the ring's centre | 0: `the ball was not released within the time allowed` at 5.01 s |
| `catch-and-shoot` | the catch is real (an open palm on the pass line takes the 7.2 m/s ball and the robot stays up); the shot is an injection (8.7 m/s at 52 degrees set at the release); negatives: not caught, touched before the pass, a leg, the pivot foot, a third step, touched again, the floor, from below, held, a fall | 0: `the pass was not caught: the ball touched the floor` at 3.51 s |
| `layup` | positive by injection (a real arm raise and two real walking steps, a 2.6 m/s ghost take-off, a real release in flight with a 4.4 m/s toss set at the release); negatives: a third step, the same foot twice, not in the air, in the air without a take-off, too far from the ring, a miss, touched again, from below, a fall. The H1-2 has no jump | 0: `time` at 15 s |
| `dunk` | positive by injection (a real arm raise, a 4.5 m/s ghost take-off, the gripped ball really taken down through the ring; the landing is injected too); negatives: let go before the dunk, from below, through without a hand on it, a third step, a fall. Standing, the gripped ball reaches 2.37 m; the ring is at 3.05 m | 0: `time` at 15 s |
| `basketball-dribble` | positive by injection (a real 14 m walk in 20 s with 42 real floor bounces and palm touches; each push is the ball's velocity set at the real touch); negatives: dribbling on the spot, a carry, the ball more than 2 m away, out of bounds, a double touch, both hands, another body part, a fall. A real palm push was not attempted | 0: `time` at 60 s |
| `tennis-return` | positive by injection (the real 30 m/s serve, bounce and contact with the strings; the robot moved 2.9 m sideways and the return's velocity set at the contact: 24 m/s at 9 degrees); negatives: two bounces, the own side, outside the court, through the net, a volley, the body, a double hit, carried, a net touch. The serve reaches the baseline at 15 m/s after 1.1 s, 1.5 m from the robot, which moves 1.2 m in that time | 0: `the ball bounced twice before the racket hit it` at 4.91 s |
| `tennis-serve` | positive by injection (a real rest and release, a 0.3 m fall onto the level racket, the ball's velocity set at the contact: 20 m/s at 11 degrees, into the diagonal box; the let is played out with a real net cord); negatives: unstruck, no added speed, a ball thrown at the racket (faster than a toss), not at rest, a foot fault, struck before clear, a throw past the net, a double hit, carried, the own side, into the net, outside the box, a second let. The slowest legal serve needs 12 m/s; the H1-2 stays up to a head speed of about 9.6 m/s | 0: `time` at 20 s |
| `table-tennis-return` | positive by injection (a real waist-turn stroke with the robot put at the end line in its pre-stroke pose; the contact, the flight and the landing are real); negatives: two bounces, the return on the own court (a real still-blade block), obstruction, another part, struck twice, the table's side, the floor, the net, the free hand on the table. The drawn serve is short: the ball is in reach for 0.14 s, and the stroke returns it in 11 of 25 nearby variants | 0: `the ball bounced twice on your court` at 4.15 s |
| `paddle-bounce` | the reference controller (Harbor oracle: 1 in both modes) | 0: `the ball touched the floor` at 2.51 s |
| `golf-putt` | the reference controller (Harbor oracle: 1 in both modes) | 0: `time` at 30 s |
| `javelin` | the reference controller (Harbor oracle: 1 in both modes) | 0: `time` at 60 s |
| `shot-put` | the reference controller (Harbor oracle: 1 in both modes) | 0: `fell` at 4.58 s |
| `discus` | the reference controller (Harbor oracle: 1 in both modes) | 0: `time` at 60 s |
| `pitch-target` | positive by injection (a real stand on the mound and release, the ball's velocity set to 22 m/s: a strike; a 14.5 m/s lob at 29 degrees is a strike too); negatives: no foot on the plate, a bounce, high, wide, touched after the release. An arm swing of the H1-2 gives 6.8 m/s, 9.9 m/s with the trunk (and a fall) | 0: `the ball was not delivered within the pitch timer` at 15 s |
| `bowling` | positive by injection (a real release, the ball laid 0.35 m past the line at 8 m/s into the pocket: a strike); negatives: over the foul line, a gutter ball, a head-pin hit that is no strike, touched after the release, a foul after the delivery. Strikes exist from 4 m/s on (2 of 17 entry lines 1 cm apart); a swing of the H1-2 gives 3.3 m/s and it falls during the swing | 0: `time` at 40 s |
| `catch` | positive by injection (the real launch and flight; below 3 m the ball is put 0.12 m above the upturned palm at 3 m/s and really gripped); negatives: onto the trunk, touched while rising, dropped after the catch, a fall. The ball comes down 1.25 m from the robot after 3 s at 16.6 m/s: the walk and a palm placed within centimetres are the task | 0: `the ball touched the ground` at 3.99 s |
| `juggle-three` | positive by injection (the hands still, real grip releases and catches, each released ball put on an arc to the other palm); negatives: a ball coming down on its own hand, gripped by its own hand, a low pass, out of order, the waiting ball pushed, onto the head. With still hands the outgoing ball always meets the incoming one: a cascade needs hands that move | 0: `a ball that came down on a hand was not caught` at 2.98 s |
| `wall-ball` | positive by injection (a real release, the ball's velocity set to 20 m/s: the target hit, the rebound's last 0.8 m replaced as in `catch`); negatives: over the line, outside the target, a bounce before the wall, the rebound onto the body or the floor, taken back before the wall, dropped. An arm swing gives 6.9 m/s; the throw needs 16 to 20 m/s | 0: `time` at 15 s |
| `boxing` | the reference controller (Harbor oracle: 1 in both modes) | 0: `time` at 15 s |
| `kick-target` | positive by injection (a stiff posed leg and the whole robot given 1.0 m/s: 26.7 N s in 0.054 s; then put back on its feet); negatives: a slower kick, a touch over the bound, the other leg, below the band, walking in, the bag swinging back onto the robot. Leg swings on servo-held joints gave 2 to 8 N s; there is no balance on one leg | 0: `time` at 15 s |
| `balance-beam` | positive by injection (the robot slid along the 10 cm beam in its tandem pose, 4 mm per step); negatives: `stand` mode (off in 1.5 s), the walking policy (off in 0.5 s), stopping short, past the end, lying on it, beside it. The tandem hold on joint targets is stable; a real walk on a 10 cm beam was not attempted | 0: `time` at 90 s |
| `steeplechase` | positive by injection (a flight over the 0.914 m hurdle and the pit; a landing in the pit with a second hop out; from standing on the bar); negatives: under, round, a trailing foot, to the side of the water jump. The H1-2's open-loop squat jump raises its centre of mass 0.16 m; the walking policy does not climb the pit's slope | 0: `time` at 60 s |
| `box-jump` | positive by injection (1.6 m/s forward and 3.7 m/s up onto the 0.61 m box, a perfect landing, the stand is the robot's own); negatives: touching the box before the jump, landing on the floor, a leg tuck, a one-foot take-off, the box's side, not on the feet, the floor after the landing, a fall. The H1-2's open-loop squat jump leaves the ground at 1.8 m/s | 0: `time` at 20 s |
| `vault` | positive by injection (a ballistic handspring: 3.5 m/s forward, 5.3 m/s up, 6.2 rad/s; both hands really on the 1.35 m table; stopped at touchdown); negatives: not over the table, another part on the table, no hand on it, not on the feet, off the mat | 0: `time` at 80 s |
| `backflip` | positive by injection (3.4 m/s up and 9 rad/s backwards: 360 degrees in 0.70 s of flight, the rotation stopped at touchdown, the stand is the robot's own); a salto that lands on its feet 36 degrees short of upright has its turn and landing counted; negatives: no turn, a forward flip, two thirds of a turn, a spin about the vertical with the pelvis on its side, a head-first landing, a roll on the ground, a hop shorter than the minimum flight, not from the feet. An open-loop squat jump of the G1 has 2.7 m/s and 0.55 s of air | 0: `time` at 20 s |
| `crawl` | positive by injection (the robot laid prone, 0.27 m high, and dragged under the 21 wires by a force on the pelvis); negatives: walking upright into a wire, on hands and knees (0.46 m: a wire touched), round, over, not under, stopping inside. No crawling controller exists | 0: `time` at 120 s |
| `high-bar-swing` | the reference controller (Harbor oracle: 1 in both modes) | 0: `time` at 60 s |
| `toes-to-bar` | the reference controller (Harbor oracle: 1 in both modes) | 0: `time` at 60 s |
| `clean-and-jerk` | positive by injection (a crane force on the 45 kg barbell and a balance force on the trunk; the final 2 s are carried by the robot's own locked arms and legs); negatives: the bar off the platform without both hands, let go, down before the signal, overhead without a clean, bent elbows or knees, split feet, another part on the platform. At the shoulders the elbows need 34 of their 18 N m; overhead with straight arms the robot holds the bar about 1 s | 0: `time` at 60 s |
| `balance-board` | positive by injection (a spring-damper force on the torso, a helper's hand, for the 30 s); negatives: the do-nothing agent (the deck is down at 2.6 s), the walking policy, leaning, left alone after 20 s, off the board. A linear feedback on leg sway rides the full 30 s from the exact start but falls after 14 to 28 s when started 1 mm off, so it is not shipped as a reference solution | 0: `the deck touched the floor` at 2.59 s |
<!-- evidence:end -->

### What the families without a reference controller rest on

Nothing but their referee tests: in the official settings no controller of ours does these sports, and for most of
them none is known for these robots. The injected positives show that each referee says yes to the sport done right
and the negatives that it refuses the cheap ways round; they say nothing about whether an agent can do it within its
budget. Some are a measured factor of two to four from the hardware's open-loop reach (the jumps onto and over things,
the pitch, the serve and the return in tennis; the shot, the discus, the javelin and the volleyball serve were in this
list until the offline key-pose search found reference solutions for them), a few may be beyond the motors altogether (the clean and jerk of
45 kg: the elbows need 34 of their 18 N m at the shoulders; the dunk: 0.7 m of rise above the reach). They are in the
set on the owner's decision that the settings are the real ones; a first model batch will say which nobody passes.

## Compute

CPU only. One world steps about five times faster than real time on one core and holds about 0.4 GB. Privileged: the
agent's container has 8 CPUs and 16 GiB (it may run several worlds at once, or train); the verifier 4 CPUs and 8 GiB.
Standard: the sidecar 4 CPUs and 8 GiB, the agent's container 4 CPUs and 10 GiB. The values are author estimates until
a batch has been measured (`scripts/task_resources.toml`).

## Run

```bash
python3 scripts/roboolympics/gen_tasks.py check
harbor run -p tasks/roboolympics-sprint-i00-privileged -a oracle        # or -a nop: scores 0
harbor run -p tasks/roboolympics-penalty-kick-i00-standard -a codex -m openai/gpt-6-luna --env-file .env
scripts/roboolympics/tests/run_all.sh                                   # every family's referee test, in the image
```
Build the image: `scripts/build_images.sh` (context `images/robofunolympics/`). Regenerate after a change to a family:
`RFO_RW=1 scripts/roboolympics/dev.sh /rfo/make_instances.py`, `RFO_RW=1 scripts/roboolympics/dev.sh
/rfo/make_oracles.py`, `python3 scripts/roboolympics/gen_tasks.py render`, `cd tasks && harbor add --scan .`.

## Tasks exported by RoboOlympics (its own service inside the task; PROTOCOL §4c)

RoboOlympics exports these tasks itself with `tools/export_fexam.py` (CHIGUI0/roboolympics, private): its own
generated task, with the simulator service, referee, scripted opponents, observation, the frozen review between points,
the fresh-process replay and the grader unchanged, turned into a plain Harbor 0.23.0 task (contributed in #180, by
CHIGUI0; merged with the maintainers' fixes below). They are listed in `scripts/roboolympics/exported.toml` (with the
RoboOlympics commit and the sport's frozen revision of each, and the files changed here since the export);
`gen_tasks.py` renders none of them, and they are refreshed by re-running the exporter (`python3 tools/export_fexam.py
--hub <this checkout> <this checkout>/tasks`), then `scripts/task_conventions.py` on them (each keeps its own `[agent] timeout_sec`).

| task | what | instance | oracle (vanilla Harbor 0.23.0, 2026-10-13) |
|---|---|---|---|
| `roboolympics-tabletennis-match-i01-standard-realtime` | table tennis vs the scripted opponent, RoboOlympics revision `wallclock-15` (players serve, rail base, real-robot limits; S = 10 since RoboOlympics PR #138) | level 2, seed 22, S = 10 | partial: the camera-only reference player lost 3:5 at S = 10 (it won 6:4 at S = 20; it wins level 2 in 16 of 40 seeds in the screening); nop 0 |
| `roboolympics-tabletennis-match-i02-standard-realtime` | as above | level 3, seed 12, S = 10 | partial: the reference lost 3:5 (it wins level 3 in 7 of 40); nop 0 |
| `roboolympics-badminton-match-i01-standard-realtime` | singles badminton on a 0.4-scale court (BWF Laws, one game to 11; revision `badminton-wallclock-12`, PR #81): Franka Panda with a racket on a Festo gantry base; the players serve | level 1, seed 7, S = 20; agent budget **14400 s** (a per-task exception: a game to 11 at S = 20 took the reference alone 78 min; at S = 10 the camera-only reference loses level 1, 0 of 20) | partial: the camera-only reference won 12:10 (93 min; an earlier run on the same instance lost 10:12; it wins level 1 in 17 of 20 seeds in the screening); nop 0 |
| `roboolympics-badminton-match-i02-standard-realtime` | as above | level 2, seed 8, S = 20, 14400 s | partial: the camera-only reference does not win level 2 (a model did: Opus 11:7); same task as i01 but the level |
| `roboolympics-soccer-match-i00-standard-realtime` | humanoid soccer 2 v 2 (RoboCup Humanoid League rules, revision `soccer-2v2-10`: the T1's real motors): one agent commands both Booster T1 robots of its team (walk velocity, stand, kick) from their head cameras against a scripted team; 2 x 5 min of game time | level 2, seed 7, S = 5 (2 x 5 min = 3000 s of wall time plus the reviews, inside 7200 s) | partial: the camera-only reference lost 1:8 on soccer-2v2-10 (0:2 on soccer-2v2-9; it cannot kick while walking; a model has won level 2, Astra 12:2); nop 0. Image `ghcr.io/mll-lab-nu/eai-olympiad-soccer:0.1.0` (private to the mll-lab-nu organization for now) |
| `roboolympics-soccerssl-match-i00-standard-realtime` | wheeled soccer 5 v 5 (RoboCup Small Size League rules, revision `soccer_ssl-1`): one agent commands its five omnidirectional robots (move, kick, dribble) from four overhead cameras against a scripted team; two halves and, if level, a shoot-out (about 1035 s of game time) | level 2, seed 7, S = 10; agent budget **14400 s** (the task's own `[agent] timeout_sec`: the match alone is 2.9 h of wall time at S = 10, and at S = 5 the four cameras cannot be rendered in time) | partial: the camera-only reference lost 2:5 in a full match (valid, replay identical; 2 h 35 min of agent time, over 7200 s); nop 0 |
| `roboolympics-fencing-bout-i01-standard` | robot epee fencing, one FIE direct-elimination bout (15 touches or 9 min of fencing time; RoboOlympics revision `fencing-7`, a RoboOlympics preview sport): two Unitree G1s (NVIDIA SONIC on legs, waist and free arm) fence phrase by phrase from on guard, each phrase replayed from a table of all 2916 phrases measured in MuJoCo; the agent chooses each phrase's tactical intention (one of nine) against a scripted fencer that reads its choices; turn-based (`eai-standard-turn/1.0`), a chess clock of 60 min per player | level 1, seed 39 | full: the camera-only reference won 15:11 (25 phrases, replay identical; the world is deterministic, so the oracle's result is the one RoboOlympics computes in process; seed chosen by a stated rule, RoboOlympics `tools/fexam/fencing/instances.py`); nop 0 (valid, no-show) |
| `roboolympics-fencing-bout-i02-standard` | as above | level 2, seed 35 | full: the reference won 15:13 (32 phrases, replay identical); nop 0 |
| `roboolympics-tabletennis-hitskill-i00-standard` | implement the robot's `hit` skill (the blade's state at contact) from the robot's model, its real-limit joint interface and a disclosed toolkit; graded offline by the sport's API test | 90 public development requests (24 development matches); success: rate >= 0.7 | full: RoboOlympics' reference skill 69/90 (the platform's own `hit` 90/90, an IK-only baseline 0/90); nop 0 |
| `roboolympics-badminton-actskill-i00-standard` | implement the badminton robot's `act` skill (the racket's state at contact, optional base position) from its model, its real-limit joint interface and the toolkit; graded offline by the sport's API test (RoboOlympics revision `badminton-wallclock-12`, PR #98) | 246 public development requests (12 development matches, levels 1-2); success: rate >= 0.8 | full: RoboOlympics' reference skill 244/246; nop 0 |

What differs from the 2.x tasks (PROTOCOL §4c, owner 2026-10-14):

| | the 2.x tasks | exported RoboOlympics tasks | why |
|---|---|---|---|
| protocol | `eai-standard/2.x` | `eai-standard-realtime/1.0` (real-time matches; RoboOlympics' own: `game` CLI / HTTP at `localhost:8000/A/...`), `eai-standard-turn/1.0` (turn-based matches, mode `standard`: the same service and `game` CLI; the world waits for the player whose turn it is, and each player has a chess clock of real time that runs on its own turns, reviews included; a player whose clock runs out loses, a valid 0), `skilleval-api-test/1` (skill tasks) | the frozen review after every point (at most 300 s, 600 s in soccer: `READY_TIMEOUT_S`; the world stands still, the agent's time runs on; a side that has not sent `ready` by then loses the match, `ready_timeout`, a valid 0: the world does not go on by itself; stated in each instruction and in `game spec` `timing.review_timeout_s` since 2026-10-14, board 0121, `patched` in exported.toml) is part of RoboOlympics' rules, and its results are only comparable under them |
| crash recovery | journal, resume | none: a sim crash ends the trial with `infra_error = 1` | the service replays the whole match from its record to grade it; a resumed match would not be the recorded one |
| slowdown | — | per task, the sport's official slowdown: table tennis 10 (RoboOlympics PR #138), badminton 20, humanoid soccer 5, wheeled soccer 10 (`metadata.slowdown`); turn-based matches have none (`metadata.chess_clock_s`: fencing 3600 s) | results state S, or the chess clock |
| agent budget | the benchmark's 7200 s | 7200 s; badminton i01 / i02 and wheeled soccer 14400 s (those tasks' own `[agent] timeout_sec`, owner 2026-10-14) | a game to 11 at S = 20 took the reference alone 78 to 93 min; a 5 v 5 match is 2.9 h of wall time at S = 10 |
| network | open (part 1's exception) | the allowlist (model APIs and package registries), as every other benchmark: these tasks declare it, and PROTOCOL §2.11 holds them to it | RoboOlympics' design; the open-egress exception is part 1's |
| twin | privileged + standard | none (the README's Twin row says why) | no trajectory deliverable |
| skill task | — | mode `standard`, `task_type = "policy"`, no sim service; the verifier runs the simulator and the skill | the deliverable is code (`/app/output/skill/hit.py`, `act.py`) |
| seeds | the instance's | matches: `[metadata.seeds]` default = allowed = the instance's development seed (a turn-based match whose world is deterministic has one outcome per sequence of choices: its oracle is `full` when the reference wins that seed); skill tasks: seed 0 = the fixed development request set | development seeds below 100000: previews; RoboOlympics' official results are produced by RoboOlympics on its hidden six-digit seeds |
| metering | the usage gateway | the same (the seat is "unmetered" for RoboOlympics: no proxy, no credential in the sim; the D11 proxy's file `metering/think_proxy.py` is in the image's copy but never started) | |

**Replay videos of the matches (fixed here, 2026-10-16, board 0136).** The sim service draws the spectator video after the verdict (`core.spectator`, `RCB_VIDEO_TIMEOUT_S`); the grade never depends on it. Humanoid soccer's full match takes about 8-10 min to replay and draw, so its limit is 1800 s (was 300 s, as wheeled soccer) and the collect hook waits as long. Badminton declares no spectator camera or scene, so the core drew nothing: its tasks run `environment/sim/spectator/sport_video.py` from the collect hook instead (the players' two cameras, the sport's own `Views`, at 10 frames per game second; `video.json` says whether that replay ended in the verdict replay's state). `spectator/` is outside the match's `source_sha` (`core/`, `sport/`), so the match, its replay check and the grade are unchanged and earlier results stand; both are `patched` in `exported.toml` (to be sent upstream: a spectator camera in `sports/badminton/sport.toml` would change the sport's `source_sha`). Table tennis (about 100-420 frames) and wheeled soccer (1800 s) rendered every recorded video and are unchanged. Fencing (turn-based) draws one still per phrase, held 1 s, with `core.spectator`; its limit is 900 s (board 0146: never shorter than the verdict replay's 600 s), the collect hook waits as long.

**Skill tasks' verifier (fixed here, 2026-10-14, board 0111; the #180 review's finding).** The verifier runs the
delivered skill as `nobody` in its own process, in the container that grades it. A skill could leave a detached process
behind (double fork, `setsid`) that rewrote `/logs/verifier/report.json` or the reward files after the evaluation
(Harbor makes `/logs/verifier` 777, without the sticky bit), so a skill that hits nothing could be graded a success. Now:
the evaluator is the subreaper of the skill's tree, and closing a skill kills its session and every process of
`nobody` below the evaluator until none is left (`skilleval/sandbox.py` `end_sandbox_processes`; it raises, and the
grade is a `grader_error`, if one survives); the skill runs with `RLIMIT_NPROC` 128; `tests/test.sh` makes
`/logs/verifier` 755 and writes the report to `/var/lib/skilleval/` (root, 700); `tests/engineer_grade.py` kills any
process of `nobody` left in the container, removes every entry of `/logs/verifier` root did not write, reads the
report only from a root-owned directory nobody else can write, and writes the reward files fresh (`O_EXCL`,
`O_NOFOLLOW`), then copies the report there. The isolation probe (`python3 -m skilleval.evaluate --sport-dir sport
--probe --skill <dir with probe.py>`) adds three targets: writing `/logs/verifier`, writing the report's directory,
and a detached process that must be gone after the skill is closed (`survives_close`), plus `nproc_unlimited`. Measured
in the verifier image (Harbor's layout: root, no network, `/logs/verifier` 777): a skill that plants a success and
leaves a process to keep it there got reward 1 from the exported grader and gets 0 now; the reference skill still
passes; the probe finds no leak. Still possible and harmless: a skill with `memory = "per_case"` can keep files in `/tmp`
between requests (it gets no outcome back, so it learns nothing it was not given).

Images: `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` (public; the image RoboOlympics' frozen revisions were screened on;
built from RoboOlympics' own tree, not from this repository), for every task but humanoid soccer, which runs on
`ghcr.io/mll-lab-nu/eai-olympiad-soccer:0.1.0` (private to the organization until the owner makes it public: hosts
without a login cannot pull it). The agent's container of the skill tasks is `python:3.12.14-slim`. CPU only.

## Licences

This benchmark's code: MIT (the repository's). RoboOlympics (the robot library, the running policy's port): MIT. Unitree
G1 model and meshes: MuJoCo Menagerie, BSD-3-Clause. Unitree's walking policy (unitree_rl_gym): BSD-3-Clause. The
running policy (C1801SYQ/g1_running): Apache-2.0. FALCON's G1 policy (LeCAR-Lab/FALCON): MIT. WBC-AGILE's G1
velocity-height policy (nvidia-isaac/WBC-AGILE): Apache-2.0. Every licence file is next to its files in the image
(`images/robofunolympics/roboolympics/SOURCE.md`); the image can be published.
