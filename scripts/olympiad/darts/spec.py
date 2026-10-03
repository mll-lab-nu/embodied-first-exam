"""Darts: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py)."""
import re
from pathlib import Path

from common import IMAGE, START_S
from darts_prompt import DEVIATIONS, DUEL_ORDER, RULEBOOK, SINGLE_ORDER, duel_prompt, single_prompt

HERE = Path(__file__).resolve().parent
PROTOCOL = "eai-standard-turn/1.0"
# Official configurations: three seeds per level, from the old tasks (darts-501-l<L>-interactive[-seed2/3], MATCH_SEED)
OFFICIAL_SEEDS = {1: [5011, 5012, 5013], 2: [5021, 5022, 5023], 3: [5031, 5032, 5033], 4: [5041, 5042, 5043]}
OFFICIAL_DUEL_SEEDS = [1, 2, 3]          # each with FIRST_PLAYER A and B

EXPERIMENT = dict(
    single=dict(task="darts-501-program-standard", seeds=OFFICIAL_SEEDS, slowdowns=None),
    duel=dict(task="darts-duel-program-standard", seeds=OFFICIAL_DUEL_SEEDS, slowdowns=None, first="FIRST_PLAYER"),
)


def rules_row(order):
    """README: the rulebook and the deviations, one table row."""
    devs = DEVIATIONS.format(order=order).split("\n- ")[1:]
    return f"| Rules | {RULEBOOK}. Deviations: " + " ".join(f"({i + 1}) {' '.join(d.split())}" for i, d in enumerate(devs)) + " |"


def _graders_agree():
    """The graders carry their own copy of the official sets (they run in a sandbox without this file)."""
    g1 = (HERE / "single/tests/grade.py").read_text()
    g2 = (HERE / "duel/tests/grade.py").read_text()
    assert re.search(r"^OFFICIAL_SEEDS = (.*)$", g1, re.M).group(1) == repr(OFFICIAL_SEEDS), "single grader seeds"
    assert re.search(r"^OFFICIAL_DUEL_SEEDS = (.*)$", g2, re.M).group(1) == repr(OFFICIAL_DUEL_SEEDS), "duel grader seeds"


_graders_agree()

TASKS = {
    "darts-501-program-standard": dict(
        source="darts/single", shared="shared/darts/sim", pins_to=["environment"], prompt=single_prompt,
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (darts)",
            family="`darts_501` / level and seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: a reference player from the camera images and the documented physics; checked valid at L1-L4, wins all 12 official configurations (offline check)",
            budget_s=7200, base_image=IMAGE,
            task="""Best of 3 legs of 501 double-out (3 darts per visit, bust rule; WDF rules) against a deterministic scripted thrower
that throws first in legs 1 and 3 (the agent in leg 2) and aims with the optimal-aim policy for its own scatter (Tibshirani et al. 2011, extended to minimum expected
visits to check out). A regulation board in a MuJoCo scene (osmesa rendering); the dart flies under gravity and
quadratic drag whose constant is not given. Each dart is a release command (`game throw YAW PITCH SPEED`) with
published seeded scatter; the agent sees camera images only (thrower's view, side view with its last dart's path,
board close-up) and hears the caller's calls. It may write a program that measures its darts in the images and computes
and sends its throws; it stays in the loop and reviews after every dart. The prompt follows the general turn-based
program-play structure (`scripts/olympiad/turn_prompt.py`) with darts' sections (`scripts/olympiad/darts/darts_prompt.py`).""",
            difficulty=f"""Set at run time: opponent level 1-4 (`RCB_LEVEL`; its execution scatter shrinks from about 3 times the agent's
at L1 to about 1.1 times at L4) and seed (`RCB_SEED`: the drag constant and both throwers' scatter draws). Time: a
60-minute chess clock on the agent's turn. Official configurations: levels with seeds {OFFICIAL_SEEDS}.""",
            reference="""`solution/solve.sh` runs a reference player (`solution/darts_ref.py`) that uses only the camera images and the
documented physics: it finds each of its darts in the board close-up by its flight colour, refits the drag constant
from its landing errors, and aims with the optimal-aim table for its own scatter (`solution/policy_player.json`).""",
            verification="""The `sim` service records the match; a fresh process replays the throws and must reproduce the state hash. A
separate verifier (`tests/grade.py`, no network) writes `success` = 1 iff the agent wins a valid match (deterministic
replay; no simulator, model-API or metering failure). `reward.json` also reports `level`, `seed`, `official_config`,
`valid_trial`, `technical_failure`, `clock_forfeit`, both players' legs and remaining scores and the agent's three-dart
average.""",
            details="""| | |
|---|---|
| Parameters | `RCB_LEVEL` (1-4, default 1), `RCB_SEED` (default 5011) |
| Run | `scripts/olympiad/run_single.sh --task darts-501-program-standard --agent opus\\|astra\\|oracle\\|nop --level L --seed N` |
| Clock | 60 minutes from `game start`, on the agent's turn only (reviews included); out of time = the match is lost |
""" + rules_row(SINGLE_ORDER) + """
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |""")),
    "darts-duel-program-standard": dict(
        source="darts/duel", shared="shared/darts/sim", pins_to=["environment/seat"],
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes"),
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (darts, two players)",
            family="`darts_duel` / seed and first player chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the reference player on either seat; oracle against oracle plays valid matches with either first player",
            budget_s=10800, base_image=IMAGE,
            task="""Two agents throw at one regulation board with identical release mechanisms (the same drag and the same scatter
draws): best of 3 legs of 501 double-out, alternate visits of 3 darts. Each may write a program that measures its
darts in the camera images and computes and sends its throws, and reviews after every dart.""",
            difficulty=f"""Set at run time: seed (`DUEL_SEED`: the drag constant and the scatter draws) and first player (`FIRST_PLAYER`: it
throws first in legs 1 and 3, the other in leg 2). Official configurations: seeds {OFFICIAL_DUEL_SEEDS}, each with
both first players (play both orders for a fair comparison).""",
            reference="`solution/` holds the reference player (`darts_ref.py`, camera images and the documented physics); with both seats `oracle` the match is valid.",
            verification="""The `sim` service records the match and a fresh process replays it (state hash); the verifier (`tests/grade.py`,
no network) writes `success` = 1 iff the match is valid (played out, or won on the other player's clock or
abandonment; deterministic replay; no simulator, metering or model-API failure); the winner is `A_won` / `B_won`.
`reward.json` also reports both seats' legs, remaining scores and clocks, `clock_forfeit`, `seed` and
`official_config`.""",
            details="""| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task darts-duel-program-standard --a opus\\|astra\\|oracle --b ... [--seed N] [--first A\\|B]` |
| Format | Best of 3 legs of 501 double-out; visits of 3 darts alternate; FIRST_PLAYER throws first in legs 1 and 3; visit cap 30 each per leg (lower remaining wins; tie: the second thrower) |
| Turns and clocks | An action or review out of turn: HTTP 409. One chess clock of 60 minutes per player, running on its own turn (its darts and reviews); out of time = loss; a player who stops playing on its turn loses |
| Start | Up to 30 minutes after the first player's `start` (else the trial is incomplete) |
""" + rules_row(DUEL_ORDER) + """
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Generator | `scripts/olympiad/generate.py` |""")),
}
