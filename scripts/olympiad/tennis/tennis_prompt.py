"""Tennis: the sport-specific sections of the program-play prompt (structure in program_prompt.py)."""
import textwrap

from program_prompt import duel, single

OBJ = "ball"

OBSERVATION = """**Observation** (`observe`): a PNG of 2 rows x 4 columns of 640 x 480 tiles. Row 1 is a camera behind and above your
base line looking down the court, row 2 a camera at the side of the court (x < 0) looking along +x (your half on the
right); the columns are frames 40 ms apart, newest on the right, and the reply gives each frame's step and game time
(`view_steps`, `view_sim_times`) and `view_leg_ids` (a new id each time the ball is served or hit). There are no ball
coordinates: the ball is drawn enlarged, a yellow-green sphere of radius 9 cm centred on the ball's true position.
Yellow marks every 2 m outside the doubles side lines and every 1 m behind the base lines help to judge positions.
`game spec` gives both cameras' poses and intrinsics (pinhole, 45 degree vertical field of view, focal length
579.4 px, principal point at the tile centre). The replies also give your robot's state (`robot_base_xy`, `q_arm`,
`racket_pos`, `racket_normal`), the bounces you have heard (side and time, no position) and whether the ball is coming
to you."""

ACTION = """**Action** (`act`): the racket's state at contact, T seconds after the command takes effect: the head centre
(PX, PY, PZ), the string-face normal (NX, NY, NZ), pointing towards the incoming ball, the head velocity (VX, VY, VZ)
in m/s and, optionally, the base position at contact (BX, BY; default: the forehand stance, base = (PX - 0.62,
PY - 0.30)). Limits: 0 < T <= 5, |x| <= 6.5, -16 <= y <= -6, 0.1 <= z <= 2.4, speed <= 8 m/s. An act is accepted at
the next 10 ms control step and takes effect `timing.act_lead_steps` steps later (the reply's `took_effect`) while
the stroke is planned; it replaces the stroke under way. `move BX BY` sets the base's rest position, where the base
goes whenever no stroke is under way (back to home (0, -11.4) after each point); it and `act none` take effect at the
next step and count as acts. The base moves on rails over the back part of your half (|BX| <= 5.9,
-15.4 <= BY <= -7.6) at up to 4 m/s and 8 m/s^2; the arm under joint speed limits. The reply predicts how close the
stroke gets (`ik_residual`, `blade_error_m`, `normal_error_deg`, `speed_scale`, `racket_vel_delivered`, `base`). The
delivered state scatters by about 5 mm, 0.5 degrees and 2 %."""

TASK_ROBOT = """You control a simulated Franka Panda arm holding a tennis racket, on a base that slides on rails over the back part
of your half of a regulation singles court (see Action)."""

FORMAT = """**Win the match: first to 5 points; from 4:4 a player must lead by 2, and at 6:6 the next point wins.** The match
also ends after 400 racket hits or 40 points played (replayed lets included): then the player with more points wins,
and at equal points the player who won the last point."""

BOX = """the box changes every two points (right box twice, then left box twice, ...)"""

SINGLE_TASK = TASK_ROBOT + """ Across the net a computer opponent plays you; its level is `match.opponent_level` in
`game spec`. The opponent serves every point into your service box diagonally opposite; """ + BOX + """. """ + FORMAT
SINGLE_TASK = textwrap.fill(" ".join(SINGLE_TASK.split()), 118, break_long_words=False, break_on_hyphens=False)

SINGLE_COMMANDS = [
    ("game spec", "GET /spec", "cameras, slowdown, opponent level, limits"),
    ("game status", "GET /status", "the current state, no image"),
    ("game observe", "POST /observe {}", "the newest camera frames (`game` saves the image to a file and prints its path; HTTP: `observation.image_png_b64`) and the state"),
    ("game act T PX PY PZ NX NY NZ VX VY VZ [BX BY]", 'POST /act {"type":"act","t":T,"pos":[PX,PY,PZ],"normal":[NX,NY,NZ],"vel":[VX,VY,VZ],"base":[BX,BY]}', "a racket command (below); `base` is optional"),
    ("game move BX BY", 'POST /act {"type":"move","base":[BX,BY]}', "the base's rest position"),
    ("game act none", 'POST /act {"type":"none"}', "cancel; the arm returns to its ready pose"),
    ("game wait DT", 'POST /wait {"dt":DT}', "wait DT seconds (0 < DT <= 1)"),
    ("game start", "POST /start {}", "start the match"),
    ('game ready "WHY" "PLAN"', 'POST /ready {"why":"...","plan":"..."}', "hand in the review and resume"),
]

DEVIATIONS = """**Deviations from the official rules** (ITF Rules of Tennis 2026):
- One tie-break-style game to 5 points instead of games and sets (Rules 5-7); from 4:4 a lead of 2 is needed and at
  most 7 points are played (as in a tie-break, Rule 5 b, but shorter){extra}.
- The serve is a machine-like serve that you only receive; a serve that misses the box or touches the net is replayed
  (no service faults, Rules 19-22).
- Only the strings touch the ball: it passes through the frame, arm and base (Rule 24 i).
- The robot moves on rails over the back part of its half instead of anywhere."""

PLAY = """After the serve has bounced in your service box, or after your opponent's shot (which you may also hit before it
bounces), hit the ball once so that it passes over the net, directly or after touching its top edge, and first lands
inside your opponent's singles court (lines are in). You lose the point for returning the serve before it bounces, a
second bounce on your half, a ball into the net, or a ball that lands out or on your own half; your opponent loses it
for the same faults. A serve that misses the box or touches the net is a let: the point is replayed from the same side
with a new serve."""

SINGLE_RULES = textwrap.fill(" ".join((PLAY + """ The opponent never makes unforced errors and returns every ball it can
reach; higher levels react and run faster, reach further and hit faster, wider balls with more spin.""").split()), 118,
                             break_long_words=False, break_on_hyphens=False) + """

""" + DEVIATIONS.format(extra="")

PHYSICS = """Metres; the world frame from your side: x to your right, y towards the opponent, z up.
- Court surface z = 0; singles court |x| <= 4.115, |y| <= 11.885; service lines at |y| = 6.40. The net is the plane
  y = 0, its top 0.914 m at x = 0 rising linearly to 1.07 m at |x| = 5.029. Your half is y < 0.
- Robot: shoulder 0.88 m above the court; the racket head centre is 0.52 m beyond the flange; the strung face is an
  ellipse of half axes 0.13 m x 0.16 m. Contacts are comfortable 0.6-1.4 m high, about 0.6-0.8 m to the right of and
  0.2-0.4 m in front of the base. At contact the ball's centre is 3.35 cm (its radius) from the string plane.
- Ball: mass 57.7 g, radius 0.0335; gravity 9.81 m/s^2; drag `a = -0.0203 |v| v`; Magnus lift
  `a = 0.0370 C_L |v|^2 unit(w x v)` with `C_L = 1/(2 + 1/S)`, `S = 0.0335 |w| / |v|`; the spin w is constant in flight.
- Court bounce: the normal velocity reverses with restitution 0.76; friction (coefficient 0.6) acts on the ball's
  contact point until it rolls (the tangential impulse is the smaller of 0.6 x the normal impulse and what stops the
  sliding); the ball's moment of inertia is 0.55 m r^2.
- Net: a ball whose centre comes within its radius of the net's top edge bounces off the edge by the same law
  (restitution 0.3, friction 0.3) and play goes on; a ball that meets the net lower down stops there.
- Racket contact: the ball leaves as if the racket head moved 5 times faster than its delivered velocity
  (`V = 5 x` the head velocity). In the frame moving with V, with n the unit face normal towards the ball, the normal
  component reverses with restitution 0.82 (at the head centre, up to 25 % less towards the frame) and friction
  (coefficient 0.4) acts as in the court bounce. Without the friction: `v_out = v_in - 1.82 ((v_in - V)·n) n`."""

DUEL_TASK = TASK_ROBOT + """ Another agent controls an identical robot across the net; your seat (`A` or `B`) is in
`game spec`. A neutral serving machine, behind the base line of the player who does not receive, serves every point
into the receiver's service box diagonally opposite. The receiver changes every point, starting with
`match.first_player`; """ + BOX + """. """ + FORMAT + """ Both players receive this document."""
DUEL_TASK = textwrap.fill(" ".join(DUEL_TASK.split()), 118, break_long_words=False, break_on_hyphens=False)

DUEL_COMMANDS = [
    ("game spec", "GET /spec", "your seat, cameras, slowdown, limits"),
    ("game status", "GET /status", "the current state, no image"),
    ("game observe", "POST /observe {}", "the newest camera frames (`game` saves the image to a file and prints its path; HTTP: `observation.image_png_b64`) and the state"),
    ("game act T PX PY PZ NX NY NZ VX VY VZ [BX BY]", 'POST /act {"type":"act","t":T,"pos":[PX,PY,PZ],"normal":[NX,NY,NZ],"vel":[VX,VY,VZ],"base":[BX,BY]}', "a racket command (below); `base` is optional"),
    ("game move BX BY", 'POST /act {"type":"move","base":[BX,BY]}', "the base's rest position"),
    ("game act none", 'POST /act {"type":"none"}', "cancel; the arm returns to its ready pose"),
    ("game wait DT", 'POST /wait {"dt":DT}', "wait DT seconds (0 < DT <= 1)"),
    ("game start", "POST /start {}", "ready to start; play begins when both players have started"),
    ('game ready "WHY" "PLAN"', 'POST /ready {"why":"...","plan":"..."}', "hand in the review; play resumes when both have"),
]

DUEL_RULES = PLAY + """ The robot on the serving side cannot touch the serve.

""" + DEVIATIONS.format(extra="; the receiver changes every point")

DUEL_OBSERVATION = OBSERVATION + """ Both players see the game the same way: in each player's frame its own half is
y < 0 and its base's home is (0, -11.4)."""


def single_prompt():
    return single(title="Robot tennis: program play", task=SINGLE_TASK, obj=OBJ, url="http://sim:8000",
                  commands=SINGLE_COMMANDS, observation=OBSERVATION, action=ACTION, rules=SINGLE_RULES,
                  physics=PHYSICS)


def duel_prompt(start="30 minutes", review="300 seconds"):
    return duel(title="Robot tennis, two players: program play", task=DUEL_TASK, obj=OBJ,
                url="http://sim:8000/<your seat>", commands=DUEL_COMMANDS, observation=DUEL_OBSERVATION,
                action=ACTION, rules=DUEL_RULES, physics=PHYSICS, start=start, review=review)


if __name__ == "__main__":
    import sys
    print(duel_prompt() if sys.argv[1:] == ["duel"] else single_prompt())
