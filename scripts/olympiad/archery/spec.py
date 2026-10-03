"""Archery: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py)."""
import re
from pathlib import Path

from common import IMAGE, START_S
from archery_prompt import DUEL_RULES, RULEBOOK, SINGLE_DEVIATIONS, duel_prompt, single_prompt

HERE = Path(__file__).resolve().parent
PROTOCOL = "eai-standard-turn/1.0"
# Official configurations: the three seeds of the old tasks (archery-interactive[-seed2/3], ARCHERY_SEED)
OFFICIAL_SEEDS = [20260929, 2, 3]
OFFICIAL_DUEL_SEEDS = [1, 2, 3]          # each with FIRST_PLAYER A and B

EXPERIMENT = dict(
    single=dict(task="archery-program-standard", seeds={1: OFFICIAL_SEEDS}, slowdowns=None),
    duel=dict(task="archery-duel-program-standard", seeds=OFFICIAL_DUEL_SEEDS, slowdowns=None, first="FIRST_PLAYER"),
)


def rules_row(text):
    """README: the rulebook and the deviations (the prompt's list), one table row."""
    devs = text[text.index("Deviations from the official rules"):].split("\n- ")[1:]
    return f"| Rules | {RULEBOOK}. Deviations: " + " ".join(f"({i + 1}) {' '.join(d.split())}" for i, d in enumerate(devs)) + " |"
SUCCESS_LINE = 110                       # of 120, from the old task


def _graders_agree():
    """The graders carry their own copy of the official sets (they run in a sandbox without this file)."""
    g1 = (HERE / "single/tests/grade.py").read_text()
    g2 = (HERE / "duel/tests/grade.py").read_text()
    assert re.search(r"^OFFICIAL_SEEDS = (.*)$", g1, re.M).group(1) == repr(OFFICIAL_SEEDS), "single grader seeds"
    assert f'SUCCESS_MIN_TOTAL: "{SUCCESS_LINE}"' in (HERE / "single/environment/docker-compose.yaml").read_text()
    assert re.search(r"^OFFICIAL_DUEL_SEEDS = (.*)$", g2, re.M).group(1) == repr(OFFICIAL_DUEL_SEEDS), "duel grader seeds"


_graders_agree()

TASKS = {
    "archery-program-standard": dict(
        source="archery/single", shared="shared/archery/sim", pins_to=["environment"], prompt=single_prompt,
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (archery)",
            family="`archery_target` / seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: a reference archer from the camera images and the documented physics; it scores 115, 112 and 112 on the official seeds (success line 110)",
            budget_s=7200, base_image=IMAGE,
            task=f"""A target-archery round (World Archery rules, a short custom round) of 4 ends x 3 arrows at a World Archery 122 cm 10-ring face (50, 70, 70, 90 m) in a seeded,
gusty crosswind and headwind (MuJoCo scene, osmesa rendering; deterministic point-mass arrow with quadratic drag on the
air-relative velocity, Cd 1.5 per Miyazaki et al. 2013). Each arrow is `game shoot ELEV_DEG AZIM_DEG DRAW`; the agent
sees camera images only (archer's view with the windsocks, scope view, side view of a windsock, close-up of the face;
no coordinates, no wind numbers). It may write a program that reads the windsocks and the target in the images and
computes and sends its shots; it stays in the loop and reviews after every arrow. Success: a complete round with a total
of at least {SUCCESS_LINE} of 120 (as in the old task); the total is always reported and higher is better. The prompt
follows the general turn-based program-play structure (`scripts/olympiad/turn_prompt.py`, played alone) with archery's
sections (`scripts/olympiad/archery/archery_prompt.py`).""",
            difficulty=f"""Set at run time: the seed (`RCB_SEED`: the wind of every arrow and the release scatter). Reading the wind to about
1 m/s is needed for the success line: offline, an archer that knows the true wind scores about 114, one that reads it
within 1 m/s about 111, and one that ignores it about 92. Time: a 60-minute chess clock. Official configurations:
seeds {OFFICIAL_SEEDS}.""",
            reference="""`solution/solve.sh` runs a reference archer (`solution/archery_ref.py`) that uses only the camera images and the
documented physics: it fits the wind to where the windsocks' orange stripes appear in the archer's and side views, and
solves the ballistics for the gold centre at full draw.""",
            verification=f"""The `sim` service records the round; a fresh process replays the shots and must reproduce the state hash. A
separate verifier (`tests/grade.py`, no network) writes `success` = 1 iff the round is valid (deterministic replay; no
simulator, model-API or metering failure), complete and scores at least {SUCCESS_LINE}. `reward.json` also reports
`total`, the end scores, `seed`, `official_config`, `valid_trial`, `technical_failure` and `clock_forfeit`.""",
            details="""| | |
|---|---|
| Parameters | `RCB_SEED` (default 20260929) |
| Run | `scripts/olympiad/run_single.sh --task archery-program-standard --agent opus\\|astra\\|oracle\\|nop --level 1 --seed N` (no levels: `--level 1`) |
| Clock | 60 minutes from `game start` (reviews included); out of time = the round ends, the arrows not shot score M |
""" + rules_row(SINGLE_DEVIATIONS) + """
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |""")),
    "archery-duel-program-standard": dict(
        source="archery/duel", shared="shared/archery/sim", pins_to=["environment/seat"],
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes"),
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (archery, two players)",
            family="`archery_duel` / seed and first player chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the reference archer on either seat; oracle against oracle plays valid matches with either first player",
            budget_s=10800, base_image=IMAGE,
            task="""Two agents shoot the same round (4 ends x 3 arrows at 50, 70, 70, 90 m) on identical lanes: the same wind and the
same release scatter for the n-th arrow of either player. In each end one player shoots its 3 arrows, then the other;
the higher total wins, a tie goes to a shoot-off. Each may write a program that reads the windsocks and the target in
the camera images and computes and sends its shots, and reviews after every arrow.""",
            difficulty=f"""Set at run time: seed (`DUEL_SEED`: the winds and the scatter draws) and first player (`FIRST_PLAYER`: it shoots
first in ends 1 and 3, the other in ends 2 and 4). Official configurations: seeds {OFFICIAL_DUEL_SEEDS}, each with both
first players (play both orders for a fair comparison).""",
            reference="`solution/` holds the reference archer (`archery_ref.py`, camera images and the documented physics); with both seats `oracle` the match is valid (seat B's reference aims 3 mm left of seat A's, so that two references cannot tie forever).",
            verification="""The `sim` service records the match and a fresh process replays it (state hash); the verifier (`tests/grade.py`,
no network) writes `success` = 1 iff the match is valid (played out, or won on the other player's clock or
abandonment; deterministic replay; no simulator, metering or model-API failure); the winner is `A_won` / `B_won`
(shoot-offs repeat until the tie is broken). `reward.json` also reports both totals, the shoot-off, the clocks, `seed` and
`official_config`.""",
            details="""| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task archery-duel-program-standard --a opus\\|astra\\|oracle --b ... [--seed N] [--first A\\|B]` |
| Format | 4 ends x 3 arrows each; per end one player shoots 3 arrows, then the other (FIRST_PLAYER first in ends 1 and 3); higher total wins; tie: shoot-off arrows at 70 m (WA 12.5.2.2), one each, score then distance to the centre, repeated until the tie is broken; cumulative scoring as in compound match play (WA 12.1.4.3) |
| Turns and clocks | An action or review out of turn: HTTP 409; images only on one's own turn. One chess clock of 60 minutes per player, on its own turn (arrows and reviews); out of time = loss; a player who stops playing on its turn loses |
| Start | Up to 30 minutes after the first player's `start` (else the trial is incomplete) |
""" + rules_row(DUEL_RULES) + """
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Generator | `scripts/olympiad/generate.py` |""")),
}
