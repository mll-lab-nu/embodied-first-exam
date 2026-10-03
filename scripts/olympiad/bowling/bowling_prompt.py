"""Ten-pin bowling: the sport-specific sections of the turn-based program-play prompt (structure in turn_prompt.py).
Official rules: USBC Playing Rules 2025-2026 (https://bowl.com/getmedia/cabf49db-8cc5-4ce4-abc0-dfca1a1d7706/071724_USBC-Playing-Rules.pdf)."""
from turn_prompt import duel, single

SINGLE_TASK = """You are the bowler. Bowl one game of ten-pin bowling (10 frames) on a simulated lane. **Succeed by scoring 200 or
more.** No practice balls."""

DUEL_TASK = """You are a bowler. You and another agent each bowl one game of ten-pin bowling (10 frames), each on your own simulated
lane. Both lanes and the release scatter are identical: the same release, at the same ball of a frame with the same
pins standing, gives the same result. Your seat (`A` or `B`) and the first player are in `game spec` (`seat`,
`match.first_player`). **Win with the higher total after 10 frames;** equal totals go to a roll-off (Rules). Both
players receive this document."""


def commands(duel_=False):
    rows = [
        ("game spec", "GET /spec", "the lane, cameras, limits, your clock"),
        ("game status", "GET /status", "the current state, no image"),
        ("game start", "POST /start {}", "start the game; your clock starts"),
        ("game observe", "POST /observe {}", "the current decision point and its camera image (`game` saves it to a file "
                                             "and prints the path; HTTP: `observation.image_png_b64`)"),
    ]
    if duel_:
        rows.append(("game wait [MAX_S]", 'POST /wait {"max_s":S}',
                     "return when it is your turn or the match is over (at most 60 s)"))
    return rows + [
        ("game roll BOARD ANGLE_DEG SPEED RPM AXIS_DEG",
         'POST /act {"type":"roll","board":B,"angle_deg":A,"speed":V,"rpm":R,"axis_deg":X}', "bowl one ball (below)"),
        ('game ready "WHY" "PLAN"', 'POST /ready {"why":"...","plan":"..."}', "hand in the review of your last ball"),
    ]


OBSERVATION = """**Observation** (`observe`): the decision point (`frame`, `ball` 1-3, `fresh_rack`, `pins_standing`, and your previous
ball as `last_ball`: what you played and how many pins fell) and one PNG of 1960 x 1620 pixels with four camera views
(their pixel rectangles are in `game spec`, `image.tiles`):
- left column, top: `approach` (960 x 540): your eye on the approach, 2.2 m behind the foul line over the centre of the
  lane, 1.55 m up, looking down the lane, pitched 5 degrees down;
- left column, middle: `pindeck` (960 x 540): the pins standing now, seen from 2.4 m in front of the head pin, 0.95 m
  up, pitched 17 degrees down;
- left column, bottom: `pindeck_after` (same camera): the deck right after your previous ball settled, before the
  fallen pins were swept (black before your first ball);
- right, from x = 960: `lane` (1000 x 1360): the lane from straight above in four stacked panels of 5 m each (top
  panel: from 0.5 m behind the foul line; bottom: the pin deck); in each panel image right = towards the pins and image
  up = left. The path of your previous ball is drawn as yellow dots, one every 1/30 s.

There are no ball or pin coordinates and no oil numbers: find the pins, the ball's path and the lane markings in the
image. After each ball you are told how many pins fell, not which. All cameras are pinholes with square pixels and the
principal point at the centre of their view; their poses and fields of view are in `game spec`."""

ACTION = """**Action** (`roll`): the release; what the ball then does is physics.
- `BOARD`: where the ball's centre is laid down on the lane, 35 cm past the foul line. The lane is 39 boards
  (27.03 mm each) wide, counted from the right gutter: board 1 is the rightmost, 20 the centre, 39 the leftmost (as
  seen facing the pins). Fractions are fine; 1 to 39.
- `ANGLE_DEG`: the launch direction, degrees from the lane's axis; + = towards the left (higher boards); -10 to 10.
- `SPEED`: ball speed at release, m/s; 3 to 11.
- `RPM`: rev rate at release, revolutions per minute; 0 to 700 (0 = no revs, a straight ball).
- `AXIS_DEG`: axis rotation: the spin axis is horizontal; 0 = end-over-end roll (no hook), 90 = the axis points along
  the launch direction (all side roll, the most hook); + hooks the ball to the left, - to the right; -90 to 90.
- Each executed value scatters around what you asked for (Gaussian, standard deviations: board 1.0, angle 0.24
  degrees, speed 1.5 %, rev rate 4 %, axis 2 degrees).
The reply reports how many pins fell, strike, spare or gutter, and whether the frame is finished."""

RULES = """Ten-pin rules as in the USBC Playing Rules 2025-2026. Scoring: a strike scores 10 plus your next two balls, a spare 10
plus your next ball; a strike or spare in the 10th frame gives bonus balls (three balls at most); 300 is perfect. Each
frame's first ball (and in the 10th frame each ball after a strike or spare) gets a fresh rack. After the first ball of
a frame the fallen pins are swept away; the pins still standing stay where they are, even if they were moved. A pin
counts as down if it tilts more than 20 degrees or leaves the lane surface (into a gutter, the pit or against a side
wall); a pin standing anywhere on the lane counts as standing. A ball that enters a gutter before it reaches the pins
scores no pins, and the pins it moves are respotted (USBC 6b.1)."""

DUEL_TURNS = """

Turns: a player bowls a whole frame (one or two balls, up to three in the 10th), with a review after each ball, then
the other player bowls the same frame on their own lane. The first player bowls first in every frame. You see only
your own lane; after each of your opponent's balls you are told how many pins fell, and both scores are in every
reply.

Tie: equal totals go to a roll-off (USBC 118b): each player bowls one more frame, scored like a 10th frame on a fresh
rack, the first player first, and the higher roll-off frame wins; while level, another roll-off frame follows, at most
3. If the match is still level after 3 roll-off frames, the player with more chess-clock time left wins."""

DEVIATIONS = """

Deviations from the official rules (USBC Playing Rules 2025-2026):
- Pin down: tilted more than 20 degrees or off the lane surface (approximates USBC 6a).
- No fouls: the release is a set of numbers and the ball starts past the foul line (USBC 5a does not apply).
- No rear cushion: the pit behind the pin deck is open (USBC 6b.2 does not apply)."""

DUEL_DEVIATIONS = DEVIATIONS + """
- The roll-off stops after 3 frames; then the chess clock decides (USBC 118b continues until the tie is broken)."""

PHYSICS = """Metres, seconds; rigid-body physics. The lane frame: x along the lane from the foul line towards the pins, y across
(+ = left), z up; lane surface z = 0.
- Regulation lane: 18.29 m from the foul line to the head pin, 1.054 m wide, gutters on both sides, then the pin deck,
  the pit behind it and side walls (kickbacks) that pins bounce off. Markings: the foul line, aiming arrows on boards
  5, 10, ..., 35 between 3.9 and 4.6 m (the centre one furthest), dots at 2.13 m.
- Pins: 38.1 cm tall, 1.53 kg, standing in a triangle 30.48 cm apart: pin 1 (the head pin) in front at the centre, 2
  and 3 behind it (2 on the left, 3 on the right as you see them), then 4-5-6, then 7-8-9-10 (7 far left, 10 far
  right).
- Ball: 21.8 cm, 7 kg. The front part of the lane is oiled (low friction: the ball skids), the back end is dry (high
  friction). A ball with side roll skids straight on the oil, then hooks where the friction rises and finally rolls.
  The oil runs further down the middle boards than on the outside boards, so a ball out towards the gutters meets the
  dry lane sooner. How long the oil is and how much the ball hooks: find out from your balls' paths."""


def single_prompt():
    return single(title="Ten-pin bowling: program play", task=SINGLE_TASK, url="http://sim:8000",
                  commands=commands(), observation=OBSERVATION, action=ACTION, rules=RULES + DEVIATIONS,
                  physics=PHYSICS, opponent=False, contest="game")


def duel_prompt(start="30 minutes"):
    return duel(title="Ten-pin bowling, two players: program play", task=DUEL_TASK,
                url="http://sim:8000/<your seat>", commands=commands(True), observation=OBSERVATION, action=ACTION,
                rules=RULES + DUEL_TURNS + DUEL_DEVIATIONS, physics=PHYSICS, start=start)


if __name__ == "__main__":
    import sys
    print(duel_prompt() if sys.argv[1:] == ["duel"] else single_prompt())
