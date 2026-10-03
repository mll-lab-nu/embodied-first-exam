# baseball-duel-wallclock-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-realtime/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `swing-rig` |
| Family / instance | `baseball_duel` |
| Oracle | `full` — solution/: one scripted camera-only player (pitcher and batter) on both seats plays valid games (checked at x10 and x20, both first batters) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents play baseball against each other, pitcher against batter, in a shared world running in real time
slowed by a factor S. The plate appearances alternate between the seats: in each, one seat bats with the swing rig of
the single-player task and the other pitches, choosing every pitch's type, speed and target at the plate (within the
stated limits, with a seeded execution scatter). Each seat bats 5 plate appearances; the score is the bases each
collects as the batter (walk or single 1, double 2, home run 4; the single-player game's fielders). More bases wins;
level after 5 each: one more plate appearance each until decided, at most 5 times; then the winner of the last pitch wins (no draws). Each player may write a program that
observes and acts on its own, fix it at any time and review after every pitch (300 s, else forfeit).

## Difficulty
Set at run time: slowdown S (`RCB_SLOWDOWN`; official [10, 20]), seed (`DUEL_SEED`: the windups and
the pitch and swing scatter, the same sequence for both batters) and the seat that bats first (`FIRST_RECEIVER`, A or
B: the first to receive pitches; `match.first_player` in the spec). The format is symmetric (each seat bats and pitches equally often, with the same
random sequences); play both seat orders for a fair comparison.

## Reference solution
`solution/` holds the scripted reference player for either seat: as the pitcher a fixed pitch mix (two thirds
in the zone), as the batter the camera-only batter of the single-player task (`solution/bat_player.py`); with both
seats `oracle` the game is valid.

## Verification
The `sim` service records every command with the pitch and step at which it took effect; the verifier
(`tests/grade.py`, no network) checks the fresh-process replay (state hash, score, commands, steps); `success` = 1 iff
the game is valid (played out, or won by a review forfeit); the winner is `A_won` / `B_won` (exactly one; no draws;
`decided_by_last_pitch` = 1 if the last-resort rule decided). `reward.json` also reports `A_bases` / `B_bases` (= `A_points` / `B_points`), `official_config`,
`technical_failure` and `ready_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Parameters | `RCB_SLOWDOWN` (default 20), `DUEL_SEED` (default 1), `FIRST_RECEIVER` (A or B: the seat that bats first) |
| Run | `scripts/olympiad/run_duel.sh --task baseball-duel-wallclock-program-standard --a opus\|astra\|oracle --b ... --slowdown S [--seed N] [--first A\|B]` |
| Format | plate appearances alternate (A, B, A, ... or B, A, ...); 5 each; if level, extra pairs until decided, at most 5, then the winner of the last pitch wins (no draws); a plate appearance reaching 15 pitches is an out (no stalling with two-strike fouls) |
| Pitching | type (fastball, slider, changeup, curveball; fixed spins), speed within the type's band, target -0.6 <= x <= 0.6, 0.2 <= z <= 1.6 m; scatter 3 cm, 0.3 m/s; no pitch by the release = an automatic ball |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / review | 30 minutes to start after the first player; 300 s per review, else forfeit |
| Generator | `scripts/olympiad/generate.py` |
| Rulebook | MLB *Official Baseball Rules*, 2026 edition: https://mktg.mlbstatic.com/mlb/official-information/2026-official-baseball-rules.pdf |
| Field | as in 2.01: bases 90 ft (27.43 m) apart, the pitch released about 1.4 m in front of the rubber (18.44 m) |
| Count and zone | strike, ball, foul, strikeout, walk as in the Definitions of Terms, 5.05(b), 5.09(a) |
| Deviations | no base runners, runs or innings: each plate appearance scores the bases the batter reaches, no triples (5.05, 5.06); no batter's body, so no hit by pitch (5.05(b)(2)); fouls are never caught and there are no foul tips (5.09(a)(1), "Foul Tip"); fair/foul at the first landing point also for short balls ("Fair Ball"); the strike zone judged in one plane at fixed heights ("Strike Zone"); a uniform 100 m, 3 m high fence (2.01 Note: 325 ft at the lines, 400 ft to centre); fixed fielders without errors; a plate appearance reaching 15 pitches is an out (no limit in MLB) |
| Duel deviations | the pitcher only chooses the pitch (fixed windup and release point); no pitch by the release is an automatic ball, like a pitch-clock violation (5.07(c)); level bases after 5 extra pairs: the winner of the last pitch wins (MLB plays extra innings until decided, 7.01(b)) |
