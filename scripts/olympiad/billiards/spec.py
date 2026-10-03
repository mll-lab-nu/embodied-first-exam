"""Billiards (one rack of American 8-ball): the Embodied Agent Olympiad tasks of this sport (rendered by scripts/olympiad/generate.py).

A turn-based (precision) sport: protocol eai-standard-turn/1.0, a 60-minute chess clock per player
(docs/benchmarks/olympiad-adding-a-precision-sport.md). Its simulator image is eai-olympiad-billiards (pooltool), set in
the tasks' docker-compose.yaml sources; images/olympiad-billiards/."""
from pathlib import Path

from billiards_prompt import duel_prompt, single_prompt
from common import START_S

PROTOCOL = "eai-standard-turn/1.0"
ROOT = Path(__file__).resolve().parents[3]
IMAGE = ("ghcr.io/mll-lab-nu/eai-olympiad-billiards:"
         + (ROOT / "images/olympiad-billiards/VERSION").read_text().strip())
OFFICIAL_SEEDS = {1: [1, 3, 6], 2: [2, 4, 8]}     # rack seeds where both players get several turns (checked offline)
DUEL_SEEDS = [1, 3, 4]                                        # each with FIRST_PLAYER A and B; contested games for the reference player (checked offline)

EXPERIMENT = dict(
    single=dict(task="billiards-eightball-program-standard", seeds=OFFICIAL_SEEDS, slowdowns=None),
    duel=dict(task="billiards-duel-program-standard", seeds=DUEL_SEEDS, slowdowns=None, first="FIRST_PLAYER"),
)

TASKS = {
    "billiards-eightball-program-standard": dict(
        source="billiards/eightball", shared="shared/billiards/sim", pins_to=["environment"], prompt=single_prompt,
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (billiards: 8-ball)",
            family="`billiards_eightball` / level and seed chosen at run time",
            oracle="full",
            oracle_evidence="solution/: a scripted camera-only 8-ball player; wins the default L1 configuration (seed 1), checked valid at L1 and L2 (it can lose)",
            budget_s=7200, base_image=IMAGE,
            task="""One rack of 8-ball against a scripted computer opponent on a simulated 7-ft table (pooltool's event-based physics
with spin, cushions and pockets). The agent sees the table only through an overhead camera and a sighting camera (no
ball coordinates) and shoots by cue direction, cue speed and tip offset; with ball in hand it also places the cue ball,
and every shot after the break is called (ball and pocket, or safety). The rules (`environment/sim/eightball.py`) are
the WPA Rules of Play (effective 2025-09-15) for 8-Ball with the deviations in the Rules row below. A 60-shot limit per
player ends every game (then fewer balls left wins; if level, more chess-clock time left; the scripted opponent's clock
never runs). Turn-based: a
60-minute chess clock runs only on the agent's turn (reviews included; clock out = loss), and the agent reviews each of
its shots. It may write a program that measures the images and sends its shots. The prompt follows the general
turn-based program-play structure (`scripts/olympiad/turn_prompt.py`) with 8-ball's sections
(`scripts/olympiad/billiards/billiards_prompt.py`).""",
            difficulty=f"""Set at run time: opponent level 1-2 (`RCB_LEVEL`; level 1: aim error 0.5 deg, the agent breaks; level 2: aim
error 0.25 deg, safer shot selection, the opponent breaks) and the rack seed (`RCB_SEED`: the order of the balls in the
rack, a small rack jitter, the execution scatter). Official configurations: levels with seeds {OFFICIAL_SEEDS},
chosen so that both players get several turns.""",
            reference="""`solution/solve.sh` runs a scripted player that uses only the top camera image, the documented geometry and the
rules (`solution/eight_player.py`: ball centres from a distance transform of the image, solids / stripes / 8 / cue ball
from their colours; the break from the head spot; ball in hand placed for a straight pot; the easiest direct pot of its
group by ghost-ball geometry, called as ball and pocket (numbers read from the ball colours); a firm hit called
safety when it has no pot).""",
            verification="""The `sim` service records the game; a separate verifier (`tests/grade.py`, no network) checks the
fresh-process replay and writes `success` = 1 iff the agent wins a valid game (deterministic replay; no simulator,
model-API or metering failure; the clock did not run out). `reward.json` also reports `level`, `seed`,
`official_config`, `valid_trial`, `technical_failure`, `your_balls_left` / `opponent_balls_left`, `lost`, `clock_tiebreak` and
`clock_forfeit`.""",
            details="""| | |
|---|---|
| Parameters | `RCB_LEVEL` (default 1), `RCB_SEED` (default: the level's first official seed, 1 or 2) |
| Run | `scripts/olympiad/run_single.sh --task billiards-eightball-program-standard --agent opus\\|astra\\|oracle\\|nop --level L --seed N` |
| Action | `shoot AIM_DEG SPEED [SPIN_X SPIN_Y] [cue=X,Y] [call=BALL:POCKET\\|safety]` (cue placement only with ball in hand; a call on every shot but the break) |
| Rules | WPA Rules of Play, effective 2025-09-15 (https://wpapool.com/wp-content/uploads/2025/09/2025.09.15-WPA-Rules.pdf), section 4 8-Ball, with the fouls of section 3. Deviations: the 8 pocketed on the break is always spotted (4.3(e)/(f): no re-break option); after an illegal break the other player always re-racks the same rack and breaks (4.3(d)(2) chosen, no other option); a foul on the break gives ball in hand above the head string (4.3(g)/(h)(2) chosen); no spot request with ball in hand above the head string (1.6); every call is explicit, no \"obvious\" shots (1.7, 4.6); no cue elevation, so no jump or massé shots (2.9); the cue ball cannot be placed touching a ball or in a pocket opening (1.6); a 60-shot limit per player (then fewer balls left, then more chess-clock time left) replaces the stalemate rule (4.11); push out is a 9-Ball rule and does not apply. pooltool's own `ruleset.eight_ball` is not used (it is tied to pooltool's game loop); its event helpers are |
| Time | chess clock: 60 minutes (`clock.total_s` in `/spec`), only on the agent's turn; review after each of its shots |
| Isolation | The agent runs in `player` (one Harbor seat): internet only while the agent is installed, then only `sim`; `main` mounts its `/app/output` |
| Container | Python 3.12 (standard client image and pins) with OpenCV (headless); 4 CPUs, 8 GB |
| Simulator image | `images/olympiad-billiards/` (pooltool 0.6.0, numba; built locally) |
| Generator | `scripts/olympiad/generate.py` |""")),
    "billiards-duel-program-standard": dict(
        source="billiards/duel", shared="shared/billiards/sim", pins_to=["environment/seat"],
        prompt=lambda: duel_prompt(start=f"{START_S // 60} minutes"),
        readme=dict(
            protocol=PROTOCOL,
            benchmark="Embodied Agent Olympiad (billiards: 8-ball, two players)",
            family="`billiards_duel` / seed and breaker chosen at run time",
            oracle="full",
            oracle_evidence="solution/: the scripted camera-only 8-ball player on either seat; oracle against oracle plays valid games (FIRST_PLAYER A and B)",
            budget_s=10800, base_image=IMAGE,
            task="""Two agents play one rack of American 8-ball against each other at one table (the single-player game's rules,
`environment/sim/eightball.py`), each from its own container through the same cameras and shot interface (cue
direction, speed, tip offset; cue placement with ball in hand; the call of every shot after the break). They take
turns as the rules say (a legal shot that pockets the called ball in the called pocket keeps the turn); an action out of
turn is refused (HTTP 409). Each
has its own 60-minute chess clock that runs only on its turn (reviews included; clock out = loss) and reviews each of
its shots.""",
            difficulty=f"""Set at run time: `DUEL_SEED` (the rack order and jitter, the execution scatter) and `FIRST_PLAYER` (A or B: who
breaks). Official configurations: seeds {DUEL_SEEDS}, each with both values of `FIRST_PLAYER`, so each pairing plays
both orders.""",
            reference="`solution/` holds the scripted camera-only reference player (either seat); with both seats `oracle` the game is valid.",
            verification="""The `sim` service records the game and the verifier (`tests/grade.py`, no network) checks the fresh-process
replay; `success` = `valid_trial` = 1 iff the game is complete (played out, or decided by a clock or start forfeit),
deterministic, and free of metering or model-API failures. The winner is `A_won` / `B_won` (they sum to 1: a tie at the shot limit goes to the player
with more chess-clock time left, `clock_tiebreak`); `reward.json` also reports `A_balls_left` / `B_balls_left` (balls left in the player's group, 7 while
open), `seed`, `first_player` (0 = A), `official_config`, `clock_forfeit` and `start_forfeit`.""",
            details=f"""| | |
|---|---|
| Parameters | `DUEL_SEED` (default 1), `FIRST_PLAYER` (A or B, default A: the breaker) |
| Run | `scripts/olympiad/run_duel.sh --task billiards-duel-program-standard --a opus\\|astra\\|oracle --b ... --seed N --first A\\|B` |
| Format | one rack of 8-ball, the single-player rules; `FIRST_PLAYER` breaks (after an illegal break the other player re-racks and breaks); 60 shots each at most (then fewer balls left in the group wins, an open table counting as 7; if level, more chess-clock time left wins) |
| Rules | WPA Rules of Play, effective 2025-09-15 (https://wpapool.com/wp-content/uploads/2025/09/2025.09.15-WPA-Rules.pdf), section 4 8-Ball, with the fouls of section 3. Deviations: the 8 pocketed on the break is always spotted (4.3(e)/(f): no re-break option); after an illegal break the other player always re-racks the same rack and breaks (4.3(d)(2) chosen, no other option); a foul on the break gives ball in hand above the head string (4.3(g)/(h)(2) chosen); no spot request with ball in hand above the head string (1.6); every call is explicit, no \"obvious\" shots (1.7, 4.6); no cue elevation, so no jump or massé shots (2.9); the cue ball cannot be placed touching a ball or in a pocket opening (1.6); a 60-shot limit per player (then fewer balls left, then more chess-clock time left) replaces the stalemate rule (4.11); push out is a 9-Ball rule and does not apply |
| Time | one 60-minute chess clock per player, running only on its turn; review after each of its shots |
| Start | {START_S // 60} minutes to start after the first player, else forfeit |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Simulator image | `images/olympiad-billiards/` (pooltool 0.6.0, numba; built locally) |
| Generator | `scripts/olympiad/generate.py` |""")),
}
