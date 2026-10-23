# Annotated whole-trial video

**One source, one video.** The only footage of a trial is the graded replay (`verifier/replay.mp4`, simulated time).
In a trial without resets it already holds all the robot's motion; `pipeline video` re-times it to the agent's wall
clock and draws the annotations on every frame. Code only: no model, no tokens.

## How a frame gets its wall time

| source | gives |
|---|---|
| service log `service/K/episode.jsonl` (from the board: `sync --fetch`) | each call: begin / end time, physics steps run, type (`submit ee_pose ×20`, `observe`, `reset`) |
| replay | frames at a fixed number of physics steps each |
| agent log `events/K.jsonl` | every message, reasoning and action with its minute |

Replay frame of a call = cumulative physics steps / all steps × frames. The video is a list of **beats**:

| beat | what plays | length |
|---|---|---|
| `move` | a call that ran physics: its replay frames | native (25 fps) |
| `call` | a call without physics (observe, ...) | 0.3 s |
| `idle` | the agent thinks or waits: the last frame held | gap / 40, within [0.25, 1] s; `--max-idle 0` drops them |

Steps before the last reset are not in the replay: those beats show a placeholder.

Check of the method (`sync --check`, the one trial whose board frame table is local): 590 frames, median error 0.21 s,
max 1.04 s on a 24 s replay.

## What is drawn on each frame (`pipeline/fullvideo.py`, class `Band`)

| element | where | from |
|---|---|---|
| wall clock `mm:ss / budget` | band, top left | beat wall time |
| current event kind and id | band, top | `events/` (last event at or before this minute) |
| robot call chip (`submit ee_pose ×20`) | band, top right | service log |
| 说: the agent's last message | band, line 2 | `events/` |
| 做: the current action, first line | band, line 3 | `events/` |
| what the agent saw (thumbnail) | picture, top right | `looks/` (newest image within 2 min) |
| recap mark near this moment (±0.4 min): progress, failure, decision, point of no return | picture, top left | `verified_recaps/` |
| strip of the whole trial with all marks and a cursor | band, bottom | `verified_recaps/` |

## Files

| file | content |
|---|---|
| `fullvideo/K.mp4` | H.264, picture + 176 px band, 25 fps |
| `fullvideo/K.jpg` | poster (a frame at one third) |
| `fullvideo/K.json` | `{"duration": s, "beats": [[video s0, video s1, wall min0, wall min1, kind], ...]}` |
| `videomap/K.json` | graded replay ↔ wall clock (`sync`): `points: [[wall abs s, video s], ...]` |

The platform maps both ways with the beats: wall minute → the beat whose wall span holds it → linear inside; video
second → the beat whose video span holds it. A click on any quote seeks the video; playing the video moves the
timeline cursor and the log.

## Speed and size

| | demo (30-min session, 24 s replay) | estimate per trial (replays: mean 125 s, 7.2 MB) |
|---|---|---|
| video length | 57 s (25 s with `--max-idle 0`) | replay length + ~30 s |
| render | 16 s on CPU | ~0.3 × video length |
| size | 3.5 MB (2.5 MB without pauses); replay 2.3 MB | 1.1–1.5 × the replay |

## Limits

- Needs the service log per trial (a valid board token for `sync --fetch`).
- Trials with resets: earlier episodes would need a re-render of the action log in the simulator image
  (`../tools/viz/hires/` has that chain for RoboTwin; other benches are not done).
- Chromium builds without H.264 (e.g. the headless one used in tests) cannot play the video; Chrome and Safari can.

`../tools/viz/` is an earlier prototype for one Codex + RoboTwin trial and the high-resolution Blender re-render;
this module is the general version.
