#!/usr/bin/env python3
"""account_failure_check.py <trial dir> [...] | --selftest: did a finished trial hit a model-account or config failure (out of
credits, rate-limited, logged out, a missing key), so that every further job of the lane would fail within minutes?
run_agent_batch.sh stops the lane on exit 4 (a runner-side tool, not task code).

Structured evidence only, from what Harbor's native agents write (2026-09-28: a grep of codex.txt once stopped a lane on
Codex's "Reconnecting... 1/5" notice after a transient server error, whose request ID happened to contain "429", in a trial
whose model calls had all answered 200 and that ended at its time budget):
  quota    Codex's own rate_limits (payload.rate_limits in the last session rollout, parsed): rate_limit_reached_type set,
           or a window at >= 100 % used;
  codex    the LAST root-level Codex event of <trial>/agent/codex.txt (the parsed object's own "type"; a failure Codex
           recovered from is followed by other events) is turn.failed / error and its message names 401 / 402 / 429 /
           usage limit / Too Many Requests / Missing environment variable;
  claude   the LAST root-level event of <trial>/agent/claude-code.txt is Claude Code's result with is_error set and a text
           that names the same failures (or an invalid key, a low credit balance, a needed login).
Prints one JSON line per trial {"trial", "stop", "why"} (long tokens in messages masked); exit 4 if any trial should stop
its lane, 0 otherwise. --selftest checks the rules on synthetic trials (exit 0 = all as expected)."""
import glob, json, os, re, sys, tempfile

PAT = re.compile(r"\b(401|402|429)\b|usage limit|Too Many Requests|Missing environment variable|Payment Required|Unauthorized|"
                 r"invalid api key|credit balance|please run /login|authentication_error|rate_limit_error", re.I)


def mask(s: str) -> str:
    return re.sub(r"[A-Za-z0-9_\-+/=.]{24,}", "<masked>", s)[:200]


def check(t: str) -> dict:
    why = []
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
    for f in glob.glob(os.path.join(t, "agent", "claude-code.txt")):
        last = None
        for line in open(f, errors="replace"):
            if line.startswith("{"):
                try:
                    last = json.loads(line)
                except ValueError:
                    continue
        if isinstance(last, dict) and last.get("type") == "result" and last.get("is_error"):
            msg = str(last.get("result") or last.get("subtype") or "")
            if PAT.search(msg):
                why.append(f"claude: result: {mask(msg)}")
    return {"trial": os.path.basename(t.rstrip("/")), "stop": bool(why), "why": why}


def selftest() -> int:
    def trial(root, name, rate_limits=None, codex=(), claude=None):
        t = os.path.join(root, name)
        os.makedirs(os.path.join(t, "agent", "sessions", "2026", "09", "28"))
        if claude is not None:
            with open(os.path.join(t, "agent", "claude-code.txt"), "w") as f:
                f.writelines(json.dumps(e) + "\n" for e in claude)
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
        "rate_limit_reached_type": (dict(rate_limits={**ok_rl, "rate_limit_reached_type": "primary"}, codex=done), True),
        "window_100_percent": (dict(rate_limits={"primary": {"used_percent": 100.0}}, codex=done), True),
        "codex_turn_failed_usage_limit": (dict(rate_limits=ok_rl, codex=[{"type": "turn.failed", "error": {
            "message": "You've hit your usage limit. Upgrade to Pro or try again later."}}]), True),
        "codex_error_missing_env": (dict(rate_limits=None, codex=[{"type": "error", "message":
            "Missing environment variable: `OPENAI_API_KEY`."}]), True),
        "codex_error_401": (dict(rate_limits=None, codex=[{"type": "turn.failed", "error": {"message": "unexpected status 401 Unauthorized"}}]), True),
        "false_positive_2026_09_28": (dict(rate_limits=ok_rl, codex=fp), False),
        "recovered_429": (dict(rate_limits=ok_rl, codex=[
            {"type": "error", "message": "stream error: 429 Too Many Requests; retrying"}, {"type": "item.completed"}] + done), False),
        "backend_400": (dict(rate_limits=ok_rl, codex=[{"type": "turn.failed", "error": {
            "message": "prompt_cache_retention is not supported on this model"}}]), False),
        "timeout": (dict(rate_limits=ok_rl, codex=[{"type": "item.started"}]), False),
        "claude_invalid_key": (dict(claude=[{"type": "system"}, {"type": "result", "subtype": "success", "is_error": True,
                                                                  "result": "Invalid API key · Please run /login"}]), True),
        "claude_credit": (dict(claude=[{"type": "result", "is_error": True, "result": "Credit balance is too low"}]), True),
        "claude_ok": (dict(claude=[{"type": "assistant"}, {"type": "result", "subtype": "success", "is_error": False, "result": "done"}]), False),
        "claude_tool_429_then_ok": (dict(claude=[{"type": "user", "message": "HTTP 429 from a tool"}, {"type": "result", "is_error": False,
                                                                                                         "result": "finished"}]), False),
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
