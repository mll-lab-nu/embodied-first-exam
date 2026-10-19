#!/usr/bin/env python3
"""L0: snapshot the eval pool into $XB_DATA (default data/) and diff against the previous snapshot.

usage: BEL_TOKEN=... tools/index.py [--jobs 8]

Sources: api/pool (one job per catalog task x run; a rerun replaces the cell's job in place, no history), api/tasks
(catalog, luna_filter), api/monitor (per-trial fields for the trials it lists; since 10-17 it may list only live ones).
Trials are matched across id formats by trial name (text after the last "/"). For a trial not seen before, api/trial
detail and result.json are fetched once into $XB_INDEX_CACHE/<trial name>.json (with the monitor record, if any);
a trial kept from the previous trials.csv only needs result.json (task_checksum).

cells.csv       one row per catalog task x run in common.AGENTS (status, current trial, review state, version).
trials.csv      the current trial of each finished cell; rows of trials seen before are kept as they were.
superseded.csv  trial keys that are no longer current (cumulative), with the replacing trial key or outside-pool.
tasks.csv       catalog metadata + versions (distinct task_checksum among the task's current trials).
changes.json    added / changed / gone / replaced vs the previous snapshot; also under snapshots/<stamp>/.
"""
from __future__ import annotations
import argparse, csv, glob, gzip, hashlib, io, json, os, sys, time, urllib.error
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import bel
from common import AGENTS, DATA, HERE, LUNA, read_csv, trial_key, write_csv

CACHE = os.environ.get("XB_INDEX_CACHE", "/data/pingyue/cross-bench/index-cache")
ACTIVE = {"queued", "running", "launching", "setup", "assigned", "claimed", "verifying"}
FINISHED = {"success", "failed"}
INFRA_EXC = {"NetworkConnectionError", "ApiOverloadedError", "ApiRateLimitError", "VerifierTimeoutError", "ApiUsageLimitError"}
BUDGET_EXC = ("TokenBudgetExceeded", "OutputTokenExceededError")       # valid failures, listed in the summary
DONE = {"valid": "done-valid", "infra": "done-rerun", "rule": "done-excluded", "suspect": "done-excluded"}


def name(trial_id: str | None) -> str:
    return (trial_id or "").rsplit("/", 1)[-1]


# ---------- validity (one trial record in the monitor's shape) ----------

def flag(t: dict, k: str):
    v = (t.get("flags") or {}).get(k)
    return v if v not in (None, "", "None") else None


def validity(t: dict) -> tuple[str, str]:
    """(class, reason): valid / infra / rule / suspect. Rule and suspect trials are listed, not scored."""
    exc = t.get("exception") or ""
    if exc in INFRA_EXC or flag(t, "infra_error") == 1 or flag(t, "grader_error") == 1:
        return "infra", exc or ("infra_error" if flag(t, "infra_error") == 1 else "grader_error")
    if (t.get("usage_limit") or 0) > 0 and (t.get("api_fatal") or exc == "NonZeroAgentExitCodeError"):
        return "infra", "usage_limit"
    if t.get("api_fatal") or t.get("transport_cut") or t.get("gw_refused"):
        return "infra", "api_fatal" if t.get("api_fatal") else "transport_cut" if t.get("transport_cut") else "gateway_refused"
    if t.get("reward") is None:
        return "infra", "no_reward"
    if flag(t, "limits_violation_observed") == 1 or flag(t, "external_tool_calls") or flag(t, "answer_packages"):
        return "rule", ",".join(k for k in ("limits_violation_observed", "external_tool_calls", "answer_packages") if flag(t, k))
    if flag(t, "end_reason") == "success" and t["state"] != "success":
        return "suspect", "episode_success_but_failed"
    return "valid", ""


def upgrade(row: dict, rec: dict | None) -> bool:
    """Rules added after a kept row was written (usage-limit exits are infra). True when the row changed."""
    if row["validity"] != "valid":
        return False
    v, why = validity(rec) if rec else (("infra", row["exception"]) if row["exception"] in INFRA_EXC else ("valid", ""))
    if v == "infra" and (why in INFRA_EXC or why == "usage_limit"):
        row["validity"], row["validity_reason"] = v, why
        return True
    return False


# ---------- per-trial cache ----------

def cache_path(trial: str) -> str:
    return os.path.join(CACHE, trial + ".json")


def cached(trial: str) -> dict:
    try:
        return json.load(open(cache_path(trial)))
    except (OSError, ValueError):
        return {}


def save(trial: str, c: dict) -> None:
    os.makedirs(CACHE, exist_ok=True)
    p = cache_path(trial)
    json.dump(c, open(p + ".part", "w"))
    os.replace(p + ".part", p)


def fill(job: dict, rec: dict | None, need_detail: bool) -> str:
    """Fetch what the cache lacks for this job's trial: result.json always, api/trial detail when `need_detail`.
    The monitor record is stored too when the monitor lists the trial (no extra request)."""
    trial, tid = name(job["trial_id"]), job["trial_id"]
    c = cached(trial)
    todo = [k for k in ("result",) + (("detail",) if need_detail else ()) if k not in c]
    if not todo and (rec is None or "monitor" in c):
        return "cached"
    if rec is not None:
        c["monitor"] = rec
    try:
        if "result" in todo:
            c["result"] = json.loads(bel.get_file(tid, "result.json"))
        if "detail" in todo:
            c["detail"] = bel.get_json("api/trial", id=tid)
        out = "fetched " + "+".join(todo) if todo else "monitor record"
    except (urllib.error.URLError, ValueError, OSError) as e:
        out = f"error {getattr(e, 'code', type(e).__name__)}"   # not cached: the next run retries
    if c:
        save(trial, {**c, "trial_id": tid, "time": c.get("time") or time.strftime("%Y-%m-%d %H:%M")})
    return out


def _ts(s: str | None):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None
    except ValueError:
        return None


def record(job: dict, c: dict) -> tuple[dict, str]:
    """The trial in the monitor's shape: the monitor record if one was seen, else built from detail + result.json + job.
    Not recoverable without the monitor: end_reason, gave_up, external_tool_calls, answer_packages, api_fatal,
    usage_limit, transport_cut, live_success (gateway refusals only as a count of refused hosts)."""
    if c.get("monitor"):
        return c["monitor"], "monitor"
    d, r = c.get("detail") or {}, c.get("result") or {}
    rw = d.get("reward") if isinstance(d.get("reward"), dict) else {}
    ae, ar, gw = r.get("agent_execution") or {}, r.get("agent_result") or {}, d.get("gateway") or {}
    return ({"id": job["trial_id"], "state": job["state"], "reward": job.get("reward"),
             "exception": job.get("exception") or (r.get("exception_info") or {}).get("exception_type") or "",
             "flags": {k: rw[k] for k in ("infra_error", "grader_error", "limits_violation_observed") if k in rw},
             "gw_refused": {"refused_hosts": gw["refused_hosts"]} if gw.get("refused_hosts") else None,
             "agent_start": job.get("agent_start") or _ts(ae.get("started_at")),
             "agent_end": job.get("agent_end") or _ts(ae.get("finished_at")),
             "finished": _ts(r.get("finished_at")) or job.get("updated"), "timeout": job.get("timeout"),
             "tok_in": ar.get("n_input_tokens") or job.get("tok_in"), "tok_out": ar.get("n_output_tokens"),
             "requests": gw.get("requests")}, "detail" if d else "pool")


def fingerprint(t: dict) -> str:
    s = json.dumps([name(t["id"]), t.get("finished"), t.get("agent_end"), t.get("reward"), t["state"]])
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def trial_row(t: dict, meta: dict) -> dict:
    v, why = validity(t)
    m = meta.get(t["task"], {})
    a0, a1 = t.get("agent_start"), t.get("agent_end")
    return {
        "key": trial_key({"run": t["run"], "trial": name(t["id"])}), "id": t["id"], "run": t["run"],
        "agent": AGENTS.get(t["run"], t["run"]), "bench": t["bench"], "task": t["task"],
        "base": m.get("base", t["task"].rsplit("-", 1)[0]), "family": m.get("family", ""), "mode": t["mode"],
        "state": t["state"], "success": int(t["state"] == "success"), "validity": v, "validity_reason": why,
        "end_reason": flag(t, "end_reason") or "", "exception": t.get("exception") or "",
        "gave_up": flag(t, "gave_up") or 0, "timeout_min": round((t.get("timeout") or 0) / 60),
        "agent_min": round((a1 - a0) / 60, 1) if a0 and a1 else "",
        "tok_in": t.get("tok_in") or 0, "tok_out": t.get("tok_out") or 0, "requests": t.get("requests") or 0,
        "in_catalog": int(t["task"] in meta), "finished": t.get("finished") or t.get("agent_end") or "",
        "fingerprint": fingerprint(t),
    }


# ---------- snapshots ----------

def gz_csv(path: str) -> list[dict]:
    return list(csv.DictReader(io.TextIOWrapper(gzip.open(path), newline=""))) if os.path.exists(path) else []


def snapshot(stamp: str, files: dict, changes: dict) -> str:
    d = os.path.join(DATA, "snapshots", stamp)
    os.makedirs(d, exist_ok=True)
    for fn, rows in files.items():
        with gzip.open(os.path.join(d, fn + ".gz"), "wt", newline="") as f:
            w = csv.DictWriter(f, list(rows[0]) if rows else [])
            w.writeheader()
            w.writerows(rows)
    json.dump(changes, open(os.path.join(d, "changes.json"), "w"), indent=1)
    return d


def previous() -> list[dict]:
    snaps = sorted(glob.glob(os.path.join(DATA, "snapshots", "*", "trials.csv.gz")))
    return gz_csv(snaps[-1]) if snaps else read_csv("trials.csv")


def reviewed_keys() -> set:
    """Trials with a review (data reviews.csv) or selected for one (ledger.csv, depth skim/deep)."""
    led = os.path.join(HERE, "ledger.csv")
    keys = {r["key"] for r in read_csv("reviews.csv")}
    if os.path.exists(led):
        keys |= {r["key"] for r in csv.DictReader(open(led)) if r["depth"] in ("skim", "deep")}
    return keys


# ---------- main ----------

def renamer(rename: dict, meta: dict):
    """Old task name -> catalog name. Pairs seen on kept trials, plus their prefix rule (e.g. cell- -> rsb-) for tasks
    whose every trial was rerun."""
    def prefix(a, b):
        i = 0
        while i < min(len(a), len(b)) and a[-1 - i] == b[-1 - i]:
            i += 1
        return a[:len(a) - i], b[:len(b) - i]
    rules = {prefix(a, b) for a, b in rename.items()}

    def retask(t: str) -> str:
        if t in meta or t in rename:
            return rename.get(t, t)
        return next((b + t[len(a):] for a, b in sorted(rules) if t.startswith(a) and b + t[len(a):] in meta), t)
    return retask


def cell_status(j: dict | None, k: str, row: dict | None, task: str, run: str, luna_filter: dict) -> tuple[str, str]:
    st = (j or {}).get("state")
    if k:
        return DONE[row["validity"]], row["validity_reason"]
    if st in FINISHED:
        return "done-excluded", "no_trial"            # a result recorded without a trial (imported from elsewhere)
    if st == "held":
        return "held", ""
    if st == "infra_failed":
        return "infra-failed", ""
    if st:
        return "in-progress", "" if st in ACTIVE else st
    if run != LUNA and luna_filter.get(task) == "filtered":
        return "skipped", ""
    return "not-scheduled", ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=8, help="parallel requests (at most 8)")
    a = ap.parse_args()
    pool, cat = bel.get_json("api/pool"), bel.get_json("api/tasks")
    try:
        mon = {name(t["id"]): t for t in bel.get_json("api/monitor")["trials"] if t.get("id") and t.get("state") in FINISHED}
    except (urllib.error.URLError, ValueError, OSError) as e:
        print("api/monitor unavailable:", e)
        mon = {}
    meta = {t["task"]: t for t in cat["tasks"]}
    jobs = {}
    for j in sorted(pool["jobs"], key=lambda j: j["id"]):      # one job per cell; the latest id wins if ever two
        if j["run_id"] in AGENTS:
            jobs[(j["task"], j["run_id"])] = j

    stamp = time.strftime("%Y%m%d-%H%M")
    pv = {r["key"]: r["fingerprint"] for r in previous()}
    old = {r["key"]: r for r in read_csv("trials.csv")}
    done = [j for j in jobs.values() if j["state"] in FINISHED and j.get("trial_id")]
    keyof = lambda j: trial_key({"run": j["run_id"], "trial": name(j["trial_id"])})
    keep = {keyof(j) for j in done if keyof(j) in old and old[keyof(j)]["state"] == j["state"]
            and old[keyof(j)].get("fields_from") != "pool"}             # pool-only rows are rebuilt once more is known
    with ThreadPoolExecutor(min(a.jobs, 8)) as ex:
        fetch = Counter(ex.map(lambda j: fill(j, mon.get(name(j["trial_id"])), keyof(j) not in keep), done))

    rows, srcs, upgraded, rename = [], Counter(), 0, {}
    for j in done:
        k, c = keyof(j), cached(name(j["trial_id"]))
        if k in keep:                                # identity follows the pool (tasks were renamed, e.g. cell-* -> rsb-*)
            m = meta.get(j["task"], {})
            row, src = dict(old[k]), old[k].get("fields_from") or "monitor"
            if row["task"] != j["task"]:
                rename[row["task"]] = j["task"]
            row.update(task=j["task"], bench=j["bench"], mode=j["mode"], base=m.get("base", row["base"]),
                       family=m.get("family", row["family"]), in_catalog=int(j["task"] in meta))
            upgraded += upgrade(row, c.get("monitor"))
        else:
            rec, src = record(j, c)
            row = trial_row({**rec, "run": j["run_id"], "task": j["task"], "bench": j["bench"], "mode": j["mode"]}, meta)
        srcs["kept" if k in keep else src] += 1
        rows.append({**row, "trial_id": j["trial_id"], "task_checksum": (c.get("result") or {}).get("task_checksum") or "",
                     "job_tag": j.get("tag") or "", "attempts": j.get("attempts") or "", "fields_from": src})
    rows.sort(key=lambda r: (r["bench"], r["task"], r["run"], str(r["finished"])))
    by_key = {r["key"]: r for r in rows}
    cur = {(r["task"], r["run"]): r["key"] for r in rows}

    # task versions: distinct checksums among current trials; the most common (ties: the most recent) is the main one
    vers, last = defaultdict(Counter), {}
    for r in rows:
        if r["task_checksum"]:
            vers[r["task"]][r["task_checksum"]] += 1
            last[(r["task"], r["task_checksum"])] = max(last.get((r["task"], r["task_checksum"]), 0), float(r["finished"] or 0))
    main_ck = {t: max(c, key=lambda ck: (c[ck], last[(t, ck)])) for t, c in vers.items()}

    # superseded (cumulative): previous rows and earlier superseded keys that are no longer current
    sup_old = {r["key"]: r for r in read_csv("superseded.csv")}
    retask = renamer(rename, meta)
    cand = {**{k: {"task": retask(r["task"]), "run": r["run"], "since": stamp} for k, r in old.items()},
            **{k: {"task": retask(r["task"]), "run": r["run"], "since": r["since"]} for k, r in sup_old.items()}}
    sup = {}
    for k, r in sorted(cand.items()):
        if k not in by_key:
            j = jobs.get((r["task"], r["run"]))
            rep = cur.get((r["task"], r["run"])) or ("outside-pool" if j is None or r["task"] not in meta else "")
            sup[k] = {"key": k, "task": r["task"], "run": r["run"], "agent": AGENTS.get(r["run"], r["run"]),
                      "replaced_by": rep, "job_state": j["state"] if j else "", "since": r["since"]}
    cell_of = {k: (r["task"], r["run"]) for k, r in {**cand, **by_key}.items()}

    # reviews: a reviewed trial is current, replaced (its cell has a newer trial or a pending rerun) or outside the pool
    rev_state = {k: "current" if k in by_key else "unknown" if k not in cell_of else
                 "outside-pool" if cell_of[k] not in jobs or cell_of[k][0] not in meta else "replaced"
                 for k in reviewed_keys()}
    rev_cells = defaultdict(set)
    for k, s in rev_state.items():
        if k in cell_of:
            rev_cells[cell_of[k]].add(s)

    cells = []
    for task, m in sorted(meta.items()):
        for run in sorted(AGENTS):
            j, k = jobs.get((task, run)), cur.get((task, run), "")
            status, reason = cell_status(j, k, by_key.get(k), task, run, cat["luna_filter"])
            ck, rs = (by_key[k]["task_checksum"] if k else ""), rev_cells.get((task, run), set())
            cells.append({"task": task, "bench": m["bench"], "base": m["base"], "mode": m["mode"], "run": run,
                          "agent": AGENTS[run], "status": status, "reason": reason, "trial": k,
                          "trial_id": (j or {}).get("trial_id") or "", "job_id": (j or {}).get("id", ""),
                          "job_state": (j or {}).get("state", ""), "job_tag": (j or {}).get("tag") or "",
                          "attempts": (j or {}).get("attempts") or "", "finished": by_key[k]["finished"] if k else "",
                          "task_checksum": ck, "version_same": int(ck == main_ck.get(task)) if ck else "",
                          "review": next((s for s in ("current", "replaced", "outside-pool") if s in rs), "none")})
    tasks = [{"task": t["task"], "base": t["base"], "bench": t["bench"], "mode": t["mode"], "family": t.get("family") or "",
              "robot": t.get("robot") or "", "simulator": t.get("simulator") or "", "timeout_min": round((t.get("timeout") or 0) / 60),
              "protocol": t.get("protocol") or "", "luna_filter": cat["luna_filter"].get(t["task"], ""),
              "versions": len(vers.get(t["task"], ())), "checksum": main_ck.get(t["task"], "")}
             for t in sorted(cat["tasks"], key=lambda t: t["task"])]

    now = {r["key"]: r["fingerprint"] for r in rows}
    replaced = sorted([k, sup[k]["replaced_by"]] for k in set(pv) - set(now)
                      if k in sup and sup[k]["replaced_by"] not in ("", "outside-pool"))
    changes = {"time": time.strftime("%Y-%m-%d %H:%M"), "added": sorted(set(now) - set(pv)),
               "changed": sorted(k for k in set(now) & set(pv) if now[k] != pv[k]),
               "gone": sorted(set(pv) - set(now) - {o for o, _ in replaced}), "replaced": replaced}

    write_csv("trials.csv", rows)
    write_csv("cells.csv", cells)
    write_csv("tasks.csv", tasks)
    write_csv("superseded.csv", list(sup.values()))
    json.dump(changes, open(os.path.join(DATA, "changes.json"), "w"), indent=1)
    snap = snapshot(stamp, {"cells.csv": cells, "trials.csv": rows}, changes)

    print(f"{len(rows)} current trials ({dict(Counter(r['validity'] for r in rows))}); rows: {dict(srcs)}; "
          f"{upgraded} kept rows re-classed infra (usage limit); {len(rename)} renamed tasks followed")
    print(f"requests: {dict(fetch)}; monitor listed {len(mon)} finished trials")
    print(f'changes: {len(changes["added"])} added, {len(changes["changed"])} changed, {len(changes["gone"])} gone, '
          f'{len(changes["replaced"])} replaced; snapshot {snap}')
    print("cells:", dict(Counter(c["status"] for c in cells)))
    print("reviewed trials:", dict(Counter(rev_state.values())), "| cells:", dict(Counter(c["review"] for c in cells)))
    print("superseded:", len(sup), dict(Counter("outside-pool" if s["replaced_by"] == "outside-pool" else
                                               "pending" if not s["replaced_by"] else "replaced" for s in sup.values())))
    print("token-limit failures (kept valid):", dict(Counter((r["agent"], r["exception"]) for r in rows if r["exception"] in BUDGET_EXC)))
    print("tasks with more than one version:", sum(t["versions"] > 1 for t in tasks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
