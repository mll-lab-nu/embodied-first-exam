"""A distinct public switchboard family for acceptance after the runtime is frozen."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading


class PublicSwitchboard:
    """Use POST RPC, reversed valve codes and acknowledgments without sensor data."""

    def __init__(self, family="heldout"):
        self.actions, self.reads = [], []
        self.slots, self.sequence = [1, 1, 1], 0
        board = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def reply(self, value):
                data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                if self.path == "/public/guide.md":
                    self.reply('''# Switchboard public guide
The sole RPC endpoint is POST /v2/rpc. It accepts JSON. No initialization is required.
Use {"verb":"view"} to obtain a read-only sample:
{"slots":[1,1,1],"sequence":0}. The slots are ordered [drain,supply_b,supply_a].
Wire value 0 means open, 1 means closed. The initial state is not guaranteed; read it.
Use {"verb":"apply","slots":[1,0,0],"ticket":"any-unique-id"} to set the three valves.
An apply requires a current sample, consumes one action, and settles in 50 ms.
It returns an acknowledgment {"ack":"the-ticket","sequence":new_sequence}; this is NOT a new sample.
Call view after an apply before making another decision or asserting the valve positions.
The coordinate/frame convention is not applicable to these dimensionless valve codes.
There are no status, reset, stop, hidden success, camera, calibration or depth endpoints.
Reads consume no actions and do not advance physical time. Only apply changes the valves.
The public dependency-free Python encoder is at [client.py](client.py).
No machine-readable schema or JSON reference file is available; the above are public examples.
''')
                elif self.path == "/public/client.py":
                    self.reply('''"""Public request encoder for the switchboard HTTP RPC."""
def view():
    return {"body": {"verb": "view"}}
def apply(slots, ticket):
    return {"body": {"verb": "apply", "slots": slots, "ticket": ticket}}
''')
                else:
                    self.send_error(404)
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path != "/v2/rpc":
                    self.send_error(404)
                elif payload.get("verb") == "view":
                    board.reads.append(list(board.slots))
                    self.reply({"slots": board.slots, "sequence": board.sequence})
                elif payload.get("verb") == "apply" and len(payload.get("slots", [])) == 3 and all(x in {0, 1} for x in payload["slots"]):
                    board.slots = payload["slots"]
                    board.sequence += 1
                    board.actions.append(payload)
                    self.reply({"ack": payload["ticket"], "sequence": board.sequence})
                else:
                    self.send_error(400)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def bootstrap(self):
        return {"schema": "bootstrap-v1", "task": "Open both supply valves, leave the drain closed, and obtain a confirming public sample. Use the public interface documentation.",
                "entries": [self.url + "/public/guide.md"], "source_roots": [self.url + "/public"], "internet": False,
                "transports": [{"id": "switchboard", "kind": "http", "root": self.url + "/v2"}], "max_actions": 8}

    def outcome(self, output):
        return {"public_sample": bool(self.reads), "bounded_actions": bool(self.actions),
                "physical_actions": len(self.actions), "final_slots": self.slots,
                "task_success": self.slots == [1, 0, 0] and bool(self.reads) and self.reads[-1] == [1, 0, 0]}

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
