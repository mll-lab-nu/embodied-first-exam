"""Serve one episode over HTTP. The agent's container sees only this interface; hidden state stays in this process."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from embodied_safety_exam import verify as V
from embodied_safety_exam.harness import prompts
from embodied_safety_exam.sim.png import depth_png, encode_png


def status_body(ep) -> dict:
    """GET /status. Before the exit: whether it has ended, the calls made and the robot's time. After the exit (0.5.4):
    `{"status": "exited"}` and nothing else, so that nothing about how the episode went (a reason, a success or a
    failure, a count that differs between outcomes) reaches the agent after it, whatever the reset budget."""
    if ep.ended is not None:
        return {"status": "exited"}
    return {"ended": False, "calls": len(ep.calls), "robot_time_s": round(ep.world.time, 1)}


def serve(key: dict, host: str, port: int, out_dir: Path, condition: str = "default") -> None:
    fam, inst, ep = V.start(key)
    ep.deliver_only()           # a rendered response counts only after its complete transport write
    out_dir.mkdir(parents=True, exist_ok=True)
    brief = prompts.task_brief(fam, inst, condition)
    lock = threading.Lock()
    # realtime (0.5.1): the service's monotonic clock. A call's think gap is the time from the previous call's response
    # to this request's arrival (the first call has none: the clock starts with it); requests refused before they reach
    # the episode do not move the anchor, so their time is part of the next gap
    origin = time.monotonic()
    anchor = {"last": None}
    recipient = {"name": "agent"}
    available_frames: set[int] = set()       # receipts whose complete response reached the HTTP client
    picture_payloads: list[dict] = []       # encoded RGB payload identities, separate from completed delivery

    def save() -> None:
        rec = ep.record()
        rec["condition"] = condition
        rec["picture_delivery_recipient"] = recipient["name"]
        rec["picture_payloads"] = picture_payloads
        tmp = out_dir / "record.json.tmp"
        tmp.write_text(json.dumps(rec))
        os.replace(tmp, out_dir / "record.json")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def do_GET(self):
            if self.path == "/health":
                self._send(200, b'{"ok": true}')
            elif self.path == "/status":
                with lock:
                    body = status_body(ep)
                self._send(200, json.dumps(body).encode())
            elif self.path == "/brief":
                self._send(200, brief.encode(), "text/markdown; charset=utf-8")
            else:
                self._send(404, b'{"ok": false, "error": "not found"}')

        def do_POST(self):
            if self.path == "/flush":
                with lock:
                    save()
                return self._send(200, b'{"ok": true}')
            if self.path == "/picture-delivery":
                # The tool-calling harness is a trusted transport adapter. It can distinguish HTTP receipt by the
                # client from a later model request, using private frame receipts that it never exposes to the model.
                try:
                    data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    if not isinstance(data, dict):
                        raise ValueError
                except (ValueError, TypeError):
                    return self._send(400, b'{"ok": false, "error": "a delivery request must be a JSON object"}')
                with lock:
                    if data == {"recipient": "model"}:
                        if ep.calls:
                            return self._send(409, b'{"ok": false, "error": "the picture recipient is set before the first call"}')
                        recipient["name"] = "model"
                        save()
                        return self._send(200, b'{"ok": true, "recipient": "model", "protocol": "picture-delivery/1"}')
                    ids = data.get("frame_ids")
                    if recipient["name"] != "model":
                        return self._send(409, b'{"ok": false, "error": "model picture delivery was not configured"}')
                    if set(data) != {"frame_ids"} or not isinstance(ids, list) or any(
                            type(i) is not int or i not in available_frames for i in ids):
                        return self._send(400, b'{"ok": false, "error": "delivery names a frame without a completed capture response"}')
                    ep.deliver_picture_frames(ids)
                    save()
                    return self._send(200, b'{"ok": true}')
            if self.path != "/call":
                return self._send(404, b'{"ok": false, "error": "not found"}')
            arrived = time.monotonic()
            try:
                call = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                if not isinstance(call, dict):
                    raise ValueError
            except Exception:
                return self._send(400, b'{"ok": false, "error": "the body must be a JSON object {\\"tool\\": ..., \\"args\\": {...}}"}')
            with lock:
                if ep.clock == "realtime":
                    last = anchor["last"]
                    think = max(arrived - last, 0.0) if last is not None else 0.0
                    out = ep.execute(call, think_s=think, arrived=arrived - origin)
                else:
                    out = ep.execute(call)
                frames = {}
                if out.get("images"):
                    for camera in out["images"]:
                        detail = {"detail": ep._detail_view()} if camera == "detail" else {}
                        frames[camera] = ep.capture_pictures([camera], **detail)
                    if recipient["name"] == "model":
                        out["_picture_frame_ids"] = frames
                try:
                    if "images" in out:
                        encoded = {}
                        for camera, image in out["images"].items():
                            data = encode_png(image)
                            encoded[camera] = base64.b64encode(data).decode()
                            payload = {"camera": camera, "image_format": "png", "image_size": [image.shape[1], image.shape[0]],
                                       "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                            picture_payloads.append({"frame_id": frames[camera], "images": [payload]})
                        out["images"] = encoded
                    if "depth" in out:          # the control interface's RGB-D cameras: 16-bit PNG, millimetres, 0 = none
                        out["depth"] = {k: base64.b64encode(depth_png(v)).decode() for k, v in out["depth"].items()}
                    self._send(200, json.dumps(out).encode())
                    if frames:
                        available_frames.update(frames.values())
                        if recipient["name"] == "agent":
                            ep.deliver_picture_frames(frames.values())
                    if ep.clock == "realtime":
                        anchor["last"] = time.monotonic()   # a complete response: the agent's time starts
                finally:
                    # Keep a capture without a delivery on a failed write/flush. Holding the episode lock through
                    # transport also prevents a concurrent next action from preceding this delivery boundary.
                    save()

    httpd = ThreadingHTTPServer((host, port), Handler)

    def stop(*_):
        with lock:
            save()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    save()
    print(f"embodied_safety_exam: serving one episode on http://{host}:{port}", flush=True)
    httpd.serve_forever()
    with lock:
        save()
