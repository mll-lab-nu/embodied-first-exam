"""Badminton: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py)."""
from common import DUEL_SLOWDOWNS, IMAGE, OFFICIAL_SLOWDOWNS, REVIEW_S, START_S
from badminton_prompt import RULEBOOK, RULEBOOK_URL, duel_prompt, single_prompt

# Three instance seeds per opponent level, from the wall-clock badminton tasks (MATCH_SEED of
# badminton-match[-l2]-wallclock-x10-interactive[-seed*]); tests/grade.py of the match task holds the same sets.
OFFICIAL_SEEDS = {1: [101, 111, 121], 2: [202, 212, 222]}

# The experiment's configurations (the same format as scripts/olympiad/tabletennis/spec.py).
EXPERIMENT = dict(
    single=dict(task="badminton-match-wallclock-program-standard", seeds=OFFICIAL_SEEDS, slowdowns=OFFICIAL_SLOWDOWNS),
    duel=dict(task="badminton-duel-wallclock-program-standard", seeds=[1, 2, 3], slowdowns=DUEL_SLOWDOWNS,
              first="FIRST_RECEIVER"),
)

_COMMON = ("one game to 5 points, a two-point lead from 4-4, at most 7 (Law 7: best of three to 21, cap 30); "
           "serves from the server's right or left service court by the server's score (10.1.1) into the diagonal "
           "court (9.1; outside it: a fault, the receiver's point, 13.1); net top 1.524 m (1.10); base 6 m/s, 20 m/s^2; "
           "point-mass shuttle: a crossing of the net plane below the top is a fault, net touch / reaching over the "
           "net (13.4) not judged; robots back home before every serve; 300 hits in the match end it after that point "
           "(the leader wins, if level the winner of the last point: no draws). The single-player task and the duel "
           "play by the same rules; only who serves differs")
RULES_SINGLE = (f"[{RULEBOOK}]({RULEBOOK_URL}). Deviations: the opponent serves every point (Law 10.3); " + _COMMON)
RULES_DUEL = (f"[{RULEBOOK}]({RULEBOOK_URL}). Deviations: a neutral machine on the server side's half serves every "
              "point and the receiver changes every point (Law 10.3); " + _COMMON)

TASKS = {
    "badminton-match-wallclock-program-standard": dict(
        source="badminton/match", shared="shared/badminton/sim", pins_to=["environment"], prompt=single_prompt,
        broadcast=True,
        readme=dict(
            benchmark="Embodied Agent Olympiad (badminton)",
            family="`badminton_match` / level, slowdown and seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the privileged reference player (true shuttle state through the oracle-only endpoint, sent as ordinary acts); checked valid at L1-L2 and x1-x20",
            budget_s=7200, base_image=IMAGE,
            task="""A simulated Franka Panda arm on a sliding base, holding a badminton racket, plays a singles match (first to 5 points, two-point lead from 4-4, at most 7,
rally scoring) against a scripted computer opponent, in real time slowed by a factor S. The shuttle is a point mass
with quadratic drag and no bounce. The agent sees the shuttle only through two cameras and may write a player program
that observes and acts on its own; it may fix and restart the program at any time and reviews after every point. The
prompt follows the general program-play structure (`scripts/olympiad/program_prompt.py`) with badminton's sections
(`scripts/olympiad/badminton/badminton_prompt.py`).""",
            difficulty=f"""Set at run time: opponent level 1-2 (`RCB_LEVEL`) and slowdown S (`RCB_SLOWDOWN`; 1 = real speed). Official
configurations: levels with seeds {OFFICIAL_SEEDS}, slowdowns {OFFICIAL_SLOWDOWNS}.""",
            reference="""`solution/solve.sh` runs the privileged reference player: with `RCB_PLAYER_MODE=oracle` (set by the runner for
`oracle`/`nop` only) the service exposes `POST /oracle` with the true shuttle state and a reference decision computed
on an exact copy of the match (`environment/sim/oracle_ref.py`); the decision is sent as an ordinary `act` and pays
every wall-clock cost. In model mode the endpoint answers 403.""",
            verification="""The `sim` service records the match and replays it in a fresh process from the logged acts; a separate verifier
(`tests/grade.py`, no network) writes `success` = 1 iff the agent wins a valid match (deterministic replay; no
simulator, model-API or metering failure). `reward.json` also reports `level`, `seed`, `slowdown`, `official_config`,
`valid_trial` and `technical_failure`.""",
            details=f"""| | |
|---|---|
| Rules | {RULES_SINGLE} |
| Parameters | `RCB_LEVEL` (1-2, default 1), `RCB_SLOWDOWN` (default 20), `RCB_SEED` (default 101) |
| Run | `scripts/olympiad/run_single.sh --task badminton-match-wallclock-program-standard --agent opus\\|astra\\|oracle\\|nop --level L --slowdown S --seed N` |
| Act lead | an act takes effect `timing.act_lead_steps` = ceil(0.4 s / (0.01 S)) control steps after it arrives (the stroke planner's time) |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |""")),
    "badminton-duel-wallclock-program-standard": dict(
        source="badminton/duel", shared="shared/badminton/sim", pins_to=["environment/seat"], extra_scene="scene_extra",
        broadcast=True,
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes", review=f"{REVIEW_S} seconds"),
        readme=dict(
            benchmark="Embodied Agent Olympiad (badminton, two players)",
            family="`badminton_duel` / slowdown, seed and first receiver chosen at run time",
            oracle="full",
            oracle_evidence="solution/: a camera-only reference player for either seat (images, replies and documented physics only); two of them play valid matches with real rallies (checked at x10 and x20, both first receivers)",
            budget_s=7200, base_image=IMAGE,
            task="""Two agents each control an identical simulated Franka Panda arm on a sliding base, holding a badminton racket, on
the two halves of one court, and play a singles match (first to 5 points, two-point lead from 4-4, at most 7, rally scoring) in a shared world running in
real time, slowed by a factor S. Each may write a player program that observes and acts on its own, fix it at any time
and review after every point (300 s, else forfeit).""",
            difficulty=f"""Set at run time: slowdown S (`RCB_SLOWDOWN`; official {DUEL_SLOWDOWNS}), seed (`DUEL_SEED`: the serves and the
execution scatter) and first receiver (`FIRST_RECEIVER`, A or B). Play both seat orders for a fair comparison.""",
            reference="""`solution/` holds a camera-only reference player for either seat (`oracle_play.py`, `cam_player.py`):
it detects the orange cork in both cameras, triangulates it, fits the documented drag model, picks a contact the base
can reach and a target (deep corners or short), and turns the launch velocity into the racket state with the contact
law; it corrects the command while the shuttle flies and uses the act reply to switch to another stroke when the arm
cannot deliver one. It uses only the seat's ordinary endpoints. With both seats `oracle` the match is valid.""",
            verification="""The `sim` service records the match and replays it in a fresh process from the logged acts; the verifier
(`tests/grade.py`, no network) checks the replay against the live state, joint targets and score. `success` = 1 iff the
match is valid (played out, or won by a review forfeit); the winner is `A_won` / `B_won`. `reward.json` also reports
`A_points` / `B_points`, `seed`, `slowdown`, `official_config`, `technical_failure` and `ready_forfeit`.""",
            details=f"""| | |
|---|---|
| Rules | {RULES_DUEL} |
| Parameters | `RCB_SLOWDOWN` (default 20), `DUEL_SEED` (default 1), `FIRST_RECEIVER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task badminton-duel-wallclock-program-standard --a opus\\|astra\\|oracle --b ... --slowdown S [--seed N] [--first A\\|B]` |
| Court | Both robots are the match task's robot; B's frame is the world turned 180 degrees about z, so each seat plays in the single-player frame (home (0, -4.0), its half y < 0) with the same cameras, prompt and act |
| Serve format | A neutral serving machine on the server side's half serves every point, 1 s after play resumes: from that side's right service court when that side's score is even, else from its left one (at (-+0.45, 2.3, 1.05) in the receiver's frame), a high deep or a short serve into the receiver's diagonal service court, seeded by `DUEL_SEED` and the point number (the match task's opponent serves). The receiver changes every point: `FIRST_RECEIVER` receives points 1, 3, 5, ... (a replayed point keeps its receiver). An unreturned serve in the service court is the server side's point; outside it, the receiver's (never seen); a serve into the net is replayed |
| Scoring | First to 5 points; from 4-4 a two-point lead is needed; the first to 7 wins (6-6: the next point wins) |
| Rally | The players hit in turn; a racket meets the shuttle only on its own half when it is that player's turn (no double hits). The shuttle landing in the court of the player to hit loses that player the point; out, into the net or on the hitter's own half loses the hitter the point. Both robots go back home in the ready pose before every serve |
| Base | The base moves up to 6 m/s and 20 m/s^2 (both tasks; the wall-clock engine had 3 m/s, 6 m/s^2). With the old base no drop with a flight under 1.1 s can be returned from anywhere on the half, so the receiver's corner drop off a high serve won every point (every oracle duel ended 5-4 to the first receiver); with the faster base a well-placed fast drop can still win, a slower one can be returned |
| Physics | Contacts are off in the badminton scene, so each robot runs in its own copy of the single-player model; the shuttle (point mass, quadratic drag) and the referee run once in the world frame; `scene/bm_duel.xml` (from `scripts/olympiad/badminton/mk_duel_scene.py`) only draws the game |
| Act lead | an act takes effect `timing.act_lead_steps` = ceil(0.4 s / (0.01 S)) control steps after it arrives; the seat's planner process plans it on an exact copy of the seat's robot |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / review | 30 minutes to start after the first player; 300 s per review, else forfeit |
| Generator | `scripts/olympiad/generate.py` |""")),
}


def _check_grader_sets():
    """The match grader's official sets must equal the ones above (they are written out in tests/grade.py)."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent / "match/tests/grade.py").read_text()
    vals = {t.targets[0].id: ast.literal_eval(t.value) for t in ast.parse(src).body
            if isinstance(t, ast.Assign) and isinstance(t.targets[0], ast.Name)
            and t.targets[0].id in ("OFFICIAL_SEEDS", "OFFICIAL_SLOWDOWNS")}
    assert vals == {"OFFICIAL_SEEDS": OFFICIAL_SEEDS, "OFFICIAL_SLOWDOWNS": OFFICIAL_SLOWDOWNS}, vals


_check_grader_sets()
