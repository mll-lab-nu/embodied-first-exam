# Full-simulator program task: fencing, level 2, seed 35

The development source at `/opt/fullsim` is complete and CPU-only: the frozen simulator of `embodied-olympics-match-fencing-bout-i02-standard` (this task's turn-based
twin), its referee, its phrase table and its scripted fencer. No GPU, renderer or simulator service is needed. Run the
commands inside the task's agent container from `/app`.

## First command: inspect, play and reset the actual simulator

```bash
python -c 'from tools.fullsim.turn import TurnSession; s=TurnSession("fencing", level=2, seed=35); print(s.state()["scores"]); print(s.act({"type": "phrase", "intention": "lunge"})["applied"]); print(s.reset()["scores"])'
```

`s.world` is the entire mutable Match object: the bout, the phrase table and the scripted fencer. `s.spec()` gives the
original action interface, the intentions, the phrase table's counts and the rules as the twin's `game spec` states
them. `act(command)` handles an action as the live service does (parse, apply: the phrase is chosen, played and
judged); `reset()` rebuilds the whole bout with the same seed. Private changes and repeated resets are allowed in
development; none of them reaches the formal bout. The sport's code: `sports/fencing/` (`plugin.py`, `sport.toml`,
`phrases.py`, `bout.py`, `opponent.py`).

## Submit a persistent program

Create `/app/output/policy/program.py`:

```python
def make_policy(config):
    # config["spec"]: the original action interface, the intentions, the phrase table, the rules, cfg, frozen_commit
    return Policy()


class Policy:
    def act(self, view):
        if view["state"]["phase"] == "unit_over":
            return {"type": "ready"}
        return {"type": "phrase", "intention": "lunge"}  # replace with your decision
```

Helpers and data must be regular files under `policy/` (at most 512 files, 32 MiB in all; no links, devices, FIFOs
or sockets); they are importable by file name. The object lives for the whole bout. It is called once per decision:
on your turn (`state.phase` `playing`: return one phrase action) and at the review after each of your phrases
(`state.phase` `unit_over`: return `{"type": "ready"}`). The view: `state` (the twin's observation fields; `phrase`,
`score`, `phrases` so far, the clocks; `service_phase` the core's own), `truth`, `scores` and an empty `observation`.
There is no formal reset and no handle on the formal bout; you may build your own private `TurnSession` for
predictions.

`truth` (the current state only):

`view["truth"]` is the state of the bout at the decision (nothing of the coming phrase):

- `bout`: the referee's whole state (`score`, fencing time `t`, the minute's start, `extra` minute, `priority`,
  `p_calls`, `winner`, `how`, and `log`: every phrase so far with both intentions, both start delays, the ends of the
  piste, the result and the score after it); `phrase` (the next phrase's number), `time_left_s`, `no_hit_s`;
- `opponent`: the scripted fencer's whole state (`level`, its history `hist` of what it has seen, and its random
  generator's state `rng`): with the simulator (`sports/fencing/opponent.py`) its next choice can be computed;
- `table_sha256`: the phrase table's digest (`sports/fencing/phrases/table.json`, the 2916 measured phrases).

A turn sport: there is no world between decisions. Each of your actions is your intention for the next phrase
(`{"type": "phrase", "intention": ...}`, the nine intentions of `Session.spec()`); the scripted fencer chooses its own
from what it has seen of the bout (never from your choice for this phrase), and the phrase is played from the measured
table with this phrase's start delays and ends, drawn from the seed (`sports/fencing/phrases.py` `play`), then judged
(`sports/fencing/bout.py`). The rules (FIE direct elimination: 15 touches or 9 minutes of fencing time, the extra
minute, unwillingness to fight) and the table: `Session.spec()` and `sports/fencing/sport.toml`.

## Developer self-test of your saved program

```bash
python -m tools.fullsim.turn --sport fencing --policy /app/output/policy --level 2 --seed 35 \
  --out /tmp/my-self-test-1 --unsafe-local
```

Use a new output directory each time. This plays a fresh bout on the original turn service with your program, then
replays the journal in a fresh process. `--unsafe-local` is a self-test, not the trusted grading boundary.

The formal evaluation runs in a separate verifier without network: root owns the trusted simulator and the logs; your
program runs as nobody, with a read-only public copy of the simulator and a writable scratch directory. Program load
30 s, each exchange 5 s, the chess clock 3600 s on your turns (as in the twin), the formal bout 4200 s of wall
time, 2 GiB of address space, 4200 CPU seconds. No model or API calls in the formal evaluation. Success: a
complete win by the original referee, confirmed by a fresh replay. A missing, invalid, stuck or unfinished program does
not win. The deliverable is a program, not a list of intentions. After the verdict the verifier replays the formal
bout's record once more and draws `/logs/verifier/replay.mp4` as the twin's service draws its video, for spectators
only (nothing reads it back; a failed render leaves no video).
