"""Policy clients; both expose .spec, .reset(seed), .infer(obs) and .close()."""
from __future__ import annotations

from multiprocessing.connection import Client

from vla.protocol import ActionChunk, PolicySpec, decode, encode


class PolicyError(RuntimeError):
    """The policy failed, returned a malformed chunk or disconnected; not a task failure."""


class RemoteClient:
    """One connection to ``python -m vla.models.serve`` at "host:port"; the server sends its PolicySpec first.

    Replies are awaited without a time limit: a server that dies closes the connection (PolicyError at once), and
    a server busy with another client answers once that client disconnects."""

    def __init__(self, address):
        host, port = address.rsplit(":", 1)
        self.conn = Client((host, int(port)))
        msg = self._receive()
        msg.pop("type")
        self.spec = PolicySpec(**msg)  # raises ValueError on a protocol version mismatch

    def reset(self, seed):
        self._request({"type": "reset", "seed": seed}, "ok")

    def infer(self, obs):
        return ActionChunk(self._request({"type": "infer", **vars(obs)}, "chunk")["actions"])

    def close(self):
        self.conn.close()

    def _request(self, msg, expected):
        try:
            self.conn.send_bytes(encode(msg))
        except OSError as error:
            raise PolicyError(f"Model server connection lost: {error}") from error
        reply = self._receive()
        if reply["type"] != expected:
            raise PolicyError(reply.get("message", f"Expected a {expected} reply, got {reply['type']}"))
        return reply

    def _receive(self):
        try:
            return decode(self.conn.recv_bytes())
        except (EOFError, OSError) as error:
            raise PolicyError(f"Model server connection lost: {error}") from error


class LocalClient:
    """Calls a BaseVLA in this process; only for tests and HoldVLA (model libraries stay out of TopoGym)."""

    def __init__(self, model):
        self.model = model
        self.spec = model.spec

    def reset(self, seed):
        self._call(self.model.reset, seed)

    def infer(self, obs):
        return self._call(self.model.infer, obs)

    def close(self):
        pass

    @staticmethod
    def _call(method, argument):
        # Same contract as the model server: a model exception becomes a PolicyError.
        try:
            return method(argument)
        except Exception as error:
            raise PolicyError(f"{type(error).__name__}: {error}") from error
