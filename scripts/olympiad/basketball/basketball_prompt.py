"""Basketball shooting: the sport-specific sections of the turn-based program-play prompt (structure in turn_prompt.py)."""
from turn_prompt import duel, single

RULEBOOK = ("FIBA Official Basketball Rules 2024 (Art. 16, goal), "
            "https://assets.fiba.basketball/image/upload/documents-corporate-fiba-official-rules-2024-v10a.pdf; "
            "closest standard contest: FIBA 3x3 Shoot-out Contest, https://fiba3x3.com/en/rules.html")

SINGLE_TASK = """You are the shooter: a simulated Franka Panda arm on a 1 m pedestal with a ball cup, which works as a launcher (you
choose the release, it throws), on a basketball court. You take **10 shots**: two from each of five spots, in order
(spot 1 twice, then spot 2 twice, ... spot 5 twice), from mid-range to beyond the three-point line. Nobody tells you
where the spots are: you see the court, the hoop and the defender only through cameras. **Success: at least 6 makes
of 10.**"""

DUEL_TASK = """You are a shooter: a simulated Franka Panda arm on a 1 m pedestal with a ball cup, which works as a launcher (you
choose the release, it throws), on a basketball court. Another agent shoots on an identical court; your seat (`A` or
`B`) is in `game spec`. The match has five rounds, one per spot (spot 1 .. spot 5, from mid-range to beyond the
three-point line): in each round one player takes its 2 shots from the spot, then the other. The player
`match.first_player` in `game spec` shoots first in rounds 1, 3 and 5, the other player in rounds 2 and 4. **The most
makes wins.** A tie goes to extra shots: pairs of one shot each (the first player first) from spot 1, 2, ... 5, 1, ...;
the pairs continue until one pair differs, which decides. If the makes are still level after 30 extra pairs (a safety
cap), the player with more chess-clock time left wins (the last-resort rule; both clocks are recorded exactly). Nobody tells you where the spots are: you see
the court, the hoop and the defender only through cameras. Both players receive this document."""

OBSERVATION = """**Observation** (`observe`{when}): one PNG (`game` saves it as a file and prints its path; HTTP:
`observation.image_png_b64`, base64), a 2 x 2 grid of 640 x 480 tiles. Top left `shooter_wide` and top right
`shooter_zoom`: two cameras on your shooter (the same position, behind and above the arm, looking along the shooter's
heading, pitched up 8 degrees; vertical field of view 55 and 16 degrees). Bottom left `broadcast`, bottom right
`baseline`: fixed cameras overlooking the court. There are no hoop, ball or shooter coordinates: judge them from the
images. `game spec` gives every camera's pose and intrinsics (pinholes, no distortion; for the two shooter cameras the
pose in the shooter's frame), so image points can be turned into rays. The reply to a shot gives its `result`
(`made`, `rim`, `backboard`, `blocked`, `airball`), `how` it went in, what the ball `touched`, and a picture strip of
it (`result_image_file`; HTTP: `result_image_b64`): 4 frames 100 ms apart around the ball's closest approach to the
hoop, from a side camera at the hoop (row 1) and your `shooter_zoom` (row 2)."""

ACTION = """**Action** (`shoot`): `ANGLE SPEED SPIN YAW`:
- `ANGLE`: release elevation above horizontal, degrees, 20 to 80;
- `SPEED`: release speed, m/s, 3 to 14;
- `SPIN`: revolutions per second, -5 to 5; positive = backspin (Magnus force, below), negative = topspin;
- `YAW`: the release direction relative to the shooter's current heading, degrees, -35 to 35, **positive = to the
  left** (counter-clockwise seen from above). The shooter is parked facing roughly, **not exactly**, towards the hoop
  (a few degrees off, different at every spot).
The launcher is good but not perfect: each shot's release scatters by about 0.5 % in speed, 0.4 degrees in elevation
and direction, and 0.15 rev/s in spin (1 sigma)."""

RULES = """A shot is **made** when the ball enters the basket from above and passes through it (FIBA Art. 16.1.1); every make
counts 1, from any spot. A defender stands between you and the hoop, on the line from you to it,
`min(3.0 m, 0.55 x your distance to the hoop)` from you (axis to axis), with its hands up (the hands' top at 2.55 m);
it does not move. A ball that touches the defender first is **blocked** and does not count."""

DEVIATIONS = """Deviations from the official rules (there is no official shooting contest in the FIBA or NBA rules; the closest
standard is the FIBA 3x3 Shoot-out Contest, 10 shots, each make worth 1):
- A shooting contest: {format}, instead of a game.
- Every make counts 1, from any spot, instead of 2 or 3 points by the release area (FIBA Art. 16.2.1).
- NBA court markings and equipment sizes (FIBA Art. 2 uses a 6.75 m three-point arc and a 1.80 m backboard).
- A static defender with its hands up, and a ball that touches it first does not count, instead of live defence.
- The shots are thrown by a launcher with a stated scatter; time is a chess clock instead of a shot clock."""

SINGLE_RULES = RULES + "\n\n" + DEVIATIONS.format(format="10 shots from five spots")

DUEL_RULES = RULES + """

The two courts are identical: the same spots and headings, and the n-th shot of either player has the same release
scatter. You see the camera images only on your own turn. The replies list every shot taken since your previous call
with its result (`shots_since_your_last_call`).

""" + DEVIATIONS.format(format="two players, 2 shots each from five spots in alternating rounds, then extra pairs of shots on a tie, with a safety cap of 30 pairs decided by the chess clocks")

PHYSICS = """Metres, seconds. NBA court markings. The hoop's centre is at (0, 0, 3.048) (rim height 3.048 m); the floor is z = 0;
the court is y < 0 (the baseline is y = +1.60 behind the backboard). Rim inner diameter 0.457 m (orange, 16 mm tube);
backboard 1.83 x 1.07 m, its front face 0.381 m behind the rim centre, bottom edge at 2.90 m, with a red border and a
red 0.61 x 0.45 m shooter's square above the rim. Court lines (white, 5 cm): lane 4.88 m wide, free-throw line at
y = -4.19 with its 1.8 m circle, three-point arc 7.24 m from the hoop centre (straight 6.71 m from the centre line in
the corners), sidelines x = +-7.62.
- The shooter's frame: origin on the floor at the pedestal axis, +x = its heading, z up. The ball (radius 0.1195 m,
  size 7, 0.62 kg) is released at (0.503, 0, 2.166) in that frame, rotated with `YAW` about the pedestal axis (the arm
  turns to aim), 0.45 s after the throw starts.
- Flight: gravity 9.81; air drag F = -0.01454 |v| v N; Magnus F = 0.00419 (omega x v) N (omega in rad/s; backspin
  turns about the horizontal axis d x z, d the release direction). The floor, rim, bracket and backboard are hard and
  bouncy (restitution about 0.8 floor, 0.6 rim, 0.65 backboard); the net is visual only."""

SINGLE_COMMANDS = [
    ("game spec", "GET /spec", "the court, the shooter, the ball, the cameras, the clock"),
    ("game status", "GET /status", "the current state, no image"),
    ("game start", "POST /start {}", "start the round (your clock starts); the state and the image"),
    ("game observe", "POST /observe {}", "the state and the camera image"),
    ("game shoot ANGLE SPEED SPIN YAW", 'POST /act {"type":"shoot","angle_deg":ANGLE,"speed":SPEED,"spin_hz":SPIN,"yaw_deg":YAW}', "take one shot (below)"),
    ('game ready "WHY" "PLAN"', 'POST /ready {"why":"...","plan":"..."}', "after each shot: your review"),
]

DUEL_COMMANDS = [
    ("game spec", "GET /spec", "your seat, the court, the shooter, the ball, the cameras, the clock"),
    ("game status", "GET /status", "the current state, no image"),
    ("game start", "POST /start {}", "you are ready; the match begins when both players have started"),
    ("game wait", 'POST /wait {"timeout_s":T}', "block until it is your turn or the match is over (HTTP: at most T <= 60 s per call)"),
    ("game observe", "POST /observe {}", "on your turn: the state and the camera image"),
    ("game shoot ANGLE SPEED SPIN YAW", 'POST /act {"type":"shoot","angle_deg":ANGLE,"speed":SPEED,"spin_hz":SPIN,"yaw_deg":YAW}', "take one shot (below)"),
    ('game ready "WHY" "PLAN"', 'POST /ready {"why":"...","plan":"..."}', "after each of your shots: your review"),
]


def single_prompt():
    return single(title="Robot basketball shooting: program play", task=SINGLE_TASK, url="http://sim:8000",
                  commands=SINGLE_COMMANDS, observation=OBSERVATION.format(when=""), action=ACTION, rules=SINGLE_RULES,
                  physics=PHYSICS, opponent=False, state="makes so far")


def duel_prompt(start="30 minutes"):
    return duel(title="Robot basketball shooting, two players: program play", task=DUEL_TASK,
                url="http://sim:8000/<your seat>", commands=DUEL_COMMANDS, observation=OBSERVATION.format(when=", on your turn"),
                action=ACTION, rules=DUEL_RULES, physics=PHYSICS, start=start, state="both players' makes")


if __name__ == "__main__":
    import sys
    print(duel_prompt() if sys.argv[1:] == ["duel"] else single_prompt())
