# The 50 RoboOlympics families, v2: official settings

Owner's decisions (2026-10-11), which replace the v1 design ("an easy setting"):

1. **Real settings.** Every venue, piece of equipment and ball is the rule book's: official dimensions and masses, the
   ball's real flight (drag and lift in air: `scene.OFFICIAL`, `Scene(air=True)`) and bounce. Nothing is scaled to the
   robot, and nothing is softened so that a reference solution exists. The benchmark measures the ceiling of coding
   agents; a task nobody can do yet is a legitimate task.
2. **All humanoid, two sizes.** `robot = "unitree_g1"` (1.32 m, 33 kg; walking and running policies) or
   `robot = "unitree_h1"` (Unitree H1-2: 1.78 m, 67 kg, 27 joints; a walking policy, no running policy) where the
   official size needs an adult-size body.
3. **Single actions.** One attempt of one skill (one jump, one throw, one return), not a match.

How a family states its realism (RoboOlympics' convention): `rulebook` (name, edition, the articles used) and a list
of `deviations`, each with the article it departs from, what is different and why. A deviation is allowed when the
sport cannot be simulated or judged otherwise (the hand's grip instead of fingers, a rigid pole, a scripted feeder
instead of an opponent, no wind), never to make the task easier. Both go into the task's texts.

**Success lines.** Where the rule book defines the success (a goal, a made basket, a legal serve, a strike, a valid
trial that clears the bar) that is the success. Where the sport only measures (a distance, a time), the success is a
valid trial that reaches the family's *qualifying mark*, a round number taken from human school or club standards and
named as such; it is never derived from what a reference controller reaches.

Robot: G = Unitree G1, H = Unitree H1-2. Status of the v1 module in brackets: (rework) = same sport, official numbers;
(new) = replaces a v1 family that was not a real event.

## A. Athletics: track and jumps (World Athletics Competition and Technical Rules 2024, TR)

| family | robot | official setting | success |
|---|---|---|---|
| `sprint` (rework) | G | TR 16-19 at the indoor distance of 50 m (owner, 2026-10-12: not 100 m; the benchmark shows a capability, it does not stage the Olympic programme): a 50 m straight, 1.22 m lanes, standing start; "on your marks", "set" 2.0 s later, the gun 1.2-2.2 s after "set" (the instance's fixed draw); a start movement earlier than 0.100 s after the gun is a false start; the finish is the torso reaching the line | a valid finish (no false start, in the lane) within 30 s |
| `hurdles` (rework) | H | TR 22 at the indoor distance of 50 m (owner, 2026-10-12: not 110 m): four hurdles 1.067 m high at 13.72 m + 9.14 m × i, 8.86 m to the finish; RoboOlympics' hinged hurdle with the official toppling force (3.6-4.0 kg at the top bar); knocking a hurdle down is allowed, going beside it or under its top is not | a valid finish over all four within 140 s |
| `shuttle-run` (rework) | G | the 4 × 10 m shuttle run (the school fitness test): two lines 10 m apart, four legs, a foot beyond the line at each turn | finish within 30 s |
| `slalom` (rework) | G | the Illinois agility test: a 10 m × 5 m course, four centre cones 3.3 m apart, the prescribed path (out, back, weave up, weave down, out, back) | the path completed without touching a cone, within 60 s |
| `high-jump` (rework) | H | TR 26-27: uprights 4.02 m apart, a 4.00 m bar on its supports, the landing mat 6 × 4 × 0.7 m (soft); take-off from one foot | the bar at 1.00 m cleared and still on its supports |
| `long-jump` (rework) | G | TR 29-30: 40 m runway, the take-off board 1 m before the pit, the foul line at its far edge, a 2.75 m × 9 m sand pit (soft contact); the mark is the nearest break in the sand to the take-off line | a valid jump that lands in the pit (the mark is then at least 1.00 m) |
| `standing-long-jump` (rework) | G | the standing long jump test: two-foot take-off from behind the line, no step before it, the mark at the rearmost landing contact | mark ≥ the robot's own height, 1.32 m; land and stand |
| `triple-jump` (rework) | G | TR 31: hop (take-off and landing on the same foot), step (the other foot), jump (both feet into the pit); board 7 m before the pit | a valid hop-step-jump sequence that ends in the pit |
| `vertical-jump` (new; was precision-landing) | G | the jump-and-reach test (Sargent): standing reach is measured at the start; a vane set 0.30 m above it | a two-foot jump from a standstill whose hand touches the vane; land and stand |
| `pole-vault` (rework) | H | TR 28: the box (1.0 m long, 0.20 m deep at the stop board), uprights 4.3 m apart, a 4.5 m bar, the mat 5 × 5 × 0.8 m; deviation: a rigid 4.0 m, 2 kg pole | the bar at 2.00 m cleared with the pole planted in the box, the bar still on its supports |

## B. Football (IFAB Laws of the Game 2025/26) and volleyball (FIVB Rules 2025-2028)

| family | robot | official setting | success |
|---|---|---|---|
| `penalty-kick` (rework) | G | Law 14: goal 7.32 × 2.44 m, the mark 11 m from the goal line, a size-5 ball; a goalkeeper on the line: a keeper dummy 1.9 m × 0.6 m that starts at the centre and moves along the line (at most 3 m/s, from 0.25 s after the kick) towards where the ball is heading | the whole ball over the line inside the goal, one kick |
| `dribble-slalom` (rework) | G | a slalom dribble: six cones 2 m apart, round the last and back through them, a size-5 ball | the ball and the robot through the whole course, the ball never more than 2 m away, no cone touched, within 90 s |
| `trap-ball` (rework) | H | a ground pass from 15 m at 8 m/s, half a metre to one side | first touch with a foot; the ball under control (at rest within 1 m of the robot) inside 3 s of the touch |
| `volley-shot` (rework) | H | a cross: the ball lobbed from the wing 20 m away to the penalty mark area; the official goal 11 m away, the keeper dummy at the centre (static) | struck by a foot before it bounces, then the whole ball into the goal |
| `juggling` (rework) | G | keepie-uppie with a size-5 ball, from the ball in the hands | 10 consecutive touches by feet, thighs or head, no hand after the first drop, no ground |
| `header` (rework) | H | a cross from the wing 20 m away to the six-yard box (5.5 m from the goal line); the official goal, static keeper dummy | the first touch is the head, then the whole ball into the goal before a second touch |
| `volleyball-bump` (rework) | H | serve receive: court 18 × 9 m, net 2.43 m; a float serve from behind the far end line (about 14 m/s) lands in the robot's zone | a forearm pass (one contact, not caught) that rises above net height and comes down inside the setter's target (a 2 m circle at the net, position 2/3) |
| `volleyball-set` (rework) | H | a pass tossed from the back court to the setter at the net | one overhead contact with the fingers side of the hands (the fists; not caught), the ball rising at least 1 m above the net and coming down inside the outside hitter's target (a 2 m circle at position 4) |
| `volleyball-serve` (rework) | H | Rule 12: from behind the end line (9 m from the net), toss and hit with one hand or arm, over the 2.43 m net | the ball lands in the opponent's 9 × 9 m court (touching the net on the way is legal) |
| `volleyball-spike` (rework) | H | a set to position 4: the ball comes down 0.5 m from the net from a 4.5 m apex | struck by a hand above net height while airborne, lands in the opponent's court; no net touch, no centre-line fault |

## C. Basketball (FIBA Official Basketball Rules 2024) and rackets

| family | robot | official setting | success |
|---|---|---|---|
| `free-throw` (rework) | H | ring 3.05 m high, 0.45 m inner diameter, backboard 1.80 × 1.05 m; the free-throw line 4.225 m from the ring's centre; a size-7 ball | released behind the line, down through the ring |
| `catch-and-shoot` (rework) | H | a chest pass (8 m/s from 5 m) to the robot at the top of the key, 5.8 m from the ring's centre | caught, then shot from there: down through the ring |
| `layup` (rework) | H | Art. 25 travelling: from a standing start 3 m from the ring with the ball held, at most two steps | released while airborne, down through the ring |
| `dunk` (rework) | H | the official ring | the ball pushed down through the ring from above with a hand on it; land on the feet |
| `basketball-dribble` (rework) | H | Art. 24: baseline to the centre line (14 m), a size-7 ball | the ball dribbled all the way (one hand at a time, no carry, no double dribble, never held for more than two steps), within 60 s |
| `tennis-return` (rework) | H | ITF court (23.77 × 8.23 m singles), net 0.914 m at the centre; a serve at 30 m/s into the robot's service box; a 0.30 kg racket on the hand, MuJoCo ball-string contact (restitution 0.85 on a clamped racket: no gain) | returned after one bounce, over the net, into the singles court |
| `tennis-serve` (rework) | H | ITF Rules 16-18: from behind the baseline, a toss and a strike, diagonally | lands in the correct service box (6.40 m deep); a let is replayed once |
| `table-tennis-return` (rework) | G | ITTF Laws 2.1-2.6: table 2.74 × 1.525 × 0.76 m, net 15.25 cm; Google DeepMind's system-identified ball, table and net contact (RoboOlympics `tt_scene.xml`, Apache-2.0); a legal serve from RoboOlympics' serve library (the instance's draw by seed, not chosen for being returnable); a 0.14 kg paddle | a good return (Law 2.7) |
| `paddle-bounce` (rework) | G | the same ball and paddle | 20 consecutive bounces on the paddle, each rising at least 0.15 m, alternating forehand and backhand sides not required; no other contact |
| `golf-putt` (rework) | G | Rules of Golf: ball 45.9 g, 42.67 mm; a hole 108 mm in diameter, at least 101.6 mm deep, cut into the green; a 3 m putt on a flat green at stimp 10; a putter on the hand | holed with one stroke |

## D. Throws, catching, striking

| family | robot | official setting | success |
|---|---|---|---|
| `javelin` (rework) | H | TR 38: men's javelin 800 g, 2.65 m, grip at the cord; a 4 m wide runway, the arc, a 28.96° sector; the throw counts only if the tip touches the ground before any other part; the javelin's drag and lift from MuJoCo's ellipsoid fluid model | a valid throw of at least 20 m |
| `shot-put` (rework) | H | TR 33: men's shot 7.260 kg; the 2.135 m circle with the stop board; a 34.92° sector; put from the shoulder with one hand (the shot at the neck at the start, never behind the line of the shoulders or below the shoulder) | a valid put of at least 6 m |
| `discus` (rework) | H | TR 34: men's discus 2 kg, 0.22 m; the 2.50 m circle; a 34.92° sector; the ellipsoid fluid model for its drag and lift | a valid throw of at least 15 m |
| `pitch-target` (rework) | H | MLB Official Baseball Rules: the pitcher's plate 18.44 m from home plate, a foot on the plate at release; the strike zone 0.432 m wide, 0.46 to 1.07 m high, at the plate; a baseball with RoboOlympics' drag and Magnus coefficients | a strike: the ball through the zone on the fly |
| `bowling` (rework) | H | USBC: lane 18.288 m to the head pin, 1.0541 m wide, gutters; ten 1.53 kg pins on their spots; a 6 lb (2.72 kg) ball (legal: the rules set only a maximum); RoboOlympics' oil pattern as friction zones | a strike, delivered from behind the foul line |
| `catch` (rework) | H | a fly ball: a baseball launched from 40 m at 45° (about 21 m/s), coming down within 3 m of the robot | caught before it touches the ground, held 1 s |
| `juggle-three` (new; was toss-and-catch) | G | a three-ball cascade (balls 0.07 m, 0.13 kg), two in one hand and one in the other at the start | 10 consecutive catches in cascade order, no ball on the ground |
| `wall-ball` (rework) | H | a throw at a wall 5 m away, a 0.5 m target circle 1.5 m high, a tennis ball | hits the target and is caught on the fly, held 1 s |
| `boxing` (rework) | H | a 30 kg, 1.2 m heavy bag hanging by a chain | a clean punch with the knuckle part of the named fist that gives the bag at least 12 N s, guard up again, on the feet 2 s later |
| `kick-target` (rework) | H | the same bag, a mark at trunk height (1.1 m) | a kick with the named foot or shin on the mark that gives the bag at least 20 N s; back on both feet, standing 2 s |

## E. Gymnastics apparatus (FIG Apparatus Norms), weights, obstacles

| family | robot | official setting | success |
|---|---|---|---|
| `balance-beam` (rework) | G | FIG: 5 m long, 0.10 m wide, 1.25 m high; the robot starts standing on one end | walk to the other end and stand, nothing touching the floor |
| `steeplechase` (new; was stepping-stones) | H | TR 23: the water-jump hurdle, 0.914 m high (men) and 3.66 m wide, fixed, with the 3.66 m water jump behind it (the pit slopes from 0.5 m deep at the barrier to the track level) | over the barrier (a foot or hand on it is legal) and out of the pit beyond the 3.66 m, on the feet |
| `box-jump` (rework) | H | a 0.61 m (24 in) plyometric box | a two-foot jump from the floor onto the top, stand up straight on it |
| `vault` (rework; was obstacle-vault) | H | FIG: the vault table 1.35 m high (men), a 25 m run-up, a springboard, the landing mat | over the table with the hands (only) on it, land on the feet on the mat |
| `backflip` (rework) | G | floor exercise: a standing back tuck | a full backward rotation in flight, landing on the feet, standing 2 s |
| `crawl` (rework) | G | a low-wire obstacle: wires 0.45 m above the ground over 10 m | through, under the wires without touching one |
| `high-bar-swing` (rework) | G | FIG horizontal bar: 2.80 m high, 2.40 m between the uprights, 28 mm; the robot starts in a dead hang | one giant swing: a full 360° circle around the bar with the body extended |
| `toes-to-bar` (new; was hanging-leg-raise) | G | the same bar, a dead hang | 5 toes-to-bar: both feet touch the bar between the hands, back to the hang each time |
| `clean-and-jerk` (new; was overhead-press) | H | IWF: a 20 kg men's bar (2.2 m, 28 mm) with the lightest competition load on 0.45 m discs (2 × 10 kg discs + 2 × 2.5 kg collars: 45 kg), on the platform | from the floor to locked arms overhead, feet in line, held still 2 s |
| `balance-board` (new; was wobble-board) | G | a roller board: a 0.76 × 0.38 m deck on a free roller of 0.085 m radius (no spring, no stops but the deck's lips) | 30 s on the board, the deck's ends never on the floor |

## What every v2 module must do

- `robot`, `rulebook`, `deviations` class attributes (see `task.py`); the texts state the rule book and each deviation.
- Official balls from `scene.OFFICIAL` (`sc.ball(name, "football", ...)`), the venue's real dimensions in `params`.
- Close the holes the v1 reviews found: a "flight" is not a jump unless the family requires a real take-off (pelvis
  rise or upward speed at lift-off); a strike must add something (the ball leaves faster than it came, or changes
  direction as the sport needs), a static limb in the ball's path is not a strike where the sport needs a swing; the
  robot may not wait at the launcher (a line it stays behind, or a touch only after the ball's apex); a ball waiting to
  be launched may not be touched; every threshold the referee uses is in `params` and in the rules text; "a fall" is
  defined in the rules text.
- A referee test with the do-nothing agent, a positive (a real controller, or an injection that makes the events really
  happen) and a negative for every cheap exit. A reference solution only where one comes without softening anything.
