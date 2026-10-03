"""Tennis: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py)."""
import re
from pathlib import Path

from common import DUEL_SLOWDOWNS, IMAGE, OFFICIAL_SLOWDOWNS, REVIEW_S, START_S
from tennis_prompt import duel_prompt, single_prompt

HERE = Path(__file__).resolve().parent
# Three seeds per level, those of the earlier tennis wall-clock tasks (MATCH_SEED of tennis-match-l*-wallclock-x10-
# interactive[-seed2|-seed3] on dev/chi). L4 has 424/434, not 414.
OFFICIAL_SEEDS = {1: [101, 111, 121], 2: [202, 212, 222], 3: [303, 313, 323], 4: [404, 424, 434]}

# the graders carry the official sets as constants: keep them equal to this file
_g = (HERE / "match/tests/grade.py").read_text()
assert f"OFFICIAL_SEEDS = {OFFICIAL_SEEDS!r}" in _g and f"OFFICIAL_SLOWDOWNS = {OFFICIAL_SLOWDOWNS!r}" in _g, \
    "tennis/match/tests/grade.py: official configurations differ from spec.py"
if (HERE / "duel/tests/grade.py").exists():
    assert re.search(rf"OFFICIAL_SLOWDOWNS\s*=\s*{re.escape(repr(DUEL_SLOWDOWNS))}", (HERE / "duel/tests/grade.py").read_text()), \
        "tennis/duel/tests/grade.py: official slowdowns differ from common.DUEL_SLOWDOWNS"

# The experiment's configurations (format of scripts/olympiad/tabletennis/spec.py).
EXPERIMENT = dict(
    single=dict(task="tennis-match-wallclock-program-standard", seeds=OFFICIAL_SEEDS, slowdowns=OFFICIAL_SLOWDOWNS),
    duel=dict(task="tennis-duel-wallclock-program-standard", seeds=[1, 2, 3], slowdowns=DUEL_SLOWDOWNS,
              first="FIRST_RECEIVER"),
)

RULEBOOK = "ITF Rules of Tennis 2026 (English), https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf"
DEVIATIONS = ("one tie-break-style game to 5 points instead of games and sets (Rules 5-7): from 4:4 a lead of 2 is needed, "
              "at most 7 points (tie-break-like, Rule 5 b){extra}; the serve is a machine-like serve the player only "
              "receives, and a serve that misses the box or touches the net is replayed (no service faults, Rules "
              "19-22); only the strings touch the ball, "
              "it passes through the frame, arm and base (Rule 24 i); the robot moves on rails over the back part of its "
              "half. Aligned: volleys are legal except on the serve (Rule 24 e), the serve must land in the service box "
              "diagonally opposite (Rule 17) else it is replayed, a rally ball that touches the net's top edge and lands in the correct "
              "court is good (net cord, Rule 25 a) while a serve touching the net is a let (Rule 22 a), lines are in "
              "(Rule 12)")

TASKS = {
    "tennis-match-wallclock-program-standard": dict(
        source="tennis/match", shared="shared/tennis/sim", pins_to=["environment"], prompt=single_prompt,
        broadcast=True,
        readme=dict(
            benchmark="Embodied Agent Olympiad (tennis)",
            family="`tennis_match` / level, slowdown and seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: a scripted camera-only player; checked valid at L1-L4 and x1-x20",
            budget_s=7200, base_image=IMAGE,
            task="""A simulated Franka Panda arm on an x-y rail base, holding a tennis racket, plays a singles match (first to 5
points, from 4:4 by 2, at most 7; the opponent serves every point; the same rules as the duel) against a scripted computer opponent on a regulation court, in real time
slowed by a factor S. The ball has drag, Magnus lift and hard-court bounce and racket impact laws. The agent sees the
ball only through two cameras and may write a player program that observes and acts on its own; it may fix and
restart the program at any time and reviews after every point. The prompt follows the general program-play structure
(`scripts/olympiad/program_prompt.py`) with tennis' sections (`scripts/olympiad/tennis/tennis_prompt.py`).""",
            difficulty=f"""Set at run time: opponent level 1-4 (`RCB_LEVEL`) and slowdown S (`RCB_SLOWDOWN`; 1 = real speed). Official
configurations: levels with seeds {OFFICIAL_SEEDS}, slowdowns {OFFICIAL_SLOWDOWNS}. An act takes effect
ceil(0.5 s / (0.01 S s)) control steps after it is accepted (50 at x1, 5 at x10), so small S leave little time.""",
            reference="""`solution/solve.sh` runs a scripted player that uses only the camera images, the robot state in the replies
and the documented geometry and physics (`solution/oracle_play.py`, `solution/tn_player.py`: ball detection, a
least-squares flight fit through the bounce, contact choice, the racket face from the contact law).""",
            verification="""The `sim` service records the match; a fresh process replays it from the logged commands (recomputing every
stroke plan) and must reproduce the score, the final state hash and every joint target. A separate verifier
(`tests/grade.py`, no network) writes `success` = 1 iff the agent wins a valid match (deterministic replay; no
simulator, model-API or metering failure). `reward.json` also reports `level`, `seed`, `slowdown`, `official_config`,
`valid_trial` and `technical_failure`.""",
            details=f"""| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SLOWDOWN` (default 20), `RCB_SEED` (default 101) |
| Run | `scripts/olympiad/run_single.sh --task tennis-match-wallclock-program-standard --agent opus\\|astra\\|oracle\\|nop --level L --slowdown S --seed N` |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Format | The duel's rules, format and limits: first to 5 points, from 4:4 a lead of 2, at 6:6 the next point wins (at most 7); volleys except on the serve; net cord; a serve that misses the box or touches the net is replayed with a new serve from the same half; the match also ends after 400 racket hits (both players) or 40 points played, the player ahead winning, at equal points the winner of the last point (no draws; `match_limit` in `reward.json`). The scripted opponent serves every point (`match.first_player` = opponent; the agent always receives), the box changing every two points (deuce, deuce, ad, ad, ...) as in the duel |
| Rules | {RULEBOOK}. Deviations: {DEVIATIONS.format(extra="")} |
| Origin | `tennis-match-l{{1..4}}-wallclock-x10-interactive[-seed2\\|-seed3]` (dev/chi): same court, ball, robot, stroke controller, opponent and replay; program-play act rule, one act in flight, the camera-only reference instead of the privileged one (its `/oracle/state` endpoint is removed) |
| Generator | `scripts/olympiad/generate.py` |""")),
    "tennis-duel-wallclock-program-standard": dict(
        source="tennis/duel", shared="shared/tennis/sim", pins_to=["environment/seat"], extra_scene="scene_extra",
        broadcast=True,
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes", review=f"{REVIEW_S} seconds"),
        readme=dict(
            benchmark="Embodied Agent Olympiad (tennis, two players)",
            family="`tennis_duel` / slowdown, seed and first receiver chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the camera-only reference player in both seats plays valid matches (checked at x10 and x20, both first receivers)",
            budget_s=7200, base_image=IMAGE,
            task="""Two agents each control a simulated Franka Panda arm on an x-y rail base, holding a tennis racket, and play a
singles match (first to 5 points) on a regulation court in a shared world running in real time, slowed by a factor S.
Each may write a player program that observes and acts on its own, fix it at any time and review after every point
(300 s, else forfeit).""",
            difficulty=f"""Set at run time: slowdown S (`RCB_SLOWDOWN`; official {DUEL_SLOWDOWNS}), seed (`DUEL_SEED`: the machine's
serves and both seats' execution scatter) and the first receiver (`FIRST_RECEIVER`). Play both seat orders for a fair
comparison.""",
            reference="""`solution/` holds the single-player task's camera-only reference player (`tn_player.py`), which plays from
either seat in its own frame (`SEAT`); with both seats `oracle` the match is valid.""",
            verification="""The `sim` service records both robots' joint targets; a fresh process re-runs the match from them and must
reproduce the score, the points and the final state hash. The verifier (`tests/grade.py`, no network) writes `success`
= 1 iff the match is valid (played out, or won by a review forfeit); the winner is `A_won` / `B_won`. `reward.json`
also reports both seats' points (`A_points`, `B_points`), `official_config`, `technical_failure` and `ready_forfeit`.""",
            details=f"""| | |
|---|---|
| Parameters | `RCB_SLOWDOWN` (default 20), `DUEL_SEED` (default 1), `FIRST_RECEIVER` (A or B) |
| Run | `scripts/olympiad/run_duel.sh --task tennis-duel-wallclock-program-standard --a opus\\|astra\\|oracle --b ... --slowdown S [--seed N] [--first A\\|B]` |
| Format | Mirrored court: each player sees and acts in its own frame (its half y < 0, home (0, -11.4)), with the single-player cameras and stroke interface. A neutral serving machine (the single-player level-1 serve generator, seeded by `DUEL_SEED` and the points played) serves from behind the non-receiver's base line. The receiver changes every point (`FIRST_RECEIVER` = `match.first_player` receives points 1, 3, 5, ...); the box changes every two points (deuce, deuce, ad, ad, ...). First to 5 points; from 4:4 a lead of 2 is needed, at 6:6 the next point wins (at most 7). The serving-side robot cannot touch the serve; a serve out of the box or into the net is a let, replayed from the same half with a new serve. The match also ends after 400 racket hits or 40 points played (lets included): the player ahead wins, at equal points the winner of the last point (no draws; `match_limit` in `reward.json`, a result, not a technical failure). The rules, format and limits are those of the single-player game; only the opponent, the machine serve and the receiver rotation differ. Play both seat orders |
| Rules | {RULEBOOK}. Deviations: {DEVIATIONS.format(extra="; the receiver changes every point")} |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / review | 30 minutes to start after the first player; 300 s per review, else forfeit |
| Scene | `scene_extra/tn_duel.xml` (made by `scripts/olympiad/tennis/mk_duel_scene.py`: robot B mirrors robot A) |
| Generator | `scripts/olympiad/generate.py` |""")),
}
