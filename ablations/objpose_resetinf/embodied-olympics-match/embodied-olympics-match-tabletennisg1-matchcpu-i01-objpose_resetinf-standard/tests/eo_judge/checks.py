"""The judge's input checks (fwspec verdict.schema.yaml `checks`; fw_pattern_1020.md §3.8 "Task 锁定要求，Run 记录实际
交付，Judge 核对"). Each check is pass, fail or n/a (the evidence has nothing to check); a failed check is a fault
(rules.py says which class), n/a never is.

  fixture_matches        the Fixture record's digest (recomputed) is the one the Run executed
  release_matches        the Task release digest recomputed from the sealed Task files (TaskSpec, instruction, lock)
                         equals the Run's, the Fixture's and the world report's; for a legacy task: the sha256 of the
                         sealed TaskSpec file equals what the match service reported (it used to be copied unchecked)
  images_match_lock      the images the Run started are the lock's images (by digest)
  fingerprint_meets_requirements  images, delivered resources and real-time integrity all meet the release
  evidence_complete      every item the verdict needs was sealed, and no sealed item changed since
  delivered_resources    every seat got at least the TaskSpec's seat resources (whole cores, memory, GPUs)
  integrity              the world's lag, late steps, render and plan misses are within the TaskSpec tolerance
  replay                 the fresh-process replay agrees with the live match
  routes_match_entries   every seat's model calls went through the route its Entry declares
  carry_matches          every seat's carried-in snapshot is the Fixture's

The Task release digest follows fwspec task-release.schema.yaml:
  release = sha256(JCS({"schema": "eo-task-release/1", "taskspec": d_spec, "instruction": d_inst, "lock": d_lock}))
  d_spec = sha256(JCS(taskspec)), d_inst = sha256(instruction bytes), d_lock = sha256(JCS(lock minus provenance)).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import canon

CHECKS = ("fixture_matches", "release_matches", "images_match_lock", "fingerprint_meets_requirements",
          "evidence_complete", "delivered_resources", "integrity", "replay", "routes_match_entries", "carry_matches")
_SIZE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(KiB|MiB|GiB|TiB)$")
_UNIT = {"KiB": 1 << 10, "MiB": 1 << 20, "GiB": 1 << 30, "TiB": 1 << 40}


# tolerance keys that are not a world reading's limit: the per-seat outages (judged per seat by the model access rule,
# verdict.gateway_faults; the gateway / provider seconds of older TaskSpecs), the miss fractions' count floors
PER_SEAT_TOLERANCE = ("gateway_outage_max_s", "provider_outage_max_s", "model_access_lost")
# a miss fraction breaches only when the late items are more than its floor too (MAINPORT 10-21: with ~65 acts a
# match, one late act was 1.5 % and voided a duel): late > max(fraction x total, floor); default floor 2
MISS_FLOORS = {"render_miss_fraction": "render_miss_floor", "plan_miss_fraction": "plan_miss_floor"}
DEFAULT_MISS_FLOOR = 2
# the fault code of each world reading over its tolerance (fwspec verdict.schema.yaml faults.code)
INTEGRITY_CODES = {"world_lag_p99_s": "world_lag_p99", "world_lag_max_s": "world_lag_max",
                   "late_step_p99_s": "late_step_p99", "render_miss_fraction": "render_deadline_miss",
                   "plan_miss_fraction": "plan_deadline_miss", "max_stall_s": "world_stall"}


def miss_counts(meas: dict, key: str) -> tuple[int, int] | None:
    """(late, total) behind a miss fraction, from the Host's integrity block (core 0.5.0: plan misses = the seats'
    late acts of all acts; a platform side's own planning time is its program latency, never a plan miss; render
    misses = late observations of all observations); None when the block has no counts (an older Host: the fraction
    is judged alone)."""
    def n(k):
        v = meas.get(k)
        return int(v) if _number(v) else None
    if key == "plan_miss_fraction":
        late, total = n("late_acts"), n("acts")
        if late is None or total is None:
            return None
        return late, total
    if key == "render_miss_fraction":
        late, total = n("late_observations"), n("observations")
        return (late, total) if late is not None and total is not None else None
    return None


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def size_bytes(s) -> float | None:
    m = _SIZE.match(str(s or ""))
    return float(m.group(1)) * _UNIT[m.group(2)] if m else None


def logical_cpus(seat: dict) -> int | None:
    """The logical CPUs a seat got: the size of its cpuset ("3-5,19-21" is 6), else its `logical_cpus` / `cpus`;
    None when the record says neither."""
    cs = seat.get("cpuset")
    if isinstance(cs, str) and cs.strip():
        try:
            n = 0
            for part in (x.strip() for x in cs.split(",")):
                if part:
                    lo, _, hi = part.partition("-")
                    a = int(lo)
                    n += (int(hi) if hi else a) - a + 1
            return n
        except ValueError:
            pass
    for k in ("logical_cpus", "cpus"):
        if isinstance(seat.get(k), (int, float)) and not isinstance(seat.get(k), bool):
            return int(seat[k])
    return None


def nothing_delivered(seat: dict | None) -> bool:
    """A seat record with no container behind it: no cpuset, no memory, no whole cores (what a backend reports for a
    seat whose containers never ran)."""
    if not seat:
        return True
    return not str(seat.get("cpuset") or "").strip() and not size_bytes(seat.get("memory")) and \
        not seat.get("whole_cores")


def release_preimage(taskspec: dict, instruction: bytes, lock: dict) -> dict:
    return {"taskspec": canon.digest(taskspec), "instruction": canon.bytes_digest(instruction),
            "lock": canon.digest({k: v for k, v in lock.items() if k != "provenance"})}


def release_digest(taskspec: dict, instruction: bytes, lock: dict) -> str:
    """The Task release digest (task-release.schema.yaml)."""
    return canon.digest({"schema": "eo-task-release/1", **release_preimage(taskspec, instruction, lock)})


def recompute_release(task: dict) -> tuple[str, str]:
    """(release, how): framework.task.verify.task_identity over the Task directory when the Task package is importable
    (one implementation of the rule), else this module's release_digest over the same three files."""
    d = task.get("dir")
    if d:
        try:
            from framework.task.verify import task_identity  # noqa: PLC0415  (IMPL-TASK)
            return task_identity(Path(d))["release"], "framework.task.verify.task_identity"
        except ImportError:
            pass
    return release_digest(task["taskspec"], task["instruction"], task["lock"]), "framework.judge.checks.release_digest"


def fixture_digest(fixture: dict) -> str:
    return canon.digest({k: v for k, v in fixture.items() if k != "fixture_digest"})


def _same(a, b) -> bool:
    """Digests compare equal when one is a prefix of the other (examples write 8 hex digits, records 64)."""
    if not (isinstance(a, str) and isinstance(b, str)):
        return False
    a, b = a.lower(), b.lower()
    return a.startswith(b) or b.startswith(a)


class Result:
    """The check values and the findings behind each failed one: {check: [(code, note)]}."""

    def __init__(self):
        self.value = {c: "n/a" for c in CHECKS}
        self.why: dict = {}
        self.notes: dict = {}

    def set(self, name, ok: bool | None, code=None, note=None):
        if ok is None:
            return
        if not ok:
            self.value[name] = "fail"
            self.why.setdefault(name, []).append((code or name, note or ""))
        elif self.value[name] != "fail":
            self.value[name] = "pass"


def run_checks(ev, facts) -> Result:
    """All checks over the evidence (`facts`: the judge's derived facts, rules.Facts)."""
    res = Result()
    run, fx, task = ev.run or {}, ev.fixture, ev.task or {}
    # fixture
    if fx is not None:
        fd = fixture_digest(fx)
        ok = _same(fd, fx.get("fixture_digest")) if fx.get("fixture_digest") else True
        rd = (run.get("fixture") or {}).get("digest")
        res.set("fixture_matches", ok and (rd is None or _same(fd, rd)), "fixture_mismatch",
                f"fixture digest {fd[:15]}, recorded {str(fx.get('fixture_digest'))[:15]}, run {str(rd)[:15]}")
    # release: recomputed from the sealed Task files; release.json, the Fixture, the Run, the world report and the
    # Runner's own check at the start (fingerprint.json task_package) must all name it
    ts, inst, lock = task.get("taskspec"), task.get("instruction"), task.get("lock")
    if isinstance(ts, dict) and task.get("kind") == "eo-taskspec/1" and inst is not None and isinstance(lock, dict):
        rel, how = recompute_release(task)
        res.notes["release"], res.notes["release_how"] = rel, how
        check = (ev.fingerprint or {}).get("task_package") or \
            ((run.get("execution_fingerprint") or {}).get("task_package"))
        claims = {"run": run.get("task_release"), "fixture": ((fx or {}).get("task") or {}).get("release"),
                  "world_report": (ev.world or {}).get("task_release") if ev.world_kind == "eo-world-report/1"
                  else None, "release_record": (task.get("release") or {}).get("release"),
                  "runner_check": (check or {}).get("release")}
        bad = {k: v for k, v in claims.items() if v is not None and not _same(rel, v)}
        res.set("release_matches", not bad, "release_mismatch",
                f"recomputed {rel[:15]} ({how}); differs: " +
                ", ".join(f"{k} {str(v)[:15]}" for k, v in sorted(bad.items())))
        if isinstance(check, dict) and check.get("ok") is False:
            res.set("release_matches", False, "task_check_failed",
                    "the Runner's check of the Task package at the start failed: " +
                    "; ".join(str(x) for x in (check.get("problems") or [])[:5]))
        res.notes["release_claims"] = {k: v for k, v in claims.items() if v is not None}
    if task.get("runtime_taskspec_bytes") is not None and facts.legacy:
        own = canon.sha256_hex(task["runtime_taskspec_bytes"])
        said = ((ev.world or {}).get("taskspec") or {}).get("sha256")
        res.notes["taskspec_sha256"] = own
        if said is not None:
            res.set("release_matches", said == own, "taskspec_mismatch",
                    f"the sealed TaskSpec file is {own[:12]}, the match service reported {str(said)[:12]}")
    # images
    fp = run.get("execution_fingerprint") or {}
    arts = (lock or {}).get("artifacts") or {}
    if fp.get("images") and arts:
        # B6 (FWTEST2 10-21): an image the Run never started has no identity to compare (a Run that never reached the
        # start records null): nothing to check, never a mismatch. Once play began, an image the Run did not record
        # cannot be shown to be the lock's
        have = fp.get("images") or {}
        locked = [k for k in ("official_runtime", "seat_runtime") if (arts.get(k) or {}).get("digest")]
        bad = [k for k in locked if have.get(k) and not _same((arts.get(k) or {}).get("digest"), have.get(k))]
        unrecorded = [k for k in locked if not have.get(k)]
        if bad:
            res.set("images_match_lock", False, "image_mismatch", "image(s) not the lock's: " + ", ".join(bad))
        elif unrecorded and facts.started:
            res.set("images_match_lock", False, "image_unrecorded",
                    "the match was played but the Run did not record its image(s): " + ", ".join(unrecorded))
        elif len(unrecorded) < len(locked):
            res.set("images_match_lock", True)
    # delivered resources. CPUs: the TaskSpec's `cpus` against the logical CPUs of the seat's whole cores (the size of
    # its cpuset). The unit is the vCPU, one hardware thread (Chi 10-31; fwspec taskspec.schema.yaml): the Runner's
    # pool hands out whole cores by logical CPU (8 = 4 cores with their two threads), and the judge counts logical CPUs.
    need = (ts or {}).get("seat_resources") if task.get("kind") == "eo-taskspec/1" else None
    got = ((run.get("delivered") or {}).get("seats")) or {}
    if need and got:
        short, seen = [], 0
        for seat in facts.seats:
            g = got.get(seat)
            if not facts.started and nothing_delivered(g):
                continue              # B6: the seat's containers never ran because the match never started: n/a
            seen += 1
            if g is None:
                short.append(f"{seat}: nothing delivered")
                continue
            have = logical_cpus(g)
            if have is None:
                have = int(g.get("whole_cores") or 0)
            if have < int(need.get("cpus") or 0):
                short.append(f"{seat}: {have} logical CPUs (cpuset {g.get('cpuset')}, {g.get('whole_cores')} whole "
                             f"cores) < cpus {need.get('cpus')}")
            gm, nm = size_bytes(g.get("memory")), size_bytes(need.get("memory"))
            if nm is not None and (gm is None or gm < nm):
                short.append(f"{seat}: memory {g.get('memory')} < {need.get('memory')}")
            if int(need.get("gpus") or 0) > 0 and not g.get("gpu"):
                short.append(f"{seat}: no GPU")
        if seen:
            res.set("delivered_resources", not short, "under_resourced", "; ".join(short))
    # integrity: every declared tolerance against the world's reading (world lag p99 and its single spike, late steps,
    # render and plan misses), each breach a fault of its own code (INTEGRITY_CODES); a miss fraction breaches only
    # with more late items than its floor too (MISS_FLOORS). The per-seat model access is the model access rule's
    # (verdict.gateway_faults). A declared tolerance without a reading (render misses when the task declares no camera
    # latency, a core before 0.4.0) is listed in diagnostics.integrity_unmeasured; no reading at all: n/a.
    tol = ((ts or {}).get("integrity") or {}).get("tolerance") if task.get("kind") == "eo-taskspec/1" else None
    meas = facts.integrity
    if tol and meas:
        limits = sorted(k for k, v in tol.items() if _number(v) and k not in PER_SEAT_TOLERANCE
                        and k not in MISS_FLOORS.values())
        measured = [k for k in limits if _number(meas.get(k))]
        for k in measured:
            value, limit = meas[k], tol[k]
            if value <= limit:
                continue
            note = f"{k} {value} > {limit}"
            if k in MISS_FLOORS:
                floor = tol.get(MISS_FLOORS[k])
                floor = int(floor) if _number(floor) else DEFAULT_MISS_FLOOR
                counts = miss_counts(meas, k)
                if counts is not None:
                    if counts[0] <= floor:          # a fraction over its limit with no more late items than the floor
                        res.notes.setdefault("integrity_under_floor", []).append(
                            f"{k} {value}: {counts[0]} late of {counts[1]}, not more than the floor {floor}")
                        continue
                    note += f" ({counts[0]} late of {counts[1]}, more than the floor {floor})"
            res.set("integrity", False, INTEGRITY_CODES.get(k, "integrity"), note)
        if measured:
            res.set("integrity", True)                   # pass unless a breach above failed it
        res.notes["integrity_unmeasured"] = [k for k in limits if not _number(meas.get(k))]
    # fingerprint = images + resources + integrity
    parts = [res.value[c] for c in ("images_match_lock", "delivered_resources", "integrity")]
    if "fail" in parts:
        res.value["fingerprint_meets_requirements"] = "fail"
    elif "pass" in parts:
        res.value["fingerprint_meets_requirements"] = "pass"
    # replay
    if facts.replay_ok is not None:
        res.set("replay", facts.replay_ok, "replay_mismatch", facts.replay_note)
    # routes
    entries = facts.entry_routes
    if entries:
        bad = []
        for seat, want in sorted(entries.items()):
            seen = (fp.get("model_routes") or {}).get(seat) or {}
            if not seen:
                continue
            if want.get("gateway_route") and seen.get("route") != want["gateway_route"]:
                bad.append(f"{seat}: route {seen.get('route')} != {want['gateway_route']}")
            dep, pool = want.get("deployment"), want.get("failover")
            if dep and pool != "same_deployment_pool":
                other = [d for d in seen.get("deployments_seen") or [] if d != dep]
                if other:
                    bad.append(f"{seat}: deployments {other} besides {dep}")
        res.set("routes_match_entries", not bad, "route_mismatch", "; ".join(bad))
    # carry
    carry, fx_in = run.get("carry") or {}, (fx or {}).get("carry_in") or {}
    if carry and fx_in:
        bad = []
        for seat, c in sorted(carry.items()):
            want = fx_in.get(seat)
            want_d = want if isinstance(want, str) else (want or {}).get("snapshot")
            have = c.get("in")
            if want_d in (None, "none") and have in (None, "none"):
                continue
            if not (have == want_d or _same(have, want_d)):
                bad.append(f"{seat}: carried {have}, fixture {want_d}")
        res.set("carry_matches", not bad, "carry_mismatch", "; ".join(bad))
    # evidence
    need_items = facts.needed_items
    gone = sorted({m["name"] for m in ev.missing if m.get("name") in need_items})
    res.set("evidence_complete", not gone and not ev.tampered, "evidence_missing",
            "; ".join([f"missing {g}" for g in gone] + [f"changed after sealing: {t}" for t in ev.tampered]))
    return res
