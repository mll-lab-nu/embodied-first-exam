"""Mini-golf putting: the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py).
A precision (turn-based) sport: protocol eai-standard-turn/1.0, a 60-minute chess clock per player, program play."""
from common import IMAGE, START_S
from golf_prompt import duel_prompt, single_prompt

PROTOCOL = "eai-standard-turn/1.0"
OFFICIAL_SEEDS = [20260928, 13, 14]   # the old tasks golf-putting-interactive (GOLF_SEED 20260928), -seed13, -seed14
SUCCESS_MAX_TOTAL = 9                 # single player: par, the old task's line
RULEBOOK = "WMF Rulebook 2.3, Worldwide international sport rules (World Minigolf Sport Federation), https://gov.minigolfsport.com/rules/2_3.pdf; secondary: R&A/USGA Rules of Golf 2023, https://www.randa.org/rog"
DEVIATIONS = ("greens enclosed by walls: no border line, no out of bounds (WMF 2.7, 8); a chess clock instead of the "
              "per-stroke time limit (WMF 11.3)")
DUEL_DEVIATIONS = DEVIATIONS + ("; the starter alternates from hole to hole instead of the honour (R&A 6.4b), and the "
                                "first play-off hole continues the alternation instead of a coin flip (WMF 9.3); the "
                                "play-off stops after 4 holes, then the chess clock decides (WMF 9.3 continues until "
                                "there is a difference)")

EXPERIMENT = dict(
    single=dict(task="golf-putting-program-standard", seeds={1: OFFICIAL_SEEDS}, slowdowns=None),
    duel=dict(task="golf-putting-duel-program-standard", seeds=OFFICIAL_SEEDS, slowdowns=None, first="FIRST_PLAYER"),
)

TASKS = {
    "golf-putting-program-standard": dict(
        source="golf/single", shared="shared/golf/sim", pins_to=["environment"], prompt=single_prompt,
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (mini-golf putting)",
            family="`golf_putting` / seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the privileged reference player's precomputed strokes for each official seed (5, 6 and 5 strokes), played through the service's HTTP calls",
            budget_s=7200, base_image=IMAGE,
            task=f"""A 4-hole mini-golf putting round (par {SUCCESS_MAX_TOTAL}) on sloped greens with walls and an obstacle block (a deterministic
rolling-ball and cup model; MuJoCo renders the scene). The agent sees the course only through cameras and plays each
stroke with an aim and a speed (seeded scatter). It may write a program that observes and putts on its own, fix it at
any time and reviews after every stroke. A 60-minute chess clock runs on the agent's turns (simulation excluded).
Success: the round in {SUCCESS_MAX_TOTAL} strokes or fewer. The prompt follows the turn-based program-play structure
(`scripts/olympiad/turn_prompt.py`) with golf's sections (`scripts/olympiad/golf/golf_prompt.py`).""",
            difficulty=f"""Set at run time: the seed (`RCB_SEED`: where the ball and the cup are, the tilts, bumps and ridges, and the
stroke scatter). Official seeds: {OFFICIAL_SEEDS} (the old `golf-putting-interactive[-seed13/14]`).""",
            reference="""`solution/solve.sh` runs the reference player (`solution/oracle_play.py`): the strokes the privileged reference
player computed offline for each official seed (true positions and physics; grid search over aim and speed, the most
robust holed cell), sent through the same HTTP calls a player program uses.""",
            verification=f"""The `sim` service records the round; a separate verifier (`tests/grade.py`, no network) checks the
fresh-process replay (`replay_check.json`: every recorded stroke reproduces the state and the score) and writes
`success` = 1 iff the round is valid, complete (no clock out) and takes at most {SUCCESS_MAX_TOTAL} strokes. `reward.json` also reports
`total`, `to_par`, per-hole scores, `seed`, `official_config`, `valid_trial`, `technical_failure` and the clock used.""",
            details=f"""| | |
|---|---|
| Rules | {RULEBOOK}; scoring as WMF 9.1 (6 strokes, then 7) |
| Deviations | {DEVIATIONS} |
| Parameters | `RCB_SEED` (default 20260928) |
| Run | `scripts/olympiad/run_single.sh --task golf-putting-program-standard --agent opus\\|astra\\|oracle\\|nop --level 1 --seed N` |
| Time | a 60-minute chess clock, running from `game start` on the agent's turns, reviews included, simulation excluded; clock out = loss (the unfinished holes score 7) |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Generator | `scripts/olympiad/generate.py` |""")),
    "golf-putting-duel-program-standard": dict(
        source="golf/duel", shared="shared/golf/sim", pins_to=["environment/seat"],
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes"),
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (mini-golf putting, two players)",
            family="`golf_putting_duel` / seed and first player chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the reference player on either seat; oracle against oracle plays valid matches with both first players",
            budget_s=7200, base_image=IMAGE,
            task="""Two agents play the same 4-hole mini-golf putting round, each with its own ball; the balls never meet: a player
plays a hole alone, from the start to the cup (a review after each stroke), then the other plays the same hole.
Whoever plays a hole second plays the next hole first (hole 1: the first player), so each leads two holes. The stroke
scatter is the same for both (seeded by seed, hole and stroke). An action out of turn is refused (HTTP 409); `game wait`
returns when it is the player's turn. Each player has a 60-minute chess clock (its turns only, reviews included; clock
out = loss). Fewest strokes wins; equal totals go to a sudden-death play-off (WMF 9.3: holes 1, 2, ... again, each
scored alone, at most 4), then the player with more chess-clock time left wins: there are no draws. A player sees only
its own ball and hears the opponent's results. Single and duel play by the same rules (holes, scoring, pick-up rule,
limits).""",
            difficulty=f"""Set at run time: the seed (`DUEL_SEED`; official {OFFICIAL_SEEDS}) and the first player (`FIRST_PLAYER`, A or B).
Play both orders for a fair comparison.""",
            reference="""`solution/` holds the reference player (precomputed strokes per official seed), usable on either seat. The two
seats' references differ slightly so that two references do not tie: seat B aims 0.2 degrees further counter-clockwise
than seat A (on the official seeds A takes 5 / 6 / 5 strokes, B 6 / 22 / 10).""",
            verification="""The `sim` service records the match and the verifier (`tests/grade.py`, no network) checks the fresh-process
replay of both rounds; `success` = 1 iff the match is valid and decided (played out, or won on the opponent's clock or
start); the winner is `A_won` / `B_won` (exactly one in a valid match). `reward.json` also reports both totals and
per-hole scores, the play-off holes (`tiebreaks`), whether the clock decided (`clock_decided`), `official_config`,
`technical_failure`, `clock_forfeit` and `start_forfeit`.""",
            details=f"""| | |
|---|---|
| Rules | {RULEBOOK}; scoring as WMF 9.1, order of play as WMF 11.2, lowest total wins (WMF 9.2), a tie goes to a sudden-death play-off (WMF 9.3), at most 4 holes, then more chess-clock time left wins |
| Deviations | {DUEL_DEVIATIONS} |
| Parameters | `DUEL_SEED` (default 20260928), `FIRST_PLAYER` (A or B) |
| Run | `scripts/olympiad/run_duel.sh --task golf-putting-duel-program-standard --a opus\\|astra\\|oracle --b ... [--seed N] [--first A\\|B]` |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / clock | 30 minutes to start after the first player; one 60-minute chess clock per player |
| Generator | `scripts/olympiad/generate.py` |""")),
}
