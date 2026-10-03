# badminton-duel-wallclock-program-standard

| | |
|---|---|
| Benchmark | Embodied Agent Olympiad |
| Mode | standard (`eai-standard-realtime/1.0`) |
| Twin | — (standard only: Olympiad sports have no privileged twin) |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `badminton_duel` |
| Oracle | `full` — solution/: a camera-only reference player for either seat (images, replies and documented physics only); two of them play valid matches with real rallies (checked at x10 and x20, both first receivers) |
| Agent time budget | 7200 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` |

## Task
Two agents each control an identical simulated Franka Panda arm on a sliding base, holding a badminton racket, on
the two halves of one court, and play a singles match (first to 5 points, two-point lead from 4-4, at most 7, rally scoring) in a shared world running in
real time, slowed by a factor S. Each may write a player program that observes and acts on its own, fix it at any time
and review after every point (300 s, else forfeit).

## Difficulty
Set at run time: slowdown S (`RCB_SLOWDOWN`; official [10, 20]), seed (`DUEL_SEED`: the serves and the
execution scatter) and first receiver (`FIRST_RECEIVER`, A or B). Play both seat orders for a fair comparison.

## Reference solution
`solution/` holds a camera-only reference player for either seat (`oracle_play.py`, `cam_player.py`):
it detects the orange cork in both cameras, triangulates it, fits the documented drag model, picks a contact the base
can reach and a target (deep corners or short), and turns the launch velocity into the racket state with the contact
law; it corrects the command while the shuttle flies and uses the act reply to switch to another stroke when the arm
cannot deliver one. It uses only the seat's ordinary endpoints. With both seats `oracle` the match is valid.

## Verification
The `sim` service records the match and replays it in a fresh process from the logged acts; the verifier
(`tests/grade.py`, no network) checks the replay against the live state, joint targets and score. `success` = 1 iff the
match is valid (played out, or won by a review forfeit); the winner is `A_won` / `B_won`. `reward.json` also reports
`A_points` / `B_points`, `seed`, `slowdown`, `official_config`, `technical_failure` and `ready_forfeit`.
Model-API errors (`environment/sim/api_errors.py`): an error the agent's harness recovered from (a later model call of the same seat completed successfully) is only counted and reported (`transient_api_errors`; `A_`/`B_` per seat in a duel). The model API fails the trial (`proxy_error`, a technical failure) only if a seat had an unrecovered error (no successful model call after it) or more than 5 transient errors in the match.

## Details
| | |
|---|---|
| Rules | [BWF Laws of Badminton (BWF Statutes, Section 4.1, in force 26 April 2025, version 5.0)](https://extranet.bwf.sport/docs/document-system/81/1466/1470/Section%204.1%20-%20Laws%20of%20Badminton%20-%2026%20April%202025%20V5.0%20(2)%20.pdf). Deviations: a neutral machine on the server side's half serves every point and the receiver changes every point (Law 10.3); one game to 5 points, a two-point lead from 4-4, at most 7 (Law 7: best of three to 21, cap 30); serves from the server's right or left service court by the server's score (10.1.1) into the diagonal court (9.1; outside it: a fault, the receiver's point, 13.1); net top 1.524 m (1.10); base 6 m/s, 20 m/s^2; point-mass shuttle: a crossing of the net plane below the top is a fault, net touch / reaching over the net (13.4) not judged; robots back home before every serve; 300 hits in the match end it after that point (the leader wins, if level the winner of the last point: no draws). The single-player task and the duel play by the same rules; only who serves differs |
| Parameters | `RCB_SLOWDOWN` (default 20), `DUEL_SEED` (default 1), `FIRST_RECEIVER` (A or B, default A) |
| Run | `scripts/olympiad/run_duel.sh --task badminton-duel-wallclock-program-standard --a opus\|astra\|oracle --b ... --slowdown S [--seed N] [--first A\|B]` |
| Court | Both robots are the match task's robot; B's frame is the world turned 180 degrees about z, so each seat plays in the single-player frame (home (0, -4.0), its half y < 0) with the same cameras, prompt and act |
| Serve format | A neutral serving machine on the server side's half serves every point, 1 s after play resumes: from that side's right service court when that side's score is even, else from its left one (at (-+0.45, 2.3, 1.05) in the receiver's frame), a high deep or a short serve into the receiver's diagonal service court, seeded by `DUEL_SEED` and the point number (the match task's opponent serves). The receiver changes every point: `FIRST_RECEIVER` receives points 1, 3, 5, ... (a replayed point keeps its receiver). An unreturned serve in the service court is the server side's point; outside it, the receiver's (never seen); a serve into the net is replayed |
| Scoring | First to 5 points; from 4-4 a two-point lead is needed; the first to 7 wins (6-6: the next point wins) |
| Rally | The players hit in turn; a racket meets the shuttle only on its own half when it is that player's turn (no double hits). The shuttle landing in the court of the player to hit loses that player the point; out, into the net or on the hitter's own half loses the hitter the point. Both robots go back home in the ready pose before every serve |
| Base | The base moves up to 6 m/s and 20 m/s^2 (both tasks; the wall-clock engine had 3 m/s, 6 m/s^2). With the old base no drop with a flight under 1.1 s can be returned from anywhere on the half, so the receiver's corner drop off a high serve won every point (every oracle duel ended 5-4 to the first receiver); with the faster base a well-placed fast drop can still win, a slower one can be returned |
| Physics | Contacts are off in the badminton scene, so each robot runs in its own copy of the single-player model; the shuttle (point mass, quadratic drag) and the referee run once in the world frame; `scene/bm_duel.xml` (from `scripts/olympiad/badminton/mk_duel_scene.py`) only draws the game |
| Act lead | an act takes effect `timing.act_lead_steps` = ceil(0.4 s / (0.01 S)) control steps after it arrives; the seat's planner process plans it on an exact copy of the seat's robot |
| Isolation | Each seat shares only an internal network with `sim`; internet only while its agent is installed |
| Start / review | 30 minutes to start after the first player; 300 s per review, else forfeit |
| Generator | `scripts/olympiad/generate.py` |
