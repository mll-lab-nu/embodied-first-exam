"""Archery: the sport-specific sections of the turn-based program-play prompt (structure in turn_prompt.py)."""
from turn_prompt import duel, single

RULEBOOK = ("World Archery Rulebook, Book 3: Target Archery (version 2026-03-13), "
            "https://extranet.worldarchery.sport/documents/index.php/?doc=7626&inline=1")

SINGLE_TASK = """You are the archer. Shoot a round of **4 ends x 3 arrows** at a World Archery **122 cm 10-ring target face**, at
**50 m (end 1), 70 m (ends 2 and 3) and 90 m (end 4)**, outdoors in a gusty wind. **Success: a complete round with a
total of at least 110 of the 120 possible points.**"""

DUEL_TASK = """You are an archer. Another agent shoots the same round on an identical lane next to yours; your seat (`A` or `B`) is
in `game spec`. The round is **4 ends x 3 arrows** at a World Archery **122 cm 10-ring target face**, at **50 m
(end 1), 70 m (ends 2 and 3) and 90 m (end 4)**, outdoors in a gusty wind. In each end one player shoots its 3 arrows,
then the other: the player `match.first_player` in `game spec` shoots first in ends 1 and 3, the other player in ends
2 and 4. **The higher total wins.** A tie goes to a shoot-off (below). Both players receive this document."""

OBSERVATION = """**Observation** (`observe`{when}): one PNG (`game` saves it as a file and prints its path; HTTP: `observation.image_png_b64`,
base64) with four camera tiles at the positions given in `game spec` (`image.tiles`: x, y, width, height):
- `archer` (1000 x 600): from just behind the bow, looking straight down the range. Windsocks on 4 m poles at 1/4, 1/2
  and 3/4 of the distance stand 3.5 m to your left; a smaller one stands next to the target;
- `scope` (600 x 600): a narrow view from the arrow rest, centred on the gold (3.6 m across at the target);
- `side` (800 x 500): from 12 m right of the range at half the distance, looking across the range at the middle
  windsock; image right = towards the target;
- `target` (600 x 600): a close-up of the face, centred on the gold (1.44 m across), with your arrows of this end:
  nock and fletching **magenta = arrow 1, lime = arrow 2, cyan = arrow 3**. An arrow's hole is where its black shaft
  meets the face; arrows arrive descending, so the shaft rises from the hole towards the camera. Arrows are pulled
  after each end.
There are no coordinates and no wind numbers. The cameras are pinholes with square pixels and the principal point at
the tile centre; `game spec` gives their poses and focal lengths for each distance (`cameras_by_distance`) and where
the windsocks hang (`windsocks_by_distance`). The reply to a shot gives the arrow's score (`X` = inner 10, `10` ...
`1`, `M`), for a miss what the spotter saw (e.g. "missed the boss, passed high and left of it"), and a close-up of the
face right after the arrow landed (`landed_image_file`; HTTP: `landed_image_b64`)."""

ACTION = """**Action** (`shoot`): `ELEV AZIM DRAW`:
- `ELEV`: the arrow's launch direction above horizontal at release, degrees (-10 to 30);
- `AZIM`: the launch direction's heading, degrees (-20 to 20): 0 = straight down the range (perpendicular to the
  target face), positive = to your **left**;
- `DRAW`: the draw fraction, 0.5 to 1.0; the arrow leaves the bow at **68 m/s x DRAW**.
Your release is not perfect: the executed shot scatters around your command with N(0, 0.03 deg) in elevation,
N(0, 0.03 deg) in azimuth and N(0, 0.3 %) in launch speed."""

RULES = """World Archery target archery scoring. Each arrow scores the zone it lands in: 10 for the gold centre down to 1 for the
outer white ring; X (the inner 10) counts 10; an arrow touching a dividing line scores the higher zone; an arrow off
the face scores M (0). The wind is horizontal and uniform over the range and constant during a flight; it changes from
end to end and gusts from arrow to arrow, and **the windsocks always show the wind for the arrow you are about to
shoot**. A windsock points downwind; it hangs straight down in calm air and rises linearly with the wind speed: its
angle below horizontal is 90 deg x (1 - speed / 10 m/s), horizontal at 10 m/s or more (1.2 m long, 5 stripes,
orange at the mouth)."""

SINGLE_DEVIATIONS = """Deviations from the official rules (World Archery Rulebook, Book 3, 2026):
- A short custom round (12 arrows at 50-90 m) instead of a standard round; no practice ends.
- The arrows are shot by a release primitive with a stated scatter; time is a chess clock instead of 2 minutes per
  3-arrow end (WA 11.2)."""

DUEL_RULES = RULES + """

The match is scored as in compound match play: the cumulative total of the 4 ends (WA 12.1.4.3). A tied total goes to a
shoot-off (WA 12.5.2.2): one arrow each at 70 m, the first player first; the higher score wins, then the arrow nearer
the centre; a tied pair is shot again until the tie is broken. Both lanes are identical: the n-th arrow of either
player meets the same wind and the same release scatter. You see the camera images only on your own turn. The replies
list every arrow shot since your previous call with its score (`shots_since_your_last_call`).

Deviations from the official rules (World Archery Rulebook, Book 3, 2026):
- A short custom round (4 ends x 3 arrows at 50, 70, 70, 90 m) instead of a standard match round; no practice ends.
- Each player shoots its 3 arrows of an end in a block, not alternating arrow by arrow (WA 11.1.4.1, 11.2.3.2).
- The end order is fixed (the first player starts ends 1 and 3, the other ends 2 and 4) instead of the trailing
  archer starting the next end (WA 11.1.4.1).
- The shoot-off is shot at 70 m.
- The arrows are shot by a release primitive with a stated scatter; time is a chess clock instead of end and arrow
  time limits (WA 11.2)."""

PHYSICS = """Metres, seconds. x points down the range (the shooting line is x = 0, the target face is the vertical plane x = D), y
to your left, z up; the ground is z = 0. The arrow leaves the rest at (0, 0, 1.50). The gold centre is at (D, 0, 1.30);
zones are 6.1 cm wide (1-2 white, 3-4 black, 5-6 blue, 7-8 red, 9-10 gold); the face sits on a 1.30 m square straw
boss. White lines cross the range every 10 m.
- The arrow is a point mass (20 g, shaft diameter 5.5 mm) under gravity (9.81 m/s^2) and quadratic air drag on its
  velocity **relative to the air**: a = -g z - K |v - w| (v - w), K = rho Cd A / (2 m) = 1.07e-3 1/m (rho = 1.2 kg/m^3,
  Cd = 1.5 on the shaft cross-section A = pi d^2 / 4), w = the wind."""

SINGLE_COMMANDS = [
    ("game spec", "GET /spec", "the range, the bow, the arrow, the cameras, the clock"),
    ("game status", "GET /status", "the current state and the scorecard, no image"),
    ("game start", "POST /start {}", "start the round (your clock starts); the state and the image"),
    ("game observe", "POST /observe {}", "the state and the camera image"),
    ("game shoot ELEV AZIM DRAW", 'POST /act {"type":"shoot","elev_deg":ELEV,"azim_deg":AZIM,"draw":DRAW}', "shoot one arrow (below)"),
    ('game ready "WHY" "PLAN"', 'POST /ready {"why":"...","plan":"..."}', "after each arrow: your review"),
]

DUEL_COMMANDS = [
    ("game spec", "GET /spec", "your seat, the range, the bow, the arrow, the cameras, the clock"),
    ("game status", "GET /status", "the current state and your scorecard, no image"),
    ("game start", "POST /start {}", "you are ready; the match begins when both players have started"),
    ("game wait", 'POST /wait {"timeout_s":T}', "block until it is your turn or the match is over (HTTP: at most T <= 60 s per call)"),
    ("game observe", "POST /observe {}", "on your turn: the state and the camera image"),
    ("game shoot ELEV AZIM DRAW", 'POST /act {"type":"shoot","elev_deg":ELEV,"azim_deg":AZIM,"draw":DRAW}', "shoot one arrow (below)"),
    ('game ready "WHY" "PLAN"', 'POST /ready {"why":"...","plan":"..."}', "after each of your arrows: your review"),
]


def single_prompt():
    return single(title="Target archery in the wind: program play", task=SINGLE_TASK, url="http://sim:8000",
                  commands=SINGLE_COMMANDS, observation=OBSERVATION.format(when=""), action=ACTION,
                  rules=RULES + "\n\n" + SINGLE_DEVIATIONS, physics=PHYSICS, opponent=False, state="total so far")


def duel_prompt(start="30 minutes"):
    return duel(title="Target archery, two players: program play", task=DUEL_TASK, url="http://sim:8000/<your seat>",
                commands=DUEL_COMMANDS, observation=OBSERVATION.format(when=", on your turn"), action=ACTION,
                rules=DUEL_RULES, physics=PHYSICS, start=start, state="both totals")


if __name__ == "__main__":
    import sys
    print(duel_prompt() if sys.argv[1:] == ["duel"] else single_prompt())
