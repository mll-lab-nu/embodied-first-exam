#!/usr/bin/env python3
"""Add the agent-trace log to a task's rcb_traj.py (idempotent). Every Session rollout (reset -> next reset / exit)
dumps its per-physics-step drive targets to RCB_AGENT_TRACE_DIR (default /app/output/rcb_trace/<pid>_<n>.npz), so the
verifier can reconstruct videos of what the agent tried. Self-reported: it lives in the agent's container.
usage: scripts/patch_rcb_traj_trace.py <rcb_traj.py> [...]"""
import sys, pathlib
MARK = "RCB_AGENT_TRACE_DIR"
for f in sys.argv[1:]:
    p = pathlib.Path(f); s = p.read_text()
    if MARK in s: print("already", f); continue
    def rep(old, new):
        global s
        assert s.count(old) == 1, (f, old[:70]); s = s.replace(old, new)
    rep('SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")\n',
        'SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")\n'
        '# Agent trace: every rollout (reset -> next reset / exit) of every Session dumps its per-step drive targets (float32,\n'
        '# same (T, 34) layout as a trajectory) to RCB_AGENT_TRACE_DIR/<pid>_<n>.npz; the verifier renders the last few as\n'
        '# videos of what the agent tried. Self-reported like the session log. RCB_AGENT_TRACE_DIR="" disables it.\n'
        'TRACE_DIR = os.environ.get("RCB_AGENT_TRACE_DIR", "/app/output/rcb_trace")\n'
        'TRACE_MAX_FILES = 300; TRACE_MAX_BYTES = 400 * 1024 * 1024\n')
    rep('        self._total_steps = 0\n        _slog("session_start"',
        '        self._total_steps = 0\n        self._trace: list | None = None; self._trace_kind = "rollout"; self._trace_t0 = time.time()\n        _slog("session_start"')
    rep('        atexit.register(lambda: _slog("session_end", task=task, resets=self._resets, sim_steps=self._total_steps + self._sim_steps))\n',
        '        atexit.register(lambda: _slog("session_end", task=task, resets=self._resets, sim_steps=self._total_steps + self._sim_steps))\n'
        '        atexit.register(self._trace_dump)\n')
    rep('        import sapien\n        self._recording = None\n',
        '        import sapien\n        self._trace_dump()\n        self._recording = None\n')
    rep('        self._sim_steps = 0\n        self._resets += 1\n',
        '        self._sim_steps = 0\n        self._resets += 1\n        self._trace = [] if TRACE_DIR else None; self._trace_t0 = time.time()\n')
    rep('        if self._recording is not None:\n            self._recording.append(self._current_row())\n',
        '        if self._recording is not None or self._trace is not None:\n            row = self._current_row()\n'
        '            if self._recording is not None: self._recording.append(row)\n'
        '            if self._trace is not None: self._trace.append(row.astype(np.float32))\n')
    rep('    def replay(self, actions: np.ndarray) -> dict[str, Any]:\n        self.reset()\n',
        '    def replay(self, actions: np.ndarray) -> dict[str, Any]:\n        self.reset(); self._trace_kind = "replay"\n')
    rep('        self.reset()\n        grab = lambda: self.render_grid(cameras, cols=cols, size=size)\n',
        '        self.reset(); self._trace_kind = "render"\n        grab = lambda: self.render_grid(cameras, cols=cols, size=size)\n')
    rep('    def close(self) -> None:\n',
        '    def _trace_dump(self) -> None:\n'
        '        """Write the current rollout\'s trace (if any) and start none; never raises."""\n'
        '        tr, kind = self._trace, self._trace_kind; self._trace = None; self._trace_kind = "rollout"\n'
        '        if not tr or not TRACE_DIR: return\n'
        '        try:\n'
        '            os.makedirs(TRACE_DIR, exist_ok=True)\n'
        '            ents = [e for e in os.scandir(TRACE_DIR) if e.name.endswith(".npz")]\n'
        '            if len(ents) >= TRACE_MAX_FILES or sum(e.stat().st_size for e in ents) >= TRACE_MAX_BYTES:\n'
        '                _slog("trace_dropped", task=self.task, n_steps=len(tr)); return\n'
        '            try: ok = bool(self.env.check_success())\n'
        '            except Exception: ok = False  # noqa: BLE001 — e.g. at interpreter exit\n'
        '            path = os.path.join(TRACE_DIR, f"{os.getpid()}_{self._resets:05d}.npz")\n'
        '            np.savez_compressed(path, actions=np.stack(tr), task=self.task, seed=self.seed, instance_sha=self.expected_sha or "",\n'
        '                                kind=kind, t_start=self._trace_t0, t_end=time.time(), success=ok)\n'
        '        except Exception:  # noqa: BLE001 — tracing must never break the agent\'s run\n'
        '            pass\n\n'
        '    def close(self) -> None:\n'
        '        self._trace_dump()\n')
    p.write_text(s); print("patched", f)
