#!/usr/bin/env python3
"""Board 0151 (owner, 2026-10-17): the tasks RoboOlympics exports (scripts/roboolympics/exported.toml) are graded by the
LIVE match: the olympiad core's fresh-process validity replay (python -m core.episode, replay_check.json) no longer runs,
and the verdict is the live match the trusted core recorded (scores, match_winner, reason, errors, the seats' metering).
The spectator video (core.spectator / spectator/sport_video.py) stays, a video-only pass after the verdict.

This is a patch on the exported files (PROTOCOL §4c: a re-export must keep it; exported.toml `patched` lists it). It
switches on with the sim service's environment RO_VERDICT_REPLAY=0 (environment/docker-compose.yaml; the convention of
#300's matchlow tasks, whose core already has these hunks), so the core keeps its upstream behaviour (and its own tests)
without it:
  environment/sim/core/service.py   finalize(): no replay; write_final(): valid without the replay term, final.json
                                    verdict_replay false, deterministic null, graded_by "live", replays 0
  environment/sim/core/grading.py   (= tests/grade.py) a final.json with verdict_replay false needs no replay_check.json
  tests/grade.py                    and no replay agreement; reward.json verdict_replay 0, graded_by_live 1, replays 0, no
                                    deterministic and none of the sport's legacy replay_* fields
  environment/docker-compose.yaml   RO_VERDICT_REPLAY: "0"; the video's time limit at least the old replay's (the time the
                                    replay no longer takes)
  task.toml                         the hook's comment; where the video's limit grows to 600 s the hook waits 720 s for it
                                    and 180 s for the verdict (its timeout unchanged); the replay_check.json artifact dropped
  environment/sim/core/realtime.py  (real-time) the control step (apply_pending + m.step) fails under its own `where`,
                                    "world_step": only that, after the agent's first applied act, is the agent's 0
  environment/sim/spectator/sport_video.py   (where present) compares its replay's end with final.json, not replay_check.json
  README.md                         Verification
Every replacement asserts its source text (or that it was applied already: the script is idempotent). Then
scripts/task_conventions.py normalize (DIGEST).
    python3 scripts/roboolympics/live_grading_export.py [--check] [task dir ...]   (default: every exported task)
source_sha: core/ is hashed into every match's source_sha (core/episode.py source_sha(core, sport dirs)), so a patched
task's matches record a new source_sha (old episodes still replay: the replay echoes the header's own source_sha)."""
from __future__ import annotations
import pathlib, re, sys, tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
MARK = "robot_coding_bench (board 0151"

# The hunks are those of #300's matchlow tasks (RO_VERDICT_REPLAY, final.json verdict_replay), so every exported task
# carries the same live-grading code, plus the protocol's own fields (graded_by / replays, graded_by_live).
VR_DOC = (
    '\n\n\nclass _NoReplay(Exception):\n    pass\n\n\ndef verdict_replay() -> bool:\n'
    '    """robot_coding_bench (owner 2026-10-17, board 0151): standard and standard-realtime are graded by the sim\n'
    "    sidecar's live record only. RO_VERDICT_REPLAY=0 (the task's compose file): no fresh-process grading replay; the\n"
    "    verdict (valid_trial, winner) is the live match's; final.json says so (verdict_replay false, deterministic null).\n"
    '    Unset or 1: RoboOlympics\' own rule (the replay must agree)."""\n'
    '    return os.environ.get("RO_VERDICT_REPLAY", "1") != "0"\n\n\n')
SERVICE = [
    ("ROOT = Path(__file__).resolve().parent\nFORFEIT_REASONS", "ROOT = Path(__file__).resolve().parent" + VR_DOC + "FORFEIT_REASONS"),
    ("""        try:
            subprocess.run([sys.executable, "-m", "core.episode", self.plugin, str(self.data)], check=True,""",
     """        try:
            if not verdict_replay():         # live grading (robot_coding_bench, owner 2026-10-17): no replay
                raise _NoReplay
            subprocess.run([sys.executable, "-m", "core.episode", self.plugin, str(self.data)], check=True,"""),
    ("""            self.replay = json.loads((self.data / "replay_check.json").read_text())
        except Exception as exc:  # noqa: BLE001""",
     """            self.replay = json.loads((self.data / "replay_check.json").read_text())
        except _NoReplay:
            pass
        except Exception as exc:  # noqa: BLE001"""),
    ("""            valid = bool(self.finalized and complete and replay_ok and not self.errors""",
     """            live = not verdict_replay()      # live grading: the verdict is this record's, no replay agreement
            valid = bool(self.finalized and complete and (replay_ok or live) and not self.errors"""),
    (""""deterministic": replay_ok, "replay_scores": r.get("scores"),
""", """"deterministic": None if live else replay_ok, "replay_scores": r.get("scores"),
                     "verdict_replay": not live,
"""),
    ("""            compat = {k: v for k, v in sport.items() if k not in final}     # see COMPAT below""",
     """            if live:                             # the protocol's own fields (board 0151): graded by the live match
                final.update(graded_by="live", replays=0)
            compat = {k: v for k, v in sport.items() if k not in final}     # see COMPAT below"""),
]
GRADING = [
    ("""    cont = (d.get("continuous") or {}).get("by_side")
    replay = bool(""", """    cont = (d.get("continuous") or {}).get("by_side")
    live = d.get("verdict_replay") is False    # live grading (robot_coding_bench, owner 2026-10-17): no replay
    replay = bool("""),
    ("""(d.get("valid_trial") and d.get("finalized") and replay and complete""",
     """(d.get("valid_trial") and d.get("finalized") and (replay or live) and complete"""),
    ("""    valid = bool(d.get("valid_trial") and d.get("finalized") and (replay or live) and complete and not errors)
""", """    valid = bool(d.get("valid_trial") and d.get("finalized") and (replay or live) and complete and not errors)
    # robot_coding_bench (board 0151; STANDARD_MODE Part 3): in a real-time match graded live and finalized, a simulator
    # error of the control step itself (every errors[] entry where "world_step": the agent's commands applied, then the
    # world's step; core/realtime.py) after the agent's first applied act is the agent's 0, never a technical failure (a
    # free retry); before it, any other technical error (bookkeeping, rendering, metering) or an unfinalized record stays
    # infrastructure. The match ended at that error, so every act the seat applied came before it.
    agent_sim_error = bool(live and d.get("finalized") and d.get("slowdown") and d.get("reason") == "technical_error"
                           and d.get("errors")
                           and all(isinstance(e, dict) and e.get("where") == "world_step" for e in d["errors"])
                           and not any(d["meter_error"].values()) and not any(d["proxy_error"].values())
                           and int(((d.get("seats") or {}).get(seats[0]) or {}).get("applied") or 0) > 0)
    valid = valid or agent_sim_error
"""),
    ("""    else:
        success = valid
    out = dict(""", """    else:
        success = valid
    success = success and not agent_sim_error
    out = dict("""),
    ("""missing_log=0, deterministic=int(replay), match_over=""", """missing_log=0, verdict_replay=int(not live), match_over="""),
    ("""abandoned=int(d.get("reason") == "abandoned"))
    hidx = hidden_index(d, contract)""", """abandoned=int(d.get("reason") == "abandoned"))
    if not live:
        out["deterministic"] = int(replay)
    hidx = hidden_index(d, contract)"""),
    (("""    out.update(evaluate(d))
    if (contract""",                               # the exported core, or #300's hunk without the protocol's fields:
      """    out.update(evaluate(d))
    if live:                                   # no grading replay ran: the sport's replay_* fields would read as errors
        for k in [k for k in out if k.startswith("replay_")]:
            del out[k]
    if (contract"""), """    out.update(evaluate(d))
    if live:                                   # no grading replay ran: the sport's replay_* fields would read as errors
        for k in [k for k in out if k.startswith("replay_")]:
            del out[k]
        out.update(graded_by_live=1, replays=0, agent_sim_error=int(agent_sim_error))   # board 0151
    if (contract"""),
    ("""        d, r = (json.loads((DATA / f).read_text()) for f in ("final.json", "replay_check.json"))""",
     """        d = json.loads((DATA / "final.json").read_text())
        rc = DATA / "replay_check.json"         # absent under live grading (final.json verdict_replay false)
        r = json.loads(rc.read_text()) if rc.exists() or d.get("verdict_replay") is not False else {}"""),
]
REALTIME = [
    ("""                    self.apply_pending()
                    events = self.m.step()
""", """                    try:                                # robot_coding_bench (board 0151): the control step itself
                        self.apply_pending()
                        events = self.m.step()
                    except Exception as exc:  # noqa: BLE001
                        exc.rcb_where = "world_step"    # its own `where` in final.json errors (tests/grade.py)
                        raise
"""),
    ("""        except Exception as exc:  # noqa: BLE001
            self.failure("world", exc)""",
     """        except Exception as exc:  # noqa: BLE001
            self.failure(getattr(exc, "rcb_where", "world"), exc)   # world_step: the control step; else bookkeeping"""),
]
SPORT_VIDEO = [
    ("""video.json records whether this replay ended in the verdict replay's
state (replay_check.json state_sha, scores, k).""", """video.json records whether this replay ended in the live match's
recorded state (final.json state_sha, scores, steps; board 0151: no verdict replay)."""),
    ("""    try:
        rc = json.loads((Path(data) / "replay_check.json").read_text())
    except (OSError, ValueError):
        rc = {}
    same = bool(rc) and all(res.get(k) == rc.get(k) for k in ("state_sha", "scores", "k"))""",
     """    try:                                    # robot_coding_bench (board 0151): the live record, no verdict replay
        fin = json.loads((Path(data) / "final.json").read_text())
    except (OSError, ValueError):
        fin = {}
    same = bool(fin) and res.get("state_sha") == fin.get("state_sha") and res.get("scores") == fin.get("scores") \\
        and res.get("k") == fin.get("steps")"""),
    ('"matches_verdict_replay": same', '"matches_live_record": same'),
]
README_RX = re.compile(r"Separate sandbox, no network\. The sim service replays the recorded match in a fresh process; the verifier\n"
                       r"\(`tests/grade\.py`, our core's grader\) checks that the replay agrees with the live match, applies the validity rule\n")
README_NEW = ("Separate sandbox, no network. The match is graded live (owner, 2026-10-17, board 0151): the sim service records the\n"
              "match's scores, winner and reason as it plays it and nothing replays it to grade it (`final.json` `graded_by` live,\n"
              "`replays` 0; the replay video is drawn after the verdict). The verifier (`tests/grade.py`, our core's grader) applies\n"
              "the validity rule\n")
HOOK_RX = re.compile(r"# Then SIGUSR1 ends the match: the service replays it in a fresh process, checks the replay and writes the verdict\n"
                     r"# \(\"graded_ready\"\)")
HOOK_NEW = ("# Then SIGUSR1 ends the match: the service writes the verdict of the live match (\"graded_ready\"; no grading replay,\n"
            "# board 0151)")


def sub_all(s: str, pairs, what: str) -> str:
    """Each (old, new): new already there, or exactly one old (a tuple: alternatives, the first found) replaced by it."""
    for old, new in pairs:
        if new in s:
            continue
        olds = old if isinstance(old, tuple) else (old,)
        hit = [o for o in olds if s.count(o) == 1]
        assert hit, f"{what}: expected one {olds[0][:70]!r}"
        s = s.replace(hit[0], new)
    return s


def patch(t: pathlib.Path) -> dict[str, str]:
    out = {}
    rd = lambda rel: (t / rel).read_text()  # noqa: E731
    out["environment/sim/core/service.py"] = sub_all(rd("environment/sim/core/service.py"), SERVICE, f"{t.name} service.py")
    for rel in ("environment/sim/core/grading.py", "tests/grade.py"):
        out[rel] = sub_all(rd(rel), GRADING, f"{t.name} {rel}")
    if t.name.endswith("-standard-realtime"):       # the real-time loop: the control step's own `where`
        out["environment/sim/core/realtime.py"] = sub_all(rd("environment/sim/core/realtime.py"), REALTIME,
                                                          f"{t.name} realtime.py")
    if (t / "environment/sim/spectator/sport_video.py").is_file():
        out["environment/sim/spectator/sport_video.py"] = sub_all(rd("environment/sim/spectator/sport_video.py"),
                                                                  SPORT_VIDEO, f"{t.name} sport_video.py")
    c = rd("environment/docker-compose.yaml")
    if 'RO_VERDICT_REPLAY: "0"' not in c:
        c = re.sub(r'(?m)^(\s+)RO_REPLAY_TIMEOUT_S: "(\d+)"\n',
                   lambda m: f'{m.group(1)}RO_REPLAY_TIMEOUT_S: "{m.group(2)}"\n{m.group(1)}RO_VERDICT_REPLAY: "0"\n', c, count=1)
        assert 'RO_VERDICT_REPLAY: "0"' in c, f"{t.name}: no RO_REPLAY_TIMEOUT_S in the compose file"
    rep = int(re.search(r'RO_REPLAY_TIMEOUT_S: "(\d+)"', c).group(1))
    vid = re.search(r'RCB_VIDEO_TIMEOUT_S: "(\d+)"', c)
    tt = rd("task.toml")
    if vid and int(vid.group(1)) < rep and re.search(r'for i in \$\(seq 1 600\); do grep -q .*for i in \$\(seq 1 ' + vid.group(1)
                                                         + r'\); do \[ -f /data/video\.json', tt):
        # the video's limit at least the verdict replay's had (which no longer runs), and the hook waits 120 s more than
        # that limit for it; the hook's own timeout unchanged: the verdict wait shrinks by what the video wait grows
        # (the verdict is written at the match's end now: 600 -> 180 s for a 300 -> 720 s video wait)
        new_vid, wait = rep, rep + 120
        verdict_wait = 600 - (wait - int(vid.group(1)))
        assert verdict_wait >= 120, f"{t.name}: the verdict wait would be {verdict_wait} s"
        c = c.replace(f'RCB_VIDEO_TIMEOUT_S: "{vid.group(1)}"', f'RCB_VIDEO_TIMEOUT_S: "{new_vid}"', 1)
        tt = re.sub(r"for i in \$\(seq 1 600\); do grep -q", f"for i in $(seq 1 {verdict_wait}); do grep -q", tt, count=1)
        tt = re.sub(r"for i in \$\(seq 1 " + vid.group(1) + r"\); do \[ -f /data/video\.json",
                    f"for i in $(seq 1 {wait}); do [ -f /data/video.json", tt, count=1)
    out["environment/docker-compose.yaml"] = c
    if HOOK_NEW not in tt and "no grading\n# replay" not in tt and "no grading replay" not in tt:   # (#300's tasks say it already)
        tt, n = HOOK_RX.subn(HOOK_NEW, tt)
        assert n == 1, f"{t.name}: the collect hook's comment"
    tt = re.sub(r'(?m)^  \{ source = "/data/replay_check\.json", service = "sim" \},\n', "", tt)
    out["task.toml"] = tt
    r = rd("README.md")
    if README_NEW not in r and "Live grading (owner 2026-10-17" not in r:   # (#300's tasks say it already)
        r, n = README_RX.subn(README_NEW, r)
        assert n == 1, f"{t.name}: README Verification"
    out["README.md"] = r
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    dirs = [pathlib.Path(a) for a in argv if a != "--check"]
    if not dirs:
        reg = tomllib.loads((ROOT / "scripts/roboolympics/exported.toml").read_text())
        dirs = [ROOT / "tasks" / e["name"] for e in reg["tasks"]]
    import task_conventions as TC
    bad = []
    for t in dirs:
        files = patch(t)
        changed = [rel for rel, s in files.items() if (t / rel).read_text() != s]
        if check:
            bad += [f"{t.name}: {rel}" for rel in changed]
            continue
        for rel in changed:
            (t / rel).write_text(files[rel])
        TC.normalize(t)
        print(f"{t.name}: {len(changed)} file(s) patched")
    for b in bad:
        print("would change:", b)
    if check:
        print(f"live_grading_export --check: {len(dirs)} task(s), {len(bad)} difference(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
