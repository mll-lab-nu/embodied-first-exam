"""Curling: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py).

A turn-based (precision) sport: protocol eai-standard-turn/1.0, a 60-minute chess clock per player
(docs/benchmarks/olympiad-adding-a-precision-sport.md). It uses the eai-olympiad simulator image unchanged (MuJoCo
renders the cameras; the ice model is pure Python)."""
from curling_prompt import duel_prompt, single_prompt
from common import IMAGE, START_S

PROTOCOL = "eai-standard-turn/1.0"
OFFICIAL_SEEDS = {1: [7101, 7111, 7121], 2: [7202, 7212, 7222]}   # from curling-match[-l2]-interactive[-seed*] (dev/chi)
DUEL_SEEDS = [1, 2, 3]                                        # each with FIRST_PLAYER A and B


EXPERIMENT = dict(
    single=dict(task="curling-match-program-standard", seeds=OFFICIAL_SEEDS, slowdowns=None),
    duel=dict(task="curling-duel-program-standard", seeds=DUEL_SEEDS, slowdowns=None, first="FIRST_PLAYER"),
)

TASKS = {
    "curling-match-program-standard": dict(
        source="curling/match", shared="shared/curling/sim", pins_to=["environment"], prompt=single_prompt,
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (curling)",
            family="`curling_match` / level and seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: a scripted camera-only player; checked valid at L1 and L2 (it can win or lose)",
            budget_s=7200, base_image=IMAGE,
            task="""Curling against a scripted computer team: the agent skips the yellow team and throws every yellow stone (4 ends
of 5 stones per team, up to 3 extra ends while tied, then the player with more chess-clock time left wins; the opponent
has the hammer in end 1 and its clock never runs; the free guard
zone five-rock rule; DigitalCurling's FCV1 ice model with impulse collisions). It sees the
sheet only through a top-down house camera and an end camera (no stone coordinates) and throws by release speed,
angle and spin. Turn-based: a 60-minute chess clock runs only on the agent's turn (reviews included; clock out =
loss), and the agent reviews each of its throws. It may write a program that measures the images and sends its
throws. The prompt follows the general turn-based program-play structure (`scripts/olympiad/turn_prompt.py`) with
curling's sections (`scripts/olympiad/curling/curling_prompt.py`).""",
            difficulty=f"""Set at run time: opponent level 1-2 (`RCB_LEVEL`; level 2 throws about as precisely as the agent and also
plays off-centre and firm takeouts and guards) and the seed of the execution noise (`RCB_SEED`). Official
configurations: levels with seeds {OFFICIAL_SEEDS} (from the original `curling-match[-l2]-interactive` tasks).""",
            reference="""`solution/solve.sh` runs a scripted player that uses only the house camera image and the documented ice model
(`solution/curling_player.py`: stones from the grey granite bodies in the image, back-projected to the sheet; takeouts
of the opponent's shot stone and draws to free spots near the button, aimed with the documented ice law and checked
for a clear path; no takeouts through guards while the free guard zone rule is in force).""",
            verification="""The `sim` service records the match; a separate verifier (`tests/grade.py`, no network) checks the
fresh-process replay and writes `success` = 1 iff the agent wins a valid match (deterministic replay; no simulator,
model-API or metering failure; the clock did not run out). `reward.json` also reports `level`, `seed`,
`official_config`, `valid_trial`, `technical_failure`, `points_for` / `points_against`, `clock_tiebreak` and `clock_forfeit`.""",
            details="""| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SEED` (default: the level's first official seed, 7101 or 7202) |
| Rules | World Curling, The Rules of Curling and Rules of Competition, July 2025 (https://worldcurling.org/wp-content/uploads/2025/08/Rules-2025.pdf). Deviations: 4 ends of 5 stones per team (C5, R2(b): 8 or 10 ends of 8 stones); at most 3 extra ends, then the player with more chess-clock time left wins (R12(a): extra ends until a team scores); no sweeping (R8); the stone is released at the hack with the given speed, direction and spin (no delivery rules, R5); no no-tick rule (R7); single player: the opponent has the hammer in end 1 (a fixed handicap; R5(a): coin toss or last stone draw) |
| Run | `scripts/olympiad/run_single.sh --task curling-match-program-standard --agent opus\\|astra\\|oracle\\|nop --level L --seed N` |
| Time | chess clock: 60 minutes (`clock.total_s` in `/spec`), only on the agent's turn; review after each of its throws |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |""")),
    "curling-duel-program-standard": dict(
        source="curling/duel", shared="shared/curling/sim", pins_to=["environment/seat"],
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes"),
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (curling, two players)",
            family="`curling_duel` / seed and first player chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the scripted camera-only player on either seat; oracle against oracle plays valid matches (FIRST_PLAYER A and B)",
            budget_s=10800, base_image=IMAGE,
            task="""Two agents play the curling match rules (4 ends of 5 stones per team, up to 3 extra ends while tied, the free guard
zone rule, the FCV1 ice model)
against each other, seat A with the yellow stones and seat B with the red ones, each from its own container through the
same cameras and throw interface. The stones alternate as the rules say (the team without the hammer throws first);
an action out of turn is refused (HTTP 409). Each has its own 60-minute chess clock that runs only on its turn
(reviews included; clock out = loss) and reviews each of its throws.""",
            difficulty=f"""Set at run time: `DUEL_SEED` (the execution noise) and `FIRST_PLAYER` (A or B: throws the first stone of end
1, so the other player has the hammer in end 1). Official configurations: seeds {DUEL_SEEDS}, each with both values of
`FIRST_PLAYER`, so each pairing plays both orders.""",
            reference="`solution/` holds the scripted camera-only reference player (either seat); with both seats `oracle` the match is valid.",
            verification="""The `sim` service records the match and the verifier (`tests/grade.py`, no network) checks the
fresh-process replay; `success` = `valid_trial` = 1 iff the match is complete (played out, or decided by a clock or start
forfeit), deterministic, and free of metering or model-API failures. The winner is `A_won` / `B_won` (they sum to 1; there is no
draw: a tie after the last extra end goes to the player with more chess-clock time left, `clock_tiebreak`);
`reward.json` also reports `A_points` / `B_points`, `seed`, `first_player` (0 = A),
`official_config`, `clock_forfeit` and `start_forfeit`.""",
            details=f"""| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task curling-duel-program-standard --a opus\\|astra\\|oracle --b ... --seed N --first A\\|B` |
| Format | the single-player match rules: 4 ends x 5 stones per team, up to 3 extra ends while tied, then the player with more chess-clock time left wins; A yellow, B red; `FIRST_PLAYER` throws first in end 1 (the other has the hammer); after an end the scorer throws first, a blank end keeps the hammer; the n-th stone of each team in an end gets the same execution error |
| Rules | World Curling, The Rules of Curling and Rules of Competition, July 2025 (https://worldcurling.org/wp-content/uploads/2025/08/Rules-2025.pdf). Deviations: 4 ends of 5 stones per team (C5, R2(b): 8 or 10 ends of 8 stones); at most 3 extra ends, then the player with more chess-clock time left wins (R12(a): extra ends until a team scores); no sweeping (R8); the stone is released at the hack with the given speed, direction and spin (no delivery rules, R5); no no-tick rule (R7) |
| Time | one 60-minute chess clock per player, running only on its turn; review after each of its throws |
| Start | {START_S // 60} minutes to start after the first player, else forfeit |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Generator | `scripts/olympiad/generate.py` |""")),
}
