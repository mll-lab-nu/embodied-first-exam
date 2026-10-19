# viz: annotated replays of agent trials

Status (2026-10-19): a working prototype on one trial (codex · GPT-6 Astra · RoboTwin put_bottles_dustbin, standard,
`…__YdHsp73`). The generic modules under "Next" are not written yet.

| file | does |
|---|---|
| `events.py` | ATIF `agent/trajectory.json` → `events.json`: the agent's sentences, the commands it typed, its looks (the images it received go to `looks/`), its `RESULT` lines. Codex only; `RESULT` is this agent's own print |
| `render.py` | `verifier/replay.mp4` (or `--views` frames) + events → annotated mp4: a chip per command, a freeze with the agent's own image per look, its sentences, clock, counters, 30-min timeline. `--service` uses the service log for when each image was taken; `--scale 2` gives 2560×1440 |
| `hires/sapien_film.py` | inside the RoboTwin image: replay `trajectory.npz`, stop unless the final state hash matches, record every shape and camera every 25 physics steps (the replay's frames) |
| `hires/cycles_studio.py` | Blender Cycles with `exam_media/film_blender.py`'s cinematic studio (its own functions, unchanged): a 3/4 studio camera plus the agent's cameras |
| `hires/robotwin.sh` | the high-resolution chain for one clip (optional backend) |
| `get_fonts.sh` | the overlay fonts into `fonts/` (not in git) |

Rules the renderer keeps:
- The agent gets an image only when its tool call returns. A command typed in the same call was written before the
  agent saw the image, so it is shown before the look.
- A look card says when its image was taken. When the robot has moved since, the card says so.

## Files

Per trial, outside git: `/data/pingyue/cross-bench/viz/<key>/`

| path | content |
|---|---|
| `events.json`, `looks/` | from `events.py` |
| `service/` | `episode.jsonl`, `live_timeline.jsonl` from the board |
| `clips/` | `<from>-<to>.mp4`, `<from>-<to>_2k.mp4`, the replay frames a clip uses |
| `hires/` | `task/` (task files of the trial's commit), `film/`, `frames/`, `blender.log` |
| `page/` | a page published with `pub` (8766) |

## Commands

```
python3 tools/viz/events.py $RAW/<key> $VIZ/<key>/events.json
python3 tools/viz/render.py $RAW/<key> $VIZ/<key>/events.json $VIZ/<key>/clips/0600-0845.mp4 --from 06:00 --to 08:45 \
        --service $VIZ/<key>/service/episode.jsonl
BEL_TOKEN=... tools/viz/hires/robotwin.sh <key> <task commit> 06:00 08:45
```

## Next

Code: `agentlog.py` (per harness), `servicelog.py` (service log families), `sync.py` (wall clock join, frame map, image
self-check), `layouts.json` (which camera each replay tile is), `player/` (web player over the replay), `viz.py` (CLI).
Agent steps (`meta/prompts/viz-*.md`): what each agent-defined helper does, which segment to show, a frame check.
