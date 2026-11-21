# Robot epee fencing: program play (bout) — MCP tools only

You play robot epee fencing against a scripted opponent (you are seat `A`). Two Unitree G1 humanoids (the robot library's, NVIDIA's SONIC whole-body policy on the legs, waist and free arm, the point skill on the sword arm) holding real epees fence one FIE direct-elimination bout (15 touches or 9 minutes of fencing time, no draws; unwillingness to fight, FIE t.124) phrase by phrase: every phrase starts on guard 1.95 m apart, both fencers choose one of nine tactical intentions (lunge, low lunge, point in line, reactive line, stop-hit, counter-attack, delayed lunge, retreat, draw), each starts after a random 0-50 ms, and the phrase is played out as it was measured in MuJoCo (2916 phrases: every pair of intentions and delays); format bout: you against a scripted fencer that reads your choices (levels 1-2, `spec` opponent), format duel: two players choosing at the same time.
This is Embodied Olympics task `fencing-bout-wallclock-program-standard` (revision `fencing-7+core-0.2`), one frozen instance: the scripted opponent at level 2; the seed is fixed and never shown. The simulator service is at `http://localhost:8000`.

## Time
Nothing moves while you think: the world waits for the player whose turn it is. Each player has a chess clock of 60 minutes of real time, running only on its own turn (thinking, tool calls and your reviews all count). **If your clock runs out, you lose.**

After each of your actions (except one that ends the match), send `ready(why, plan)` (a short review) before the game goes on.
The match is graded when your session ends: stay until it is over. **If your session ends before the match is over, you lose the match** (a valid result, success 0), also if you never sent `start`.

## How you play
You play by calling the `efe-robot` tools yourself, one call at a time (`## Robot tools` below). Only you send `start` and `ready`.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).

## Robot tools (MCP server `efe-robot`)
You play only through the tools of the MCP server `efe-robot` (in your tool list as `efe-robot` tools, for example
`mcp__efe-robot__act`). You may write and run code to compute; every robot command and observation must go through the
efe-robot MCP tools; code must not contact the simulator. Each command or observation is a tool call you make yourself:
no script starts or calls the `efe-robot` server, and the service's record of its requests is checked against the
server's. Where this text names a `game` command or its HTTP call (the `game` command is not installed here), use the
tool of the same name:

| `game` command | Tool |
|---|---|
| `game spec` | `spec()`: the whole spec is also saved as a JSON file (`spec_file`) |
| `game status` | `status()` |
| `game start` | `start()` |
| `game wait` | `wait()`: blocks until it is your turn (or a review is due, or the match is over) |
| `game observe` | `observe(query?, inline_tiles?)`: images as PNG files (the view and one file per tile, native size) |
| `game act JSON` and the sport's shortcuts | `act(action)`, e.g. `act({"type": ..., ...})` |
| `game ready "WHY" "PLAN"` | `ready(why, plan)` |

- Images are files: `observe` (and an action whose reply shows its result) writes them under `/app/obs/`; open a tile
  file with your file-reading tool (pixel coordinates in it are the camera's own), or ask for tiles in the result with
  `inline_tiles`.
- Every result is the service's reply (the state is under `now` or `state`), plus `review_due` (a review is due from you
  now: send `ready`) and `match_over`. A refused call returns the service's error (400: an invalid action, nothing
  happens; 409: not now). The tools keep under the service's request rate themselves.
- One tool call runs at a time. A call still executing after 45 s returns `{"pending": true, "operation": id}`: call
  `wait(operation=id)` for its result.
- Nothing needs to be saved: the server records every tool call, and the service records the match.

**Notes.** Turn-based: nothing moves while you think; your chess clock runs on your turn. `spec` (its file) has the
phrase table; `status` / `observe` have every phrase so far.

## Rules
- two Unitree G1 humanoids (the robot library's, NVIDIA's SONIC whole-body policy on the legs, waist and free arm, the point skill on the sword arm) holding real epees fence one FIE direct-elimination bout (15 touches or 9 minutes of fencing time, no draws; unwillingness to fight, FIE t.124) phrase by phrase: every phrase starts on guard 1.95 m apart, both fencers choose one of nine tactical intentions (lunge, low lunge, point in line, reactive line, stop-hit, counter-attack, delayed lunge, retreat, draw), each starts after a random 0-50 ms, and the phrase is played out as it was measured in MuJoCo (2916 phrases: every pair of intentions and delays); format bout: you against a scripted fencer that reads your choices (levels 1-2, `spec` opponent), format duel: two players choosing at the same time.
- `bout`: one FIE direct-elimination bout (t.39-t.40): the first to 15 touches wins; 9 minutes of fencing time (one period); at time the fencer ahead wins; at equal scores one more minute for a deciding touch with priority drawn by lot before it (seeded), the priority holder winning if still equal; a double touch counts for both except at 14-14 (not counted); in the extra minute a double leaves the scores equal. Unwillingness to fight (t.124): one minute of fencing time without a touch: the first time both fencers get a P-red card, a penalty touch each; the second time the fencer with the lower score gets the P-black card and loses the bout (at equal scores: the one who loses a lot, seeded); no card at 14-14; the minute restarts after every touch, double, annulled double and penalty touch, not after a phrase without a touch; it does not apply in the extra minute (observation `passivity`)
- `phrase`: every phrase starts with both fencers on guard 1.95 m apart; each fencer has chosen one intention (`spec` intentions) and starts it after 0, 10, 20, 30, 40 or 50 ms (each equally likely, drawn for each fencer and phrase from the seed, after both have chosen); the phrase ends at the first touch (the apparatus: the point's force along the blade above 7.35 N for 2 ms on the opponent's body; the other's touch within 45 ms is a double) or after 3 s without one; it takes its fencing time from the bout clock (a clock that ends during a phrase ends it without a touch, t.44). The phrases were measured in MuJoCo (D1, D8); `spec` phrase_table gives, for every pair of intentions, how many of the 72 equally likely phrases (36 pairs of delays x both ends of the piste) end with a touch for you, for the opponent, a double or none
- `duel`: both players choose their intention for the next phrase; the first player's choice is kept hidden from the other until the phrase is fenced
- `observation`: the state: the score, the phrase number, the fencing time and the time left, the extra minute and the priority, the passivity minute and the P-cards, and every phrase so far (your intention and the opponent's, both start delays, the result, its fencing time, the score after it, cards); the image: 2 rows (side camera beside the piste, top camera above it) x 2 columns (the last phrase half-way and at its end) of 800 x 360 tiles, your robot red, the opponent blue, the points yellow
- `scripted_opponent`: format bout: the computer fencer chooses its intention before each phrase from what it has seen of the bout (both fencers' intentions and the results), never from your choice for this phrase; it knows the phrase table. Level 1 reads you with a few simple models of a player (repeats, answers, copies, plays what just won, goes round the menu) but mostly keeps a slow habit (the best answer to your whole-bout mix); level 2 predicts your next intention from your patterns, also models how you read it, answers what it expects, and now and then plays the table's equilibrium mix
- Winner: the first to 15 touches wins (FIE t.40.1); a second minute without a touch (unwillingness to fight, FIE t.124) loses the bout for the fencer with the lower score, at equal scores for the one who loses a lot (seeded); at the end of the 9 minutes the fencer ahead wins; at equal scores one more minute is fenced and the first touch decides; if the scores are still equal after it, the fencer with priority, drawn by lot (seeded) before the extra minute, wins (FIE t.40.3). There are no draws.
- Deviation D1 (rulebook t.22, t.28-t.31 (the bout's phrases and footwork)): the bout is fenced phrase by phrase: every phrase starts with both fencers on guard 1.95 m apart (pelvis to pelvis), each fencer chooses one of nine intentions (`spec` intentions) executed by fixed skills on the robot, each starts its intention after 0, 10, ... or 50 ms (drawn per phrase), and the phrase ends at the first touch or after 3 s without one; distance, footwork between phrases and the length of the piste are not part of the bout (the screening found the robots' footwork too slow for a bout over the piste: docs/screening/fencing.md)
- Deviation D2 (rulebook t.91, m.19, Material Rules Annexe B): the robot's whole structure is the target (t.91: the whole body), its epee (guard, blade, grip) is not; the apparatus measures the force on the point along the blade (> 7.35 N for >= 2 ms, three consecutive 1 ms samples; lockout 45 ms, inside the 40-50 ms tolerance)
- Deviation D4 (rulebook t.39, t.40): the 9 minutes of fencing time are one period (no one-minute rests); every phrase takes its measured fencing time (to the halt, 3 s without a touch)
- Deviation D5 (rulebook t.38.1.b): at 14-14 a double touch is not counted (the pool bout's rule at 4-4 applied to the 15-touch bout; the 2026 rules have no clause for 14-14 in direct elimination)
- Deviation D8 (rulebook -): the fencer is the robot library's Unitree G1 (bodies/unitree_g1) with the epee on its right wrist mount, its legs, waist and free arm on NVIDIA's SONIC whole-body policy (tracking our en garde, step and lunge motions), its sword arm on the point skill; a lunge from guard covers about 0.25 m in 0.4 s, so the phrases are fenced from 1.95 m, where a lunge reaches the chest; you command it by intentions, not by motions
- Deviation D9 (rulebook t.124): unwillingness to fight as the FIE applies it to direct-elimination bouts (t.124.1): one minute of fencing time without a hit -> 'Halt!'; the first time a P-red card to both fencers, a penalty hit each; the second time the P-black card to the fencer with the lower score, who loses the bout, at equal scores to the fencer who loses a seeded lot (t.124.1.b.i: lots for fencers not in the FIE ranking); no P-card at 14-14 (t.124.3.a): the minute restarts; the minute restarts after each hit, double, annulled double and penalty hit (t.124.3.d), not after a phrase without a touch; t.124 does not apply in the extra minute (t.124.3.f)
- Deviation D11 (rulebook -): the two ends of the piste are not exactly alike in the simulation (the same phrase fenced from the other end ends differently in 205 of the 1431 pairs of mirrored phrases, about one in seven), so each phrase draws the end each fencer fences from, with probability 1/2 each: both fencers meet the same chances

## Geometry and physics
Everything you need is in `spec`: the world frame, the release point, the cameras (pose, field of view, size,
`focal_px`, `principal_point_px`; pinhole: u = cx + f * x_right / depth, v = cy - f * y_up / depth) and the
execution scatter. The physics engine is the phrases: MuJoCo 3.3.7 (1 ms physics steps, 10 ms control steps), two Unitree G1 of the robot library (bodies/unitree_g1, 29 DOF; Unitree's motor torque-speed curves through the library's output stage) with epees, robot x robot, blade x body and blade x blade contacts (bodies/contacts.py), NVIDIA SONIC (GR00T-WholeBodyControl b042411) on the legs, waist and free arm, the point skill on the sword arm, fencing-6's apparatus and phrase referee; each of the 2916 phrases measured once in that world (it is deterministic: 2799 earlier measurements of 1953 of the phrases all ended as in that run, with the same result at the same step) and replayed from sports/fencing/phrases/table.json.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the files the robot tools write included. You may write and run code to compute; every robot command and observation must go through the `efe-robot` MCP tools; code must not contact the simulator. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **2 CPUs**, **4 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the tools take counts. When it is up you are stopped without warning and graded on what stands at that moment, as the sections above say. The service does not count this limit for you: the clocks it reports are the game's own. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. A tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
