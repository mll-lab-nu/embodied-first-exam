"""The agent-facing client. `connect()` talks to the robot service over HTTP; `local(episode)` wraps an episode in
the same process (tests, admission). Both expose `call(tool, **args)` and one method per tool.

The HTTP part is `remote.py`. An agent's container gets that file and `__main__.py` and nothing else of this
repository, under the package name `robot_client` (`docker/agent.Dockerfile`), so that no name an agent can read
says what it is being run for."""
from __future__ import annotations

from .remote import Robot, _Remote, connect

AGENT_PACKAGE = "robot_client"          # what the client is called inside an agent's container


class _Local(Robot):
    def __init__(self, episode, think=None):
        self._ep = episode
        self._think = think
        self._n = 0
        self.last_clock = None              # the `clock` entry of the last call (realtime): what a driver's mirror replays

    def call(self, tool: str, **args) -> dict:
        think = None
        if self._think is not None and self._n > 0:     # a synthetic think-time schedule (realtime): seconds before this
            # call; none before the first, as the service's clock starts with the first request
            t = self._think
            think = float(t(self._n) if callable(t) else t[self._n % len(t)] if isinstance(t, (list, tuple)) else t)
        self._n += 1
        out = self._ep.execute({"tool": tool, "args": args}, think_s=think)
        self.last_clock = self._ep.calls[-1].get("clock") if self._ep.calls else None
        return out

    def _write_array(self, path, img) -> None:
        from ..sim.png import depth_png, write_png
        if getattr(img, "dtype", None) is not None and img.dtype.kind == "f":      # a depth image (metres)
            from pathlib import Path
            Path(path).write_bytes(depth_png(img))
            return
        write_png(path, img)


def local(episode, think=None) -> Robot:
    """`think` (realtime clock only): the agent's time before each call, in seconds: a number (every call), a list
    (cycled) or a callable(call index) -> seconds. Ignored by a paused episode."""
    return _Local(episode, think)
