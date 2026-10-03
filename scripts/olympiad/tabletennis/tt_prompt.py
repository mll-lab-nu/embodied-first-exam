"""Table tennis: the sport-specific sections of the program-play prompt (structure in program_prompt.py)."""
from program_prompt import duel, single

OBJ = "ball"

OBSERVATION = """**Observation** (`observe`): a PNG of 2 rows x 4 columns of 480 x 360 tiles. Row 1 is a camera behind and above your
robot, row 2 a camera at the side of the table; the columns are frames 40 ms apart, newest on the right, and the reply
gives each frame's game time (`view_sim_times`). There are no ball coordinates: the ball is a small orange sphere (4 cm).
Yellow marks every 0.25 m along the table edges help to judge positions. `game spec` gives both cameras' poses and
intrinsics (pinhole, 45 degree vertical field of view, focal length 434.6 px, principal point at the tile centre)."""

PHYSICS = """Metres; the world frame from your side: x to your right, y towards the opponent, z up.
- Table top z = 0, |x| <= 0.7625, |y| <= 1.37; the net is at y = 0, top z = 0.1525. Your half is y < 0. Your robot's
  base is at (0, -1.75, 0), facing +y.
- Ball: radius 0.02; gravity 9.81 m/s^2; air drag about 0.13 |v| v; spin bends the flight by a few cm. A bounce keeps
  about 96 % of the vertical and 87 % of the horizontal speed. A ball takes about 0.6-0.9 s from the opponent to you.
- Reach: the blade can meet a ball whose centre is within about 0.85 m of the shoulder (0, -1.75, 0.33) and above
  z = 0.12.
- Blade: 15 x 15 cm. At contact its centre is 2.75 cm from the ball's centre along the face normal; a contact more
  than a few cm off the blade centre misses or mis-hits.
- Contact: with n the unit face normal, the ball leaves with about
  `v_out = v_paddle - 0.96((v_in - v_paddle)·n)n + (v_in - v_paddle) - ((v_in - v_paddle)·n)n`
  (the normal component reverses with restitution 0.96, the tangential component is kept). On measured contacts this
  is within about 0.3 m/s; the ball's spin causes most of the difference."""

FORMAT = """**Win the match: first to 5 points, but from 4:4 you must lead by 2; at 6:6 the next point wins (so 7 points
at most).**"""

SINGLE_TASK = """You control a simulated Franka Panda arm holding a table-tennis paddle. Across the net a computer opponent plays you;
its level is `match.opponent_level` in `game spec` (higher levels are stronger). The opponent serves every point.
""" + FORMAT

SINGLE_COMMANDS = [
    ("game spec", "GET /spec", "cameras, slowdown, opponent level, match format, limits"),
    ("game status", "GET /status", "the current state, no image"),
    ("game observe", "POST /observe {}", "the newest camera frames (`game` saves the image to a file; HTTP: `observation.image_png_b64`) and the state"),
    ("game act T PX PY PZ NX NY NZ VX VY VZ", 'POST /act {"type":"act","t":T,"pos":[PX,PY,PZ],"normal":[NX,NY,NZ],"vel":[VX,VY,VZ]}', "a paddle command (below)"),
    ("game act none", 'POST /act {"type":"none"}', "cancel; the arm returns to its ready pose"),
    ("game wait DT", 'POST /wait {"dt":DT}', "wait DT seconds (0 < DT <= 1)"),
    ("game start", "POST /start {}", "start the match"),
    ('game ready "WHY" "PLAN"', 'POST /ready {"why":"...","plan":"..."}', "hand in the review and resume"),
]

ACTION = """**Action** (`act`): the blade's state at contact, T seconds after the command takes effect: its centre (PX, PY, PZ),
its face normal (NX, NY, NZ), pointing towards the opponent, and its velocity (VX, VY, VZ) in m/s. Limits: 0 < T <= 2.5,
|x| <= 1.2, -2.5 <= y <= -0.5, 0 <= z <= 1.2, speed <= 8 m/s. A command takes effect at the next 10 ms control step
(the reply's `took_effect`) and replaces the stroke under way. The arm moves under joint speed limits; the reply
predicts how close the arm will get ({fields}). The delivered state scatters by about 4 mm, 0.6 degrees and 2 %."""

SINGLE_ACTION = ACTION.format(fields="`ik_residual`, `blade_error_m`, `normal_error_deg`, `speed_scale`, `paddle_vel_delivered`")

# The Rules text both tasks share word for word (the rules are the same; only the opponent and the serve differ).
RULES = """After exactly one bounce on your half, hit the ball once so that it lands on your opponent's half, directly or after
touching the net (the upper table edges count, the vertical sides do not); the same holds for your opponent's returns.
You lose the point for a volley, a double hit, two bounces, a miss, a ball that lands on your own half or out, the ball
touching your arm or handle while it is over or travelling towards your half, or your arm or paddle touching the
table, net or floor. A shot that passes a player's half without touching it is out, even if it then hits that player's
robot. A serve that touches the net or is irregular is a let: no point, the next serve. If the receiver makes 13 good
returns in a rally, the receiver wins the point (expedite rule). If 40 points (lets included) are played, the match
ends: the player ahead wins; at a level score, the player who won the last point wins."""

DEVIATIONS = """Deviations from the official rules (ITTF Laws of Table Tennis, ITTF Statutes 2025, chapter 2):
- One game to 5 points (lead by 2 from 4:4, at most 7) instead of a best-of-games match with games to 11 (2.11, 2.12).
{serve}
- Only the blade can strike the ball: the ball touching the handle or arm loses the point (2.5.7).
- A robot has no free hand: any contact of the arm or paddle with the table, net or floor loses the point
  (2.10.1.9-2.10.1.11).
- Any double hit loses the point, deliberate or not (2.10.1.7).
- The expedite rule (13 good returns by the receiver win the point) applies from the first point (2.15.4)."""

SINGLE_RULES = RULES + """
The opponent serves every point, so you are always the receiver. It returns every ball it can reach; higher levels
react faster, reach further and play faster, wider balls with more spin.

""" + DEVIATIONS.format(serve="""- The opponent serves every point with recorded real serves, and you always receive: the robot cannot toss the ball
  (2.6), so service does not alternate (2.13).""")

DUEL_TASK = """You control a simulated Franka Panda arm holding a table-tennis paddle. Another agent controls an identical robot
across the table; your seat (`A` or `B`) is in `game spec`. A neutral machine serves every point: the ball bounces
first on the server's half, then on the receiver's. The receiver changes every point; `match.first_receiver` in
`game spec` receives the first.
""" + FORMAT + """ Both players receive this document."""

DUEL_COMMANDS = [
    ("game spec", "GET /spec", "your seat, cameras, slowdown, match format, limits"),
    ("game status", "GET /status", "the current state, no image"),
    ("game observe", "POST /observe {}", "the newest camera frames (`game` saves the image to a file; HTTP: `observation.image_png_b64`) and the state"),
    ("game act T PX PY PZ NX NY NZ VX VY VZ", 'POST /act {"type":"act","t":T,"pos":[PX,PY,PZ],"normal":[NX,NY,NZ],"vel":[VX,VY,VZ]}', "a paddle command (below)"),
    ("game act none", 'POST /act {"type":"none"}', "cancel; the arm returns to its ready pose"),
    ("game wait DT", 'POST /wait {"dt":DT}', "wait DT seconds (0 < DT <= 1)"),
    ("game start", "POST /start {}", "ready to start; play begins when both players have started"),
    ('game ready "WHY" "PLAN"', 'POST /ready {"why":"...","plan":"..."}', "hand in the review; play resumes when both have"),
]

DUEL_ACTION = ACTION.format(fields="`ik_residual`, `speed_scale`, `joint_limited_steps`, `contact_joint_error`")

DUEL_RULES = RULES + """
Faults by both players at the same instant are a let. The robot that is not receiving is transparent to the serve until
it bounces on the receiver's half.

""" + DEVIATIONS.format(serve="""- A neutral machine serves every point with recorded real serves (the robots cannot toss the ball, 2.6); the receiver
  changes every point, as under the expedite system (2.13.3, 2.15.3).""")

DUEL_OBSERVATION = OBSERVATION + """ One observation at a time per seat (HTTP 429 otherwise).
Both players see the game the same way: in each player's frame its own base is at (0, -1.75, 0), facing +y."""


def single_prompt():
    return single(title="Robot table tennis: program play", task=SINGLE_TASK, obj=OBJ, url="http://sim:8000",
                  commands=SINGLE_COMMANDS, observation=OBSERVATION, action=SINGLE_ACTION, rules=SINGLE_RULES,
                  physics=PHYSICS)


def duel_prompt(start="30 minutes", review="300 seconds"):
    return duel(title="Robot table tennis, two players: program play", task=DUEL_TASK, obj=OBJ,
                url="http://sim:8000/<your seat>", commands=DUEL_COMMANDS, observation=DUEL_OBSERVATION,
                action=DUEL_ACTION, rules=DUEL_RULES, physics=PHYSICS, start=start, review=review)


if __name__ == "__main__":
    import sys
    print(duel_prompt() if sys.argv[1:] == ["duel"] else single_prompt())
