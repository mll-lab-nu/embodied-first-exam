"""Ten-pin bowling: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py).
A precision (turn-based) sport: protocol eai-standard-turn/1.0, a 60-minute chess clock per player, program play."""
from common import IMAGE, START_S
from bowling_prompt import duel_prompt, single_prompt

PROTOCOL = "eai-standard-turn/1.0"
OFFICIAL_SEEDS = [20260930, 2, 3]     # the old tasks bowling-interactive (BOWL_SEED 20260930), -seed2, -seed3
SUCCESS_MIN_TOTAL = 200               # single player: the old task's line
RULEBOOK = "USBC Playing Rules 2025-2026 (Chapter 2, General Playing Rules; rev. 07/25), https://bowl.com/getmedia/cabf49db-8cc5-4ce4-abc0-dfca1a1d7706/071724_USBC-Playing-Rules.pdf"
DEVIATIONS = ("pin down = tilted more than 20 degrees or off the lane surface (approximates USBC 6a); no fouls (the release "
              "starts past the foul line, USBC 5a); no rear cushion (open pit, USBC 6b.2)")

EXPERIMENT = dict(
    single=dict(task="bowling-program-standard", seeds={1: OFFICIAL_SEEDS}, slowdowns=None),
    duel=dict(task="bowling-duel-program-standard", seeds=OFFICIAL_SEEDS, slowdowns=None, first="FIRST_PLAYER"),
)

TASKS = {
    "bowling-program-standard": dict(
        source="bowling/single", shared="shared/bowling/sim", pins_to=["environment"], prompt=single_prompt,
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (bowling)",
            family="`bowling` / seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the privileged reference player's precomputed releases for each official seed (300 on each), played through the service's HTTP calls",
            budget_s=7200, base_image=IMAGE,
            task=f"""A 10-frame game of ten-pin bowling on a regulation MuJoCo lane (oiled front end, dry back end; 10 rigid pins,
a 7 kg ball). The agent sees the lane only through cameras and rolls each ball with a release (board, launch angle,
speed, rev rate, axis rotation; seeded scatter). It may write a program that observes and bowls on its own, fix it at
any time and reviews after every ball. A 60-minute chess clock runs on the agent's turns (simulation excluded). Success:
a total of {SUCCESS_MIN_TOTAL} or more. The prompt follows the turn-based program-play structure
(`scripts/olympiad/turn_prompt.py`) with bowling's sections (`scripts/olympiad/bowling/bowling_prompt.py`).""",
            difficulty=f"""Set at run time: the seed (`RCB_SEED`: the lane's oil pattern and friction, and the release scatter). Official
seeds: {OFFICIAL_SEEDS} (the old `bowling-interactive[-seed2/3]`). One game varies a lot (the same bowler's games spread
by about 25-30 pins); the score is always reported.""",
            reference="""`solution/solve.sh` runs the reference player (`solution/oracle_play.py`): the releases the privileged reference
player computed offline for each official seed (true pin poses and the real lane; grid search and Monte Carlo over
the scatter), sent through the same HTTP calls a player program uses.""",
            verification=f"""The `sim` service records the game; a separate verifier (`tests/grade.py`, no network) checks the fresh-process
replay (`replay_check.json`: every recorded release reproduces the state and the score) and writes `success` = 1 iff
the game is valid, played out (no clock out) and scores at least {SUCCESS_MIN_TOTAL}. `reward.json` also reports `total`, `seed`,
`official_config`, `valid_trial`, `technical_failure`, the clock used and the per-frame pins. A gutter ball scores no
pins (USBC 6b.1) and a pin standing anywhere on the lane counts as standing (USBC 7b).""",
            details=f"""| | |
|---|---|
| Rules | {RULEBOOK} |
| Deviations | {DEVIATIONS} |
| Parameters | `RCB_SEED` (default 20260930) |
| Run | `scripts/olympiad/run_single.sh --task bowling-program-standard --agent opus\\|astra\\|oracle\\|nop --level 1 --seed N` |
| Time | a 60-minute chess clock, running from `game start` on the agent's turns, reviews included, simulation excluded; clock out = loss |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |""")),
    "bowling-duel-program-standard": dict(
        source="bowling/duel", shared="shared/bowling/sim", pins_to=["environment/seat"],
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes"),
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (bowling, two players)",
            family="`bowling_duel` / seed and first player chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the reference player on either seat; oracle against oracle plays valid matches with both first players",
            budget_s=7200, base_image=IMAGE,
            task="""Two agents each bowl a 10-frame game of ten-pin bowling on their own MuJoCo lane. The lanes are identical and so
is the release scatter (seeded by seed, frame and ball), so the same release gives the same result on both lanes.
Frames alternate: a player bowls a whole frame (a review after each ball), then the other; the first player leads
every frame. An action out of turn is refused (HTTP 409); `game wait` returns when it is the player's turn. Each
player has a 60-minute chess clock (its turns only, reviews included; clock out = loss). The higher total wins; equal
totals go to a roll-off (USBC 118b: one frame scored like a 10th, repeated while level, at most 3), then the player
with more chess-clock time left wins: there are no draws. A player sees only its own lane and hears the opponent's pin
counts. Single and duel play by the same rules (frames, scoring, gutter and pin rules, limits).""",
            difficulty=f"""Set at run time: the seed (`DUEL_SEED`; official {OFFICIAL_SEEDS}) and the first player (`FIRST_PLAYER`, A or B).
Play both orders for a fair comparison.""",
            reference="""`solution/` holds the reference player (precomputed releases per official seed), usable on either seat. The two
seats' references differ slightly so that two references do not tie: seat B lays every ball down half a board further
left than seat A (on the official seeds A bowls 300, B 244 / 247 / 160).""",
            verification="""The `sim` service records the match and the verifier (`tests/grade.py`, no network) checks the fresh-process
replay of both games; `success` = 1 iff the match is valid and decided (played out, or won on the opponent's clock or
start); the winner is `A_won` / `B_won` (exactly one in a valid match). `reward.json` also reports both totals, the
roll-off frames (`tiebreaks`), whether the clock decided (`clock_decided`), `official_config`, `technical_failure`,
`clock_forfeit` and `start_forfeit`.""",
            details=f"""| | |
|---|---|
| Rules | {RULEBOOK}; a tie goes to a roll-off (USBC 118b), at most 3 frames, then more chess-clock time left wins |
| Deviations | {DEVIATIONS}; the roll-off stops after 3 frames (USBC 118b continues until the tie is broken) |
| Parameters | `DUEL_SEED` (default 20260930), `FIRST_PLAYER` (A or B) |
| Run | `scripts/olympiad/run_duel.sh --task bowling-duel-program-standard --a opus\\|astra\\|oracle --b ... [--seed N] [--first A\\|B]` |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / clock | 30 minutes to start after the first player; one 60-minute chess clock per player |
| Generator | `scripts/olympiad/generate.py` |""")),
}
