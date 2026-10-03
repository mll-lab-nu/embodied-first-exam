"""Baseball: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py)."""
from pathlib import Path

from common import DUEL_SLOWDOWNS, IMAGE, OFFICIAL_SLOWDOWNS, REVIEW_S, START_S
from baseball_prompt import duel_prompt, single_prompt

HERE = Path(__file__).resolve().parent
# Official configurations: the three instance seeds per pitcher level of the earlier wall-clock tasks (MATCH_SEED of
# tasks/baseball-batting-l{1..4}-wallclock-x10-interactive[-seed2|-seed3] on dev/chi).
OFFICIAL_SEEDS = {1: [301, 311, 321], 2: [302, 312, 322], 3: [303, 313, 323], 4: [304, 314, 324]}
for _grader, _text in ((HERE / "batting/tests/grade.py", repr(OFFICIAL_SEEDS)),
                       (HERE / "batting/tests/grade.py", f"OFFICIAL_SLOWDOWNS = {OFFICIAL_SLOWDOWNS!r}"),
                       (HERE / "duel/tests/grade.py", f"OFFICIAL_SLOWDOWNS = {DUEL_SLOWDOWNS!r}")):
    assert _text in _grader.read_text(), f"{_grader}: the official configurations differ from spec.py"

# The experiment's configurations (scripts/olympiad/run_round.py; same format as tabletennis/spec.py).
EXPERIMENT = dict(
    single=dict(task="baseball-batting-wallclock-program-standard", seeds=OFFICIAL_SEEDS, slowdowns=OFFICIAL_SLOWDOWNS),
    duel=dict(task="baseball-duel-wallclock-program-standard", seeds=[1, 2, 3], slowdowns=DUEL_SLOWDOWNS,
              first="FIRST_RECEIVER"),
)

RULES = """| | |
|---|---|
| Rulebook | MLB *Official Baseball Rules*, 2026 edition: https://mktg.mlbstatic.com/mlb/official-information/2026-official-baseball-rules.pdf |
| Field | as in 2.01: bases 90 ft (27.43 m) apart, the pitch released about 1.4 m in front of the rubber (18.44 m) |
| Count and zone | strike, ball, foul, strikeout, walk as in the Definitions of Terms, 5.05(b), 5.09(a) |
| Deviations | no base runners, runs or innings: each plate appearance scores the bases the batter reaches, no triples (5.05, 5.06); no batter's body, so no hit by pitch (5.05(b)(2)); fouls are never caught and there are no foul tips (5.09(a)(1), "Foul Tip"); fair/foul at the first landing point also for short balls ("Fair Ball"); the strike zone judged in one plane at fixed heights ("Strike Zone"); a uniform 100 m, 3 m high fence (2.01 Note: 325 ft at the lines, 400 ft to centre); fixed fielders without errors; a plate appearance reaching 15 pitches is an out (no limit in MLB) |"""

TASKS = {
    "baseball-batting-wallclock-program-standard": dict(
        source="baseball/batting", shared="shared/baseball/sim", pins_to=["environment"], prompt=single_prompt,
        broadcast=True,
        readme=dict(
            benchmark="Embodied Agent Olympiad (baseball batting)",
            family="`baseball_batting` / level, slowdown and seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: a scripted camera-only batter; checked valid at L1-L4 and x1-x20; passes the 4-base line at x2-x20 (5 home runs typical), at x1 its observations arrive too late to swing",
            budget_s=7200, base_image=IMAGE,
            task="""A simulated swing rig holding a wooden bat (robot `swing-rig`, not a Franka) bats through 5 plate appearances
against a scripted computer pitcher, in real time slowed by a factor S, and must collect at least 4 bases (walk or
single 1, double 2, home run 4). The agent sees the ball only through two cameras and may write a batting program that
observes and swings on its own; it may fix and restart the program at any time and reviews after every pitch. The
prompt follows the general program-play structure (`scripts/olympiad/program_prompt.py`) with baseball's sections
(`scripts/olympiad/baseball/baseball_prompt.py`).""",
            difficulty=f"""Set at run time: pitcher level 1-4 (`RCB_LEVEL`: L1 fastballs only, 34-36 m/s, mostly in the zone; L2 adds
changeups and curveballs and more balls; L3 faster fastballs, sliders, the edges of the zone; L4 the hardest fastballs,
overlapping speed bands, pitches chosen by the count) and slowdown S (`RCB_SLOWDOWN`; 1 = real speed). Official
configurations: levels with seeds {OFFICIAL_SEEDS}, slowdowns {OFFICIAL_SLOWDOWNS}.""",
            reference="""`solution/solve.sh` runs a scripted batter that uses only the camera images, the spec and the documented
ball and rig models (`solution/bat_player.py`: ball detection against a windup background, a fit of the release
velocity for each documented pitch type's spin, the swing geometry for a line drive; it takes pitches it predicts out
of the zone).""",
            verification="""The `sim` service records the game; a separate verifier (`tests/grade.py`, no network) checks the
fresh-process replay and writes `success` = 1 iff the agent collects at least 4 bases in a valid game (deterministic
replay; no simulator, model-API or metering failure). `reward.json` also reports `bases`, `level`, `seed`, `slowdown`,
`official_config`, `valid_trial` and `technical_failure`.""",
            details="""| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SLOWDOWN` (default 20), `RCB_SEED` (default 301) |
| Run | `scripts/olympiad/run_single.sh --task baseball-batting-wallclock-program-standard --agent opus\\|astra\\|oracle\\|nop --level L --slowdown S --seed N` |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |

## Rules
""" + RULES)),
    "baseball-duel-wallclock-program-standard": dict(
        source="baseball/duel", shared="shared/baseball/sim", pins_to=["environment/seat"],
        broadcast=True,
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes", review=f"{REVIEW_S} seconds"),
        readme=dict(
            benchmark="Embodied Agent Olympiad (baseball, two players)",
            family="`baseball_duel` / slowdown, seed and first batter chosen at run time",
            oracle="full",
            oracle_evidence="solution/: one scripted camera-only player (pitcher and batter) on both seats plays valid games (checked at x10 and x20, both first batters)",
            budget_s=7200, base_image=IMAGE,
            task="""Two agents play baseball against each other, pitcher against batter, in a shared world running in real time
slowed by a factor S. The plate appearances alternate between the seats: in each, one seat bats with the swing rig of
the single-player task and the other pitches, choosing every pitch's type, speed and target at the plate (within the
stated limits, with a seeded execution scatter). Each seat bats 5 plate appearances; the score is the bases each
collects as the batter (walk or single 1, double 2, home run 4; the single-player game's fielders). More bases wins;
level after 5 each: one more plate appearance each until decided, at most 5 times; then the winner of the last pitch wins (no draws). Each player may write a program that
observes and acts on its own, fix it at any time and review after every pitch (300 s, else forfeit).""",
            difficulty=f"""Set at run time: slowdown S (`RCB_SLOWDOWN`; official {DUEL_SLOWDOWNS}), seed (`DUEL_SEED`: the windups and
the pitch and swing scatter, the same sequence for both batters) and the seat that bats first (`FIRST_RECEIVER`, A or
B: the first to receive pitches; `match.first_player` in the spec). The format is symmetric (each seat bats and pitches equally often, with the same
random sequences); play both seat orders for a fair comparison.""",
            reference="""`solution/` holds the scripted reference player for either seat: as the pitcher a fixed pitch mix (two thirds
in the zone), as the batter the camera-only batter of the single-player task (`solution/bat_player.py`); with both
seats `oracle` the game is valid.""",
            verification="""The `sim` service records every command with the pitch and step at which it took effect; the verifier
(`tests/grade.py`, no network) checks the fresh-process replay (state hash, score, commands, steps); `success` = 1 iff
the game is valid (played out, or won by a review forfeit); the winner is `A_won` / `B_won` (exactly one; no draws;
`decided_by_last_pitch` = 1 if the last-resort rule decided). `reward.json` also reports `A_bases` / `B_bases` (= `A_points` / `B_points`), `official_config`,
`technical_failure` and `ready_forfeit`.""",
            details="""| | |
|---|---|
| Parameters | `RCB_SLOWDOWN` (default 20), `DUEL_SEED` (default 1), `FIRST_RECEIVER` (A or B: the seat that bats first) |
| Run | `scripts/olympiad/run_duel.sh --task baseball-duel-wallclock-program-standard --a opus\\|astra\\|oracle --b ... --slowdown S [--seed N] [--first A\\|B]` |
| Format | plate appearances alternate (A, B, A, ... or B, A, ...); 5 each; if level, extra pairs until decided, at most 5, then the winner of the last pitch wins (no draws); a plate appearance reaching 15 pitches is an out (no stalling with two-strike fouls) |
| Pitching | type (fastball, slider, changeup, curveball; fixed spins), speed within the type's band, target -0.6 <= x <= 0.6, 0.2 <= z <= 1.6 m; scatter 3 cm, 0.3 m/s; no pitch by the release = an automatic ball |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / review | 30 minutes to start after the first player; 300 s per review, else forfeit |
| Generator | `scripts/olympiad/generate.py` |

## Rules
""" + RULES + """
| Duel deviations | the pitcher only chooses the pitch (fixed windup and release point); no pitch by the release is an automatic ball, like a pitch-clock violation (5.07(c)); level bases after 5 extra pairs: the winner of the last pitch wins (MLB plays extra innings until decided, 7.01(b)) |""")),
}
