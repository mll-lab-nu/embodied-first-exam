"""The reference player's live control loop (builtin_players.OpenReference): a thread with its own connection to the
match that runs the striker at 50 Hz of game time (wait / act calls: the state of each reply, one joints act every
2 control steps) while the player's main loop observes the camera images and decides. Live only (a wall clock); the
seat's client library (ro_client = core/client.py) or plain urllib."""
from __future__ import annotations

import os
import sys
import threading


class ControlLoop:
    def __init__(self, player, every_steps: int = 2):
        self.player, self.every = player, int(every_steps)
        self.thread = None
        self.stop = False
        self.lock = threading.Lock()
        self.pending = None                # an act to send before the next joints act (the service's toss)

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def send(self, body):
        with self.lock:
            self.pending = body

    def _client(self):
        sys.path.insert(0, os.getcwd())
        try:
            import ro_client as client
        except ImportError:
            from core import client
        cf = client.settings()
        return client.Seat(cf["sim_url"], cf["seat"])

    def _run(self):
        c = self._client()
        P = self.player
        last_k = None
        while not self.stop:
            now = c.call("wait", {"dt": 0.01}).get("now") or {}
            if now.get("done"):
                return
            if now.get("world") != "running" or now.get("step") is None:
                continue
            P.now = now
            k = int(now["step"])
            with self.lock:
                body, self.pending = self.pending, None
            if body is not None:
                r = c.call("act", body)
                P.sent["toss"] += 1
                if r.get("now"):
                    P.now = r["now"]
                continue
            if last_k is not None and k - last_k < self.every:
                continue
            body = P._joints(now)
            if body is None:
                continue
            r = c.call("act", body)
            P.sent["joints"] += 1
            if r.get("error") or r.get("http_status"):
                P.sent["refused"] += 1
            last_k = k
