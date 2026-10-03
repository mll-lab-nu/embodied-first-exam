"""Curling: the sport-specific sections of the turn-based program-play prompt (structure in turn_prompt.py)."""
from turn_prompt import duel, single

SINGLE_TASK = """You are the skip of the yellow team and throw every yellow stone yourself, against a computer team with red stones
(its level is `match.opponent_level` in `game spec`). **Win the match**: 4 ends of 5 stones per team, with extra ends
if the score is tied (see Rules). Every match ends with a winner."""

DUEL_TASK = """You skip one team and throw all its stones against another agent. Your seat (`A` or `B`) and your colour (A yellow,
B red) are in `game spec`. **Win the match**: 4 ends of 5 stones per team, with extra ends if the score is tied (see
Rules). Every match ends with a winner. Both players receive this document."""


def _commands(prefix, duel):
    rows = [
        ("game spec", f"GET {prefix}spec", "sheet geometry, cameras (poses, intrinsics), "
                                          + ("your seat and colour, clocks" if duel else "opponent level, clock")),
        ("game status", f"GET {prefix}status", "the current state, no images"),
        ("game start", f"POST {prefix}start {{}}", "you are ready; the match begins when both players have started"
                                                 if duel else "start the match and your clock; shows the sheet"),
    ]
    if duel:
        rows.append(("game wait [MAX_S]", f'POST {prefix}wait {{"max_s":S}}',
                     "return when it is your turn (or the match is over), at most S <= 60 s"))
    rows += [
        ("game observe", f"POST {prefix}observe {{}}", "the state and two camera images (`game` saves them to files and "
                                                      "prints their paths; HTTP: `observation.images_png_b64`)"),
        ("game throw SPEED ANGLE SPIN", f'POST {prefix}act {{"type":"throw","speed":V,"angle":A,"spin":S}}',
         "throw your next stone" + (" on your turn" if duel else "") + " (below)"),
        ('game ready "WHY" "PLAN"', f'POST {prefix}ready {{"why":"...","plan":"..."}}', "hand in the review after your throw"),
    ]
    return rows


SINGLE_COMMANDS = _commands("/", False)
DUEL_COMMANDS = _commands("/", True)

OBSERVATION = """**Observation** (`observe`): the end, the throw in the end, the score, the hammer, the stones left to throw and in
play, the ends so far, and two PNG images (`house`, `hack`). There are no stone coordinates: read the positions from
the images. Stones are grey granite with a coloured top and handle (yellow or red). The reply to each throw also says
what was heard (`shots_since_your_last_call`): collisions, and stones removed from play and why.
- `house`: a camera straight above the far house at world (0, 36.2, 20), looking down; image up = +y (towards the back
  line), image right = +x. 600 x 1000 px, focal length 2000 px, principal point (300, 500):
  u = 300 + 2000 x / (20 - z), v = 500 - 2000 (y - 36.2) / (20 - z). The top of a stone is at z of about 0.11 and the
  handle top at 0.146. It shows the sheet from just before the far hog line to beyond the back line.
- `hack`: an end camera behind the hack at (0, -3, 5) looking at (0, 37, 0); 1024 x 576 px, vertical field of view
  8 degrees. Both cameras' full poses and intrinsics are in `game spec`."""

ACTION = """**Action** (`throw SPEED ANGLE SPIN`): the stone's state at release, not a target.
- `SPEED`: the release speed at the hack (the origin), 0.5-4.0 m/s.
- `ANGLE`: the release direction in degrees from the centre line; positive is to the right (+x); |ANGLE| <= 5.
- `SPIN` (HTTP `spin`): `ccw` (counter-clockwise seen from above) curls the stone to the left (-x), `cw` to the right
  (+x).

Throws have a small execution error: the release speed scatters by about 0.004 m/s (about ±14 cm in length for a draw)
and the direction by about 0.03 degrees (about ±2 cm at the house)."""

INTRO = "The Rules of Curling of World Curling (July 2025), with the deviations at the end:\n"

RULES_COMMON = """- A delivered stone that does not come to rest completely beyond the far hog line (stone centre y < 32.149) is removed
  from play, unless it struck another stone (then it stays in play). A stone that touches the side line
  (|x| + 0.145 >= 2.375) or completely crosses the back line (y - 0.145 > 40.234) is removed from play.
- Free guard zone: the area between the far hog line and the tee line, excluding the house (and stones still in play
  short of the hog line after striking stones there). Before the 6th stone of an end, if a delivered stone moves an
  opposition stone from the free guard zone out of play, directly or indirectly, the delivered stone is removed from
  play and every moved stone is put back where it was.
- Scoring, after all 10 stones of an end: the team with the stone closest to the tee (among stones in the house: centre
  distance < 1.829 + 0.145) scores one point for each of its stones in the house closer than the other team's closest
  stone. No stone in the house: a blank end.
- The team without the hammer (the last stone of the end) throws first, and the teams alternate. After an end, the team
  that scored throws first in the next end; a blank end keeps the hammer where it was.
- If the score is tied after 4 ends, extra ends are played until a team scores, at most 3. If still level at the cap,
  the player with more chess-clock time left wins.
- The n-th stone of each team in an end gets the same random draw for its execution error (its size is the
  thrower's own)."""

DEVIATIONS = """- Deviations from the rules: 4 ends of 5 stones per team (official: 8 or 10 ends of 8 stones); at most 3 extra ends,
  then the chess clocks decide (official: extra ends until a team scores); no sweeping; the stone is released at the hack with the given
  speed, direction and spin (no delivery rules); no no-tick rule (official R7)."""

SINGLE_RULES = INTRO + """- The opponent has the hammer in end 1 (a fixed handicap of this task; officially decided by a coin toss or the
  last stone draw).
""" + RULES_COMMON + """
- The opponent is a scripted team that draws to the button, takes out your stones and, at higher levels, guards its
  shot stone; it picks the shot that leaves it best placed now, and its execution error is its own size, smaller at
  higher levels. Its chess clock never runs (it keeps its 60 minutes), so a tie after the last extra end goes to it.
""" + DEVIATIONS

DUEL_RULES = INTRO + """- `match.first_player` in `game spec` throws the first stone of end 1, so the other player has the hammer in end 1.
""" + RULES_COMMON + """
""" + DEVIATIONS

PHYSICS = """Metres, world frame: the release point (the hack) is the origin, +y runs down the sheet, +x is to the right as seen
from the hack, z up.
- Far hog line y = 32.004, tee line y = 38.405 (the tee, the centre of the house, is at (0, 38.405)), back line
  y = 40.234. The house has radius 1.829, with rings at 1.219 and 0.610 and the button at 0.152. The sheet spans
  |x| <= 2.375. Stones have radius 0.145 and mass 19.96 kg.
- Ice: the speed v decreases at
  a(v) = (0.00200985 / (v + 0.06385782) + 0.00626286) x 9.80665 m/s^2. A rotating stone curls: the direction of its
  velocity turns at 0.00820 x v^-0.8 rad/s, towards -x for `ccw` and +x for `cw`. Every stone is released with
  |omega| = pi/2 rad/s; the spin decays at 0.025 / v rad/s^2, and this never reverses the curl.
- The curl is strongest when the stone is slow, so a draw bends most near the end of its path. A draw to the tee (no
  other stones) needs a release speed of about 2.39 m/s and curls about 2.1 m sideways: aim about 3.1 degrees to the
  right with `ccw`, or to the left with `cw`. Takeouts use about 2.7-3.5 m/s and curl much less.
- Collisions between stones are elastic (restitution 1, equal masses) with friction 0.2 at the contact. A full hit on a
  stationary stone roughly stops the thrower and sends the struck stone on at the thrower's speed; glancing hits split
  the motion and change both directions."""


def single_prompt():
    return single(title="Curling: program play", task=SINGLE_TASK, url="http://sim:8000", commands=SINGLE_COMMANDS,
                  observation=OBSERVATION, action=ACTION, rules=SINGLE_RULES, physics=PHYSICS, contest="match",
                  state="the score, the end and the hammer")


def duel_prompt(start="30 minutes"):
    return duel(title="Curling, two players: program play", task=DUEL_TASK, url="http://sim:8000/<your seat>/",
                commands=DUEL_COMMANDS, observation=OBSERVATION, action=ACTION, rules=DUEL_RULES, physics=PHYSICS,
                start=start, contest="match", state="the score, the end and the hammer")


if __name__ == "__main__":
    import sys
    print(duel_prompt() if sys.argv[1:] == ["duel"] else single_prompt())
