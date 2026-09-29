#!/usr/bin/env python3
"""account_failure_check.py <trial dir> [...] | --selftest: did a finished trial hit a model-account or config failure (out of
credits, rate-limited, logged out, a missing key), so that every further job of the lane would fail within minutes?
run_agent_batch.sh stops the lane on exit 4.

Structured evidence only (2026-09-28: the former grep of codex.txt stopped a lane of the RoboPaint sweep on Codex's
"Reconnecting... 1/5" notice after a transient server error, whose request ID happened to contain "429", in a trial whose 309
model calls had all answered 200 and that ended at its time budget):
  gateway  the model gateway's own record (<trial>/agent/gateway.jsonl): the last call answered 401 / 402 / 429, or 3 of the
           last 5 did;
  quota    Codex's own rate_limits (payload.rate_limits in the last session rollout, parsed): rate_limit_reached_type set,
           or a window at >= 100 % used;
  codex    the LAST root-level Codex event of <trial>/agent/codex.txt (the parsed object's own "type"; a failure Codex
           recovered from is followed by other events) is turn.failed / error and its message names 401 / 402 / 429 /
           usage limit / Too Many Requests / Missing environment variable.
Prints one JSON line per trial {"trial", "stop", "why"} (long tokens in messages masked); exit 4 if any trial should stop
its lane, 0 otherwise. --selftest checks the rules on synthetic trials (exit 0 = all as expected)."""
import glob, json, os, re, sys, tempfile

PAT = re.compile(r"\b(401|402|429)\b|usage limit|Too Many Requests|Missing environment variable|Payment Required|Unauthorized",
                 re.I)
BAD = {401, 402, 429}


def mask(s: str) -> str:
    return re.sub(r"[A-Za-z0-9_\-+/=.]{24,}", "<masked>", s)[:200]


def check(t: str) -> dict:
    why = []
    st = []
    for f in glob.glob(os.path.join(t, "agent", "gateway.jsonl")):
        for line in open(f, errors="replace"):
            try:
                st.append(int(json.loads(line).get("status")))
            except (ValueError, TypeError, AttributeError):
                continue
    if st and (st[-1] in BAD or sum(s in BAD for s in st[-5:]) >= 3):
        why.append(f"gateway: last statuses {st[-5:]}")
    for f in sorted(glob.glob(os.path.join(t, "agent", "sessions", "**", "rollout-*.jsonl"), recursive=True),
                    key=os.path.getmtime)[-1:]:
        last = None
        for line in open(f, errors="replace"):
            if '"rate_limits"' not in line:
                continue
            try:
                rl = (json.loads(line).get("payload") or {}).get("rate_limits")
            except (ValueError, AttributeError):
                continue
            if isinstance(rl, dict):
                last = rl
        if last:
            used = [float((last.get(w) or {}).get("used_percent") or 0) for w in ("primary", "secondary")]
            if last.get("rate_limit_reached_type") or max(used) >= 100:
                why.append(f"quota: rate_limit_reached_type={last.get('rate_limit_reached_type')} used_percent={used}")
    for f in glob.glob(os.path.join(t, "agent", "codex.txt")):
        last = None
        for line in open(f, errors="replace"):
            if line.startswith("{"):
                try:
                    last = json.loads(line)
                except ValueError:
                    continue
        if isinstance(last, dict) and last.get("type") in ("turn.failed", "error"):
            err = last.get("error")
            msg = str(err.get("message") if isinstance(err, dict) else last.get("message") or "")
            if PAT.search(msg):
                why.append(f"codex: {last['type']}: {mask(msg)}")
    return {"trial": os.path.basename(t.rstrip("/")), "stop": bool(why), "why": why}


def selftest() -> int:
    def trial(root, name, gateway=(), rate_limits=None, codex=()):
        t = os.path.join(root, name)
        os.makedirs(os.path.join(t, "agent", "sessions", "2026", "09", "28"))
        with open(os.path.join(t, "agent", "gateway.jsonl"), "w") as f:
            f.writelines(json.dumps({"i": i, "status": s}) + "\n" for i, s in enumerate(gateway))
        if rate_limits is not None:
            with open(os.path.join(t, "agent", "sessions", "2026", "09", "28", "rollout-x.jsonl"), "w") as f:
                f.write(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "rate_limits": rate_limits}}) + "\n")
        with open(os.path.join(t, "agent", "codex.txt"), "w") as f:
            f.write("WARNING: a plain text line\n")
            f.writelines(json.dumps(e) + "\n" for e in codex)
        return t

    ok_rl = {"primary": {"used_percent": 19.0, "window_minutes": 10080}, "secondary": None}
    done = [{"type": "turn.completed"}]
    # the false positive of 2026-09-28: Codex's reconnect notice after a transient 500, its request ID containing "429",
    # then the run went on (every other call 200); and "429" / usage limit inside a tool result
    fp = [{"type": "error", "message": "Reconnecting... 1/5 (The server had an error while processing your request. Please "
           "include the request ID 7c1e0429f3ab in your message.)"}, {"type": "item.completed", "item": {
           "type": "command_execution", "aggregated_output": 'x = 429 ... {"type":"error","code":429} usage limit'}}] + done
    cases = {  # name: (kwargs, expected stop)
        "gateway_401": (dict(gateway=[200] * 9 + [401], rate_limits=ok_rl, codex=done), True),
        "gateway_402": (dict(gateway=[200, 402], rate_limits=ok_rl, codex=done), True),
        "gateway_429_last": (dict(gateway=[200, 200, 429], rate_limits=ok_rl, codex=done), True),
        "gateway_429_3_of_5": (dict(gateway=[200, 429, 429, 200, 429, 200], rate_limits=ok_rl, codex=done), True),
        "rate_limit_reached_type": (dict(gateway=[200], rate_limits={**ok_rl, "rate_limit_reached_type": "primary"},
                                         codex=done), True),
        "window_100_percent": (dict(gateway=[200], rate_limits={"primary": {"used_percent": 100.0}}, codex=done), True),
        "codex_turn_failed_usage_limit": (dict(gateway=[200], rate_limits=ok_rl, codex=[{"type": "turn.failed", "error": {
            "message": "You've hit your usage limit. Upgrade to Pro or try again later."}}]), True),
        "codex_error_missing_env": (dict(gateway=[], rate_limits=None, codex=[{"type": "error", "message":
            "Missing environment variable: `OPENAI_API_KEY`."}]), True),
        "false_positive_2026_09_28": (dict(gateway=[200] * 150 + [500] + [200] * 158, rate_limits=ok_rl, codex=fp), False),
        "recovered_429": (dict(gateway=[200, 429, 200, 200, 200], rate_limits=ok_rl, codex=[
            {"type": "error", "message": "stream error: 429 Too Many Requests; retrying"}, {"type": "item.completed"}] + done),
            False),
        "backend_400": (dict(gateway=[200, 400], rate_limits=ok_rl, codex=[{"type": "turn.failed", "error": {
            "message": "prompt_cache_retention is not supported on this model"}}]), False),
        "timeout_all_200": (dict(gateway=[200] * 50, rate_limits=ok_rl, codex=[{"type": "item.started"}]), False),
    }
    bad = 0
    with tempfile.TemporaryDirectory() as root:
        for name, (kw, want) in cases.items():
            r = check(trial(root, name, **kw))
            bad += r["stop"] != want
            print(f"{'ok  ' if r['stop'] == want else 'FAIL'} {name}: stop={r['stop']} (want {want}) {r['why']}")
        r = check(os.path.join(root, "no_such_trial"))
        bad += r["stop"]
        print(f"{'ok  ' if not r['stop'] else 'FAIL'} missing trial dir: stop={r['stop']} (want False)")
    print(f"selftest: {len(cases) + 1 - bad} / {len(cases) + 1} as expected")
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    rows = [check(t) for t in sys.argv[1:]]
    for r in rows:
        print(json.dumps(r))
    sys.exit(4 if any(r["stop"] for r in rows) else 0)
