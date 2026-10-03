"""Table tennis: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py)."""
from common import DUEL_SLOWDOWNS, IMAGE, OFFICIAL_SLOWDOWNS, REVIEW_S, START_S
from tt_prompt import duel_prompt, single_prompt

OFFICIAL_SEEDS = {1: [101, 111, 121], 2: [202, 212, 222], 3: [303, 313, 323], 4: [404, 414, 424]}

# The experiment configuration every sport's spec.py exports (read by the run scripts and run_round.py): the task names,
# the official seeds per level (levels: [1] for a sport without opponent levels), the official slowdowns (None for
# turn-based sports), the duel seeds and the variable that says who starts the duel.
RULEBOOK = ("ITTF Laws of Table Tennis (ITTF Statutes 2025, chapter 2, effective 1 January 2025): "
            "https://db.ittf.com/sites/default/files/public/2025-02/ITTF_Statutes_2025_tracked_changes_version.pdf")
SHARED = ("a return may touch the net (2.7.1); a serve that touches the net is a let (2.9.1.1; the recorded serves clear "
          "the net by >= 3.9 cm); a shot that passes a player's half and then hits that player's robot is out, contact over "
          "or towards a robot's half is obstruction (2.10.1.4, 2.10.1.6); the expedite rule applies from the first point: the "
          "receiver's 13th good return in a rally wins it the point (2.15.4), which bounds every rally; the match always has "
          "a winner: the format caps it at 7 points, and at the guard of 40 points (lets included, never reached in "
          "practice) the player ahead wins, at a level score the player who won the last point.")
DEV_FORMAT = "one game to 5 points, lead by 2 from 4:4, at 6:6 the next point wins (instead of best-of games to 11, 2.11, 2.12)"
DEV_ROBOT = ("only the blade can strike, the ball touching the handle or arm loses (2.5.7); no free hand: any arm or paddle "
             "contact with the table, net or floor loses (2.10.1.9-11); any double hit loses, deliberate or not (2.10.1.7)")
EXPERIMENT = dict(
    single=dict(task="tabletennis-match-wallclock-program-standard", seeds=OFFICIAL_SEEDS, slowdowns=OFFICIAL_SLOWDOWNS),
    duel=dict(task="tabletennis-duel-wallclock-program-standard", seeds=[1, 2, 3], slowdowns=DUEL_SLOWDOWNS,
              first="FIRST_RECEIVER"),
)

TASKS = {
    "tabletennis-match-wallclock-program-standard": dict(
        source="tabletennis/match", shared="shared/tabletennis/sim", pins_to=["environment"], prompt=single_prompt,
        broadcast=True,
        readme=dict(
            benchmark="Embodied Agent Olympiad (table tennis)",
            family="`tabletennis_match` / level, slowdown and seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: a scripted camera-only player; checked valid at L1-L4 and x1-x20, wins L1 (it can lose at L2-L4)",
            budget_s=7200, base_image=IMAGE,
            task="""A simulated Franka Panda arm with a table-tennis paddle plays a match (first to 5 points; from 4:4 a lead of 2
is needed, at 6:6 the next point wins: the duel's rules) against a scripted computer opponent, in real time slowed by a factor S. The agent sees the ball only through two cameras and may write a
player program that observes and acts on its own; it may fix and restart the program at any time and reviews after
every point. The prompt follows the general program-play structure (`scripts/olympiad/program_prompt.py`) with table
tennis' sections (`scripts/olympiad/tabletennis/tt_prompt.py`).""",
            difficulty=f"""Set at run time: opponent level 1-4 (`RCB_LEVEL`) and slowdown S (`RCB_SLOWDOWN`; 1 = real speed). Official
configurations: levels with seeds {OFFICIAL_SEEDS}, slowdowns {OFFICIAL_SLOWDOWNS}.""",
            reference="""`solution/solve.sh` runs a scripted player that uses only the camera images and the documented geometry
(`solution/oracle_play.py`).""",
            verification="""The `sim` service records the match; a separate verifier (`tests/grade.py`, no network) replays it and writes
`success` = 1 iff the agent wins a valid match (deterministic replay; no simulator, model-API or metering failure).
`reward.json` also reports `level`, `seed`, `slowdown`, `official_config`, `valid_trial` and `technical_failure`.""",
            details=f"""| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SLOWDOWN` (default 20), `RCB_SEED` (default 101) |
| Rules | {RULEBOOK}. The same rules as the duel (only the opponent and the serve differ): {SHARED} Deviations: {DEV_FORMAT}; the opponent serves every point with recorded real serves and the agent always receives (the robot cannot toss the ball, 2.6; service cannot alternate, 2.13); {DEV_ROBOT} |
| Run | `scripts/olympiad/run_single.sh --agent opus\\|astra\\|oracle\\|nop --level L --slowdown S [--seed N]` |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |""")),
    "tabletennis-duel-wallclock-program-standard": dict(
        source="tabletennis/duel", shared="shared/tabletennis/sim", pins_to=["environment/seat"], extra_scene="scene_extra",
        broadcast=True,
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes", review=f"{REVIEW_S} seconds"),
        readme=dict(
            benchmark="Embodied Agent Olympiad (table tennis, two players)",
            family="`tabletennis_duel` / slowdown, seed and first receiver chosen at run time",
            oracle="full",
            oracle_evidence="solution/: two scripted camera-only players play valid matches (checked at x10 and x20)",
            budget_s=7200, base_image=IMAGE,
            task="""Two agents each control a simulated Franka Panda arm with a table-tennis paddle and play a match (first to 5
points; from 4:4 a lead of 2 is needed, at 6:6 the next point wins) in a shared world running in real time, slowed by a
factor S; a neutral machine serves and the receiver changes every point. Each may write a player program that observes
and acts on its own, fix it at any time and review after every point (300 s, else forfeit).""",
            difficulty=f"""Set at run time: slowdown S (`RCB_SLOWDOWN`; official {DUEL_SLOWDOWNS}), seed (`DUEL_SEED`) and first receiver
(`FIRST_RECEIVER`). Play both seat orders for a fair comparison.""",
            reference="`solution/` holds the scripted reference player; with both seats `oracle` the match is valid.",
            verification="""The `sim` service records the match and the verifier (`tests/grade.py`, no network) replays it; `success` = 1
iff the match is valid (played out, or won by a review forfeit); the winner is `A_won` / `B_won`. `reward.json` also
reports both seats' points, `official_config`, `technical_failure` and `ready_forfeit`.""",
            details=f"""| | |
|---|---|
| Parameters | `RCB_SLOWDOWN` (default 20), `DUEL_SEED` (default 1), `FIRST_RECEIVER` (A or B) |
| Rules | {RULEBOOK}. The same rules as the single-player task: {SHARED} Deviations: {DEV_FORMAT}; a neutral machine serves recorded real serves, the receiver changes every point (2.6, 2.13.3, 2.15.3); {DEV_ROBOT} |
| Run | `scripts/olympiad/run_duel.sh --a opus\\|astra\\|oracle --b ... --slowdown S [--seed N] [--first A\\|B]` |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / review | 30 minutes to start after the first player; 300 s per review, else forfeit |
| Generator | `scripts/olympiad/generate.py` |""")),
}
