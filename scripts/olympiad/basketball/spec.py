"""Basketball shooting: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py)."""
import re
from pathlib import Path

from common import IMAGE, START_S
from basketball_prompt import DUEL_RULES, RULEBOOK, SINGLE_RULES, duel_prompt, single_prompt

HERE = Path(__file__).resolve().parent
PROTOCOL = "eai-standard-turn/1.0"
# Official configurations: the three seeds of the old tasks (basketball-shootout-interactive[-seed17/27], BB_SEED)
OFFICIAL_SEEDS = [7, 17, 27]
OFFICIAL_DUEL_SEEDS = [1, 2, 3]          # each with FIRST_PLAYER A and B

EXPERIMENT = dict(
    single=dict(task="basketball-shootout-program-standard", seeds={1: OFFICIAL_SEEDS}, slowdowns=None),
    duel=dict(task="basketball-duel-program-standard", seeds=OFFICIAL_DUEL_SEEDS, slowdowns=None, first="FIRST_PLAYER"),
)


def rules_row(text):
    """README: the rulebook and the deviations (the prompt's list), one table row."""
    devs = text[text.index("Deviations from the official rules"):].split("\n- ")[1:]
    return f"| Rules | {RULEBOOK}. Deviations: " + " ".join(f"({i + 1}) {' '.join(d.split())}" for i, d in enumerate(devs)) + " |"
SUCCESS_LINE = 6                         # makes of 10, from the old task


def _graders_agree():
    """The graders carry their own copy of the official sets (they run in a sandbox without this file)."""
    g1 = (HERE / "single/tests/grade.py").read_text()
    g2 = (HERE / "duel/tests/grade.py").read_text()
    assert re.search(r"^OFFICIAL_SEEDS = (.*)$", g1, re.M).group(1) == repr(OFFICIAL_SEEDS), "single grader seeds"
    assert f'MAKES_NEEDED: "{SUCCESS_LINE}"' in (HERE / "single/environment/docker-compose.yaml").read_text()
    assert re.search(r"^OFFICIAL_DUEL_SEEDS = (.*)$", g2, re.M).group(1) == repr(OFFICIAL_DUEL_SEEDS), "duel grader seeds"


_graders_agree()

TASKS = {
    "basketball-shootout-program-standard": dict(
        source="basketball/single", shared="shared/basketball/sim", pins_to=["environment"], prompt=single_prompt,
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (basketball shooting)",
            family="`basketball_shootout` / seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: a reference shooter from the camera images and the documented physics; it makes 6, 7 and 4 of 10 on the official seeds 7, 17, 27 (success line 6)",
            budget_s=7200, base_image=IMAGE,
            task=f"""A simulated Franka Panda launcher on a 1 m pedestal takes 10 shots, two from each of five spots (mid-range to beyond the
three-point line; 1 point per make; NBA court markings), with a static defender between it and the hoop (MuJoCo, osmesa rendering; ball with drag and
Magnus force; rim, backboard and floor contacts). Each shot is `game shoot ANGLE SPEED SPIN YAW`; the agent sees
camera images only (two cameras on the shooter, two on the court; no hoop, ball or spot coordinates) and a picture
strip of every shot. It may write a program that finds the hoop in the images and computes and sends its shots; it
stays in the loop and reviews after every shot. Success: at least {SUCCESS_LINE} makes of 10 (as in the old task); the
makes are always reported and more is better. Unlike the old task, thinking costs no simulated time: the defender
stands still and there is no shot clock (program play times the agent with the chess clock instead). The prompt
follows the general turn-based program-play structure (`scripts/olympiad/turn_prompt.py`, played alone) with
basketball's sections (`scripts/olympiad/basketball/basketball_prompt.py`).""",
            difficulty=f"""Set at run time: the seed (`RCB_SEED`: the five spots, the shooter's heading offsets of 4-9 degrees and the
release scatter). Makes need the speed right to 1-2 % and the direction to about 1 degree, so the hoop must be located
precisely from the images. Time: a 60-minute chess clock. Official configurations: seeds {OFFICIAL_SEEDS}.""",
            reference="""`solution/solve.sh` runs a reference shooter (`solution/bb_ref.py`) that uses only the camera images and the
documented physics: it finds the rim in the zoom camera, turns its centre into the hoop's bearing and distance with
the camera pose from `game spec`, solves the documented flight for the release speed at 54 degrees, and corrects the
second shot from a spot after a miss.""",
            verification=f"""The `sim` service records the shootout; a fresh process replays the shots and must reproduce the state hash. A
separate verifier (`tests/grade.py`, no network) writes `success` = 1 iff the shootout is valid (deterministic replay;
no simulator, model-API or metering failure), complete and has at least {SUCCESS_LINE} makes. `reward.json` also reports
`made`, the result counts, `seed`, `official_config`, `valid_trial`, `technical_failure` and `clock_forfeit`.""",
            details="""| | |
|---|---|
| Parameters | `RCB_SEED` (default 7) |
| Run | `scripts/olympiad/run_single.sh --task basketball-shootout-program-standard --agent opus\\|astra\\|oracle\\|nop --level 1 --seed N` (no levels: `--level 1`) |
| Clock | 60 minutes from `game start` (reviews included); out of time = the round ends, the shots not taken are misses |
""" + rules_row(SINGLE_RULES) + """
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |""")),
    "basketball-duel-program-standard": dict(
        source="basketball/duel", shared="shared/basketball/sim", pins_to=["environment/seat"],
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes"),
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (basketball shooting, two players)",
            family="`basketball_duel` / seed and first player chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the reference shooter on either seat; oracle against oracle plays valid matches with either first player",
            budget_s=10800, base_image=IMAGE,
            task="""Two agents each control a simulated Franka Panda launcher on identical courts: the same five spots and headings,
the same release scatter for the n-th shot of either player. Five rounds, one per spot: one player takes its 2 shots,
then the other; the most makes wins, a tie goes to extra shots. Each may write a program that finds the hoop in the
camera images and computes and sends its shots, and reviews after every shot.""",
            difficulty=f"""Set at run time: seed (`DUEL_SEED`: the spots, headings and scatter draws) and first player (`FIRST_PLAYER`: it
shoots first in rounds 1, 3 and 5). Official configurations: seeds {OFFICIAL_DUEL_SEEDS}, each with both first players
(play both orders for a fair comparison).""",
            reference="`solution/` holds the reference shooter (`bb_ref.py`, camera images and the documented physics); with both seats `oracle` the match is valid (seat B's reference shoots 1 % faster and 0.3 degrees left of seat A's, so that two references meeting the same scatter do not tie every extra pair).",
            verification="""The `sim` service records the match and a fresh process replays it (state hash); the verifier (`tests/grade.py`,
no network) writes `success` = 1 iff the match is valid (played out, or won on the other player's clock or
abandonment; deterministic replay; no simulator, metering or model-API failure); the winner is `A_won` / `B_won`
(exactly one of them; a match level after 30 extra pairs goes to the player with more chess-clock time left). `reward.json` also reports both players' makes, the extra pairs, the clocks, `seed` and
`official_config`.""",
            details="""| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task basketball-duel-program-standard --a opus\\|astra\\|oracle --b ... [--seed N] [--first A\\|B]` |
| Format | Five rounds, one per spot; per round one player takes 2 shots, then the other (FIRST_PLAYER first in rounds 1, 3, 5); most makes wins; tie: pairs of extra shots (one each, FIRST_PLAYER first, spots 1, 2, ... 5, 1, ...) until one pair differs; safety cap of 30 tied pairs, then the player with more chess-clock time left wins (no draws) |
| Turns and clocks | An action or review out of turn: HTTP 409; images only on one's own turn. One chess clock of 60 minutes per player, on its own turn (shots and reviews); out of time = loss; a player who stops playing on its turn loses |
| Start | Up to 30 minutes after the first player's `start` (else the trial is incomplete) |
""" + rules_row(DUEL_RULES) + """
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Generator | `scripts/olympiad/generate.py` |""")),
}
