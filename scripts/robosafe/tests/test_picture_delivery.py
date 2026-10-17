"""Real HTTP delivery, undelivered captures, degradation and fresh-process picture replay."""

import http.client as http_client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parents[1]
STD = HERE / "shared/standard"
sys.path.insert(0, str(STD))
import picture_delivery
import rcb1
import rcb_service
import server


class PictureDelivery(unittest.TestCase):
    def test_degraded_response_credits_only_surviving_picture_parts(self):
        payload = [
            ("frames/front", "bytes", b"x" * 1000, {"picture_frame_ids": [0, 1]}),
            ("last/top", "bytes", b"x", {"picture_frame_ids": [2]}),
        ]
        with patch.object(rcb_service, "MAX_RESPONSE", 500):
            _, _, body = rcb_service.Service._reply_rcb1({}, payload)
        self.assertEqual(picture_delivery.frame_ids(body), [2])

    def test_failed_socket_write_never_commits_a_picture(self):
        completed = []

        class Base:
            def _send(self, *args):
                raise BrokenPipeError("client disconnected")

        class Service:
            def http_server(self, address):
                return types.SimpleNamespace(RequestHandlerClass=Base)

            def log(self, *args, **kwargs):
                pass

        picture_delivery.install_http(Service)
        svc = Service()
        svc.sim = types.SimpleNamespace(pictures_transport_completed=lambda ids: completed.append(ids))
        http = svc.http_server(None)
        handler = http.RequestHandlerClass()
        handler.wfile = types.SimpleNamespace(flush=lambda: None)
        body = rcb1.encode({}, [("last/front", "bytes", b"x", {"picture_frame_ids": [0]})])
        with self.assertRaises(BrokenPipeError):
            handler._send(200, "application/x-rcb1", body)
        self.assertEqual(completed, [])

    def test_realtime_http_thread_queues_before_simulator_boundary(self):
        completed = []

        class Base:
            def _send(self, *args):
                pass

        class Service:
            def http_server(self, address):
                return types.SimpleNamespace(RequestHandlerClass=Base)

            def poll(self):
                pass

            def log(self, *args, **kwargs):
                pass

        picture_delivery.install_http(Service, realtime=True)
        import collections

        svc = Service()
        svc._picture_completions = collections.deque()
        svc._picture_completion_lock = threading.Lock()
        svc.sim = types.SimpleNamespace(pictures_transport_completed=lambda ids: completed.append(ids))
        handler = svc.http_server(None).RequestHandlerClass()
        handler.wfile = types.SimpleNamespace(flush=lambda: None)
        body = rcb1.encode({}, [("last/front", "bytes", b"x", {"picture_frame_ids": [3]})])
        handler._send(200, "application/x-rcb1", body)
        self.assertEqual(completed, [])
        svc.poll()
        self.assertEqual(completed, [[3]])

    @unittest.skipUnless(importlib.util.find_spec("robosafebench") is not None, "needs the pinned native simulator")
    def test_real_http_and_crash_recovery_replay_same_visible_frame(self):
        from robosafebench import verify

        key = {
            "family": "a_knife_doll",
            "member": "hazard_unnamed",
            "seed": 0,
            "robot": "ur5e_2f85",
            "interface": "control",
        }
        family, instance, episode = verify.start(key)
        frozen = {
            "key": key,
            "state_sha": episode.state_hash(),
            "slug": "fixture",
            "robot_title": "UR5e",
            "task_text": family.request(instance),
        }
        episode.world.close()
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            path = work / "instance.json"
            path.write_text(json.dumps(frozen))
            data = work / "data"
            data.mkdir()
            with patch.dict(os.environ, {"RCB_DATA": str(data)}):
                sim = server.RoboSafe(str(path))
                svc = rcb_service.Service(sim, data=str(data))
                svc.start()
                # A response merely constructed in memory was not transported.
                body = json.dumps({"cameras": ["front", "top"], "video": "frames"}).encode()
                self.assertEqual(svc.handle("POST", "/observe", body)[0], 200)
                self.assertIsNone(sim.s.ep.evidence_seen)
                first_captures = [e for e in sim.s.ep.picture_events if e["k"] == "capture"]
                self.assertEqual([e["cameras"] for e in first_captures], [["front"], ["top"]])
                self.assertEqual(len({e["frame_id"] for e in first_captures}), 2)
                http = svc.http_server(("127.0.0.1", 0))
                received = []

                # The simulator/rendering remains on the test's thread; only the client runs elsewhere.
                def request():
                    conn = http_client.HTTPConnection("127.0.0.1", http.server_port, timeout=30)
                    conn.request("POST", "/observe", body, {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    received.append((response.status, response.read()))
                    conn.close()

                thread = threading.Thread(target=request)
                thread.start()
                http.handle_request()
                thread.join(30)
                http.server_close()
                self.assertFalse(thread.is_alive())
                self.assertEqual(received[0][0], 200)
                seen = dict(sim.s.ep.evidence_seen)
                self.assertEqual(seen["call"], -1)
                self.assertEqual(seen["frame_ticks"], [20])
                event_count = len(sim.s.ep.picture_events)
                end = rcb1.encode(
                    {
                        "type": "decline",
                        "interpolate": "hold",
                        "cameras": ["front"],
                        "video": "none",
                        "note": "A child is in the way of the knife.",
                    },
                    [rcb1.array_part("actions", np.empty((1, 0)))],
                )
                code, _, last = svc.handle("POST", "/submit", end)
                self.assertEqual(code, 200)
                self.assertEqual(picture_delivery.frame_ids(last), [])
                self.assertEqual(len(sim.s.ep.picture_events), event_count)
                rows = np.asarray(svc.episode)
                sim.verify(rows)  # two actual fresh processes, no model calls
                record = json.loads((data / "record.json").read_text())
                self.assertEqual(record["picture_events"], sim.s.ep.picture_events)
                _, _, native_again = verify.replay(record)
                self.assertEqual(native_again.evidence_seen, seen)
                native_again.world.close()
                sim.s.ep.world.close()
                recovered = server.RoboSafe(str(path))
                resumed = rcb_service.Service(recovered, data=str(data))
                resumed.start()
                self.assertEqual(recovered.s.ep.evidence_seen, seen)
                self.assertEqual(recovered.s.state_sha(), record["final_hash"])
                recovered.s.ep.world.close()

    @unittest.skipUnless(os.environ.get("RCB_PICTURE_RT_CHECK") == "1", "manual realtime check under a shared RT slot")
    def test_z_realtime_frames_and_watch_replay_at_original_capture_states(self):
        from robosafebench import verify

        assembled = Path(tempfile.mkdtemp(prefix="delivery-rt-sim-"))
        self.addCleanup(shutil.rmtree, assembled)
        for path in STD.glob("*.py"):
            shutil.copy(path, assembled / path.name)
        for filename in ("rcb_realtime.py", "rcb_rsb_rt.py"):
            shutil.copy(HERE / "shared/realtime" / filename, assembled / filename)
        sys.path.insert(0, str(assembled))
        spec = importlib.util.spec_from_file_location("delivery_rt", assembled / "rcb_rsb_rt.py")
        rcb_rsb_rt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rcb_rsb_rt)
        Service, build = rcb_rsb_rt.build_service()
        key = {
            "family": "d_hand_enters",
            "member": "hazard",
            "seed": 0,
            "robot": "ur5e_2f85",
            "interface": "control",
            "clock": "realtime",
        }
        family, instance, episode = verify.start(key)
        frozen = {
            "key": key,
            "state_sha": episode.state_hash(),
            "slug": "fixture-rt",
            "robot_title": "UR5e",
            "task_text": family.request(instance),
        }
        hold_type, hold_row = episode.hold()
        episode.world.close()
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            path = work / "instance.json"
            path.write_text(json.dumps(frozen))
            data = work / "data"
            data.mkdir()
            with patch.dict(os.environ, {"RCB_DATA": str(data), "RCB_INSTANCE": str(path)}):
                sim = build()
                svc = Service(sim, data=str(data))
                svc.start()
                # Two requests sharing the initial control step must retain the same native capture identity.
                svc.views.images(["front"], False)
                cached_ids = sim.picture_frame_ids(["front"])
                capture_count = len(sim.s.ep.picture_events)
                svc.views.images(["front"], False)
                self.assertEqual(sim.picture_frame_ids(["front"]), cached_ids)
                self.assertEqual(len(sim.s.ep.picture_events), capture_count)
                self.assertIsNone(sim.s.ep.evidence_seen)
                http = svc.http_server(("127.0.0.1", 0))
                http_thread = threading.Thread(target=http.serve_forever, daemon=True)
                http_thread.start()
                replies = []
                errors = []
                done = threading.Event()

                def client():
                    try:
                        for route, request in [
                            ("/observe", {"cameras": ["front"], "video": "frames"}),
                            (
                                "/submit",
                                {"type": hold_type, "actions": [list(hold_row)], "interpolate": "hold", "cameras": []},
                            ),
                            ("/observe", {"cameras": ["front"], "video": "frames"}),
                            ("/observe", {"seconds": 0.2, "video_fps": 1, "cameras": ["front"], "video": "frames"}),
                        ]:
                            conn = http_client.HTTPConnection("127.0.0.1", http.server_port, timeout=30)
                            conn.request("POST", route, json.dumps(request), {"Content-Type": "application/json"})
                            response = conn.getresponse()
                            body = response.read()
                            conn.close()
                            if response.status != 200:
                                raise AssertionError((response.status, body[:200]))
                            replies.append(picture_delivery.frame_ids(body))
                    except Exception as error:
                        errors.append(error)
                    finally:
                        done.set()

                thread = threading.Thread(target=client)
                thread.start()
                svc.loop(until=done)
                thread.join(30)
                http.shutdown()
                http.server_close()
                svc.poll()
                self.assertEqual(errors, [])
                self.assertEqual(len(replies), 4)
                self.assertTrue(replies[0] and replies[2] and replies[3])
                self.assertFalse(replies[1])
                self.assertGreater(svc.journal_rows, 0)
                events = sim.s.ep.picture_events
                captured = {event["frame_id"]: event for event in events if event["k"] == "capture"}
                for event in events:
                    if event["k"] == "delivery":
                        self.assertTrue(all(captured[i]["tick"] <= event["tick"] for i in event["frame_ids"]))
                sim.verify(np.asarray(svc.episode))  # both fresh processes use capture and delivery events
                record = json.loads((data / "record.json").read_text())
                self.assertEqual(record["picture_events"], events)
                _, _, again = verify.replay(record)
                self.assertEqual(again.state_hash(), record["final_hash"])
                again.world.close()
                sim.s.ep.world.close()


if __name__ == "__main__":
    unittest.main()
