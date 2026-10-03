# Embodied Agent Olympiad: adding a precision (turn-based) sport

Darts, archery, bowling, golf putting, basketball shooting, billiards and curling. These sports wait for the player, so
they need no real-time clock. They use the same program-play standard and generator as the real-time sports.

Read `docs/benchmarks/olympiad-adding-a-sport.md` first and follow it, with the differences below. The protocol is
`eai-standard-turn/1.0`; see the last section of `docs/EAI_STANDARD_REALTIME_1_0.md`.

## Differences from the real-time guide

| | real-time sports | precision sports |
|---|---|---|
| protocol (`task.toml`, `/spec`) | `eai-standard-realtime/1.0` | `eai-standard-turn/1.0` (pass `protocol=` to `realtime_standard.readme`) |
| task names | `<sport>-<family>-wallclock-program-standard` | `<sport>-<family>-program-standard`, e.g. `darts-501-program-standard`, `billiards-match-program-standard` |
| duel | `<sport>-duel-wallclock-program-standard` | `<sport>-duel-program-standard` |
| time | world slowed by S; `RCB_SLOWDOWN` | chess clock per player, **60 minutes for every sport** (`turn_prompt.CLOCK`; `clock.total_s` = 3600 in `/spec`), running only on the player's own turn, reviews included; clock out = loss. No slowdown parameter |
| review | after each point | after each of the player's shots (as in the old tasks) |
| prompt | `program_prompt.py` | `turn_prompt.py` (`single(..., opponent=False)` for sports played alone); do not edit it |
| act rule | `RCB_ACT_RULE=program` | the same. The old tasks require a new model call per shot ("Do not write a program that plays for you"); program play replaces that: a live metered model session is enough, and the agent may write a program that computes and sends its shots. Remove every sentence forbidding programs. |
| parameters (single) | `RCB_LEVEL`, `RCB_SLOWDOWN`, `RCB_SEED` | `RCB_LEVEL` (only sports with opponent levels: darts L1–L4, billiards L1–L2, curling L1–L2), `RCB_SEED` |
| parameters (duel) | `RCB_SLOWDOWN`, `DUEL_SEED`, `FIRST_RECEIVER` | `DUEL_SEED`, `FIRST_PLAYER` (A or B) |
| official configurations | 3 seeds per level × slowdowns | 3 seeds per level, taken from the old tasks (`*-seed2`, `*-seed3` directories and the seed variables in their compose files) |
| success (single) | win the match | against an opponent: win the match. Alone (archery, bowling, golf putting, basketball): reach the old task's success line (state it in the Task section); the prompt also says a higher score is better (`turn_prompt` does this for `opponent=False`), and the grader always reports the score |
| grader fields | ... `slowdown` ... | `level` (when there are levels), `seed`, `official_config`, `success`, `valid_trial`, `technical_failure`, the sport's score; duel: both seats' scores, `A_won`/`B_won`, `clock_forfeit` |
| `test_program_play.py` | must print `ALL OK` | the same (it tests `think_clock.py`/`think_proxy.py`, copied byte for byte from table tennis) |

## Duels

Two agents in one world, one Harbor seat each (`seat_a`, `seat_b`). The setup follows the table tennis duel:
- seat containers and networks;
- per-seat metering (`think_calls_A/B`) and per-seat routes (`THINK_OPENAI_ROUTE_A/B`, `launch.py`);
- the start window `START_S` from `common.py`;
- a scripted reference player usable on either seat;
- a replay-based grader.

Unlike table tennis, the players take turns. The service refuses an action out of turn with HTTP 409, and each player
has its own chess clock. Fairness first: both players get the same conditions, and `FIRST_PLAYER` lets the runner play
both orders. Proposed formats (choose the details, keep them simple, and document them in the README and the prompt):

| sport | duel format |
|---|---|
| darts | 501 double-out, alternate visits of 3 darts, best of 3 legs; the first leg goes to `FIRST_PLAYER`, then legs alternate |
| archery | the same target and wind for both players; alternate ends of 3 arrows; highest total after N ends wins, with a shoot-off on a tie |
| basketball shooting | the same racks for both players; alternate rounds; most points wins, with extra shots on a tie |
| bowling | each player has their own identical lane; alternate frames; 10 frames, highest score wins |
| golf putting | the same holes; alternate holes or strokes; fewest strokes over the round wins (match play optional) |
| billiards | the existing match rules, with two agents instead of agent against computer |
| curling | the existing match rules (ends, alternating stones, hammer), with two agents instead of agent against computer |

## Simulator image

Every sport except billiards has the same simulator dependencies as `eai-olympiad` (MuJoCo 3.3.7 etc.), so it uses
`eai-olympiad` unchanged. Billiards needs panda3d / pooltool. Add an image `images/olympiad-billiards/`
(Dockerfile, requirements.txt with pinned versions, VERSION 0.1.0) named
`ghcr.io/mll-lab-nu/eai-olympiad-billiards:<VERSION>`, and build it locally. Do not push it.

## Starting points (the earlier per-response sports pilot, outside this repository)

| sport | old tasks |
|---|---|
| darts | `tasks/darts-501-l{1..4}-interactive[-seed2/3]` |
| archery | `tasks/archery-interactive[-seed2/3]` |
| bowling | `tasks/bowling-interactive[-seed2/3]` |
| golf putting | `tasks/golf-putting-interactive[-seed2/3]` |
| basketball shooting | `tasks/basketball-shootout-interactive[-seed2/3]` |
| billiards | `tasks/billiards-match[-l2]-interactive[-seed*]` |
| curling | `tasks/curling-match[-l2]-interactive[-seed*]` |
