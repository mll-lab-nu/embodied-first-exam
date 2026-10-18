import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import io, os, tempfile, unittest, zipfile
from unittest.mock import patch
import numpy as np
from scripts.control_transfer.control_public.weights import Network, shapes
from scripts.control_transfer.trusted.adapter import feedback, validate
from scripts.control_transfer.trusted.session import Session, atomic
from scripts.control_transfer.trusted.verify import verdict
from scripts.control_transfer.trusted.service import parse
from scripts.control_transfer.specs import spec, FAMILIES
from scripts.control_transfer.trusted.cpu_runtime import inspect_runtime


class BoundaryTests(unittest.TestCase):
    def test_cpu_evaluator_rejects_hardware_rendering_and_exposed_devices(self):
        for settings, devices in [
            ({"MUJOCO_GL": "egl", "CUDA_VISIBLE_DEVICES": ""}, []),
            ({"MUJOCO_GL": "osmesa", "CUDA_VISIBLE_DEVICES": "0"}, []),
            (
                {"MUJOCO_GL": "osmesa", "CUDA_VISIBLE_DEVICES": "", "ROBOENGINEER_ENFORCE_CPU_ISOLATION": "1"},
                ["/dev/nvidia0"],
            ),
        ]:
            with self.subTest(settings=settings), patch.dict(os.environ, settings, clear=True):
                with patch("scripts.control_transfer.trusted.cpu_runtime.gpu_devices", return_value=devices):
                    with self.assertRaises(RuntimeError):
                        inspect_runtime()

    def test_strict_json(self):
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}']:
            with self.assertRaises(ValueError):
                parse(raw)

    def test_numeric_archives(self):
        for family in ["linearbot", "g1"]:
            a = {k: np.zeros(shape, np.float32) for k, shape in shapes(family).items()}
            a["std"][:] = 1
            stream = io.BytesIO()
            np.savez_compressed(stream, **a)
            actor = Network(stream.getvalue(), family)
            self.assertEqual(actor(np.zeros(len(a["mean"]))).shape, (16 if family == "linearbot" else 29,))
            a["extra"] = np.zeros(1)
            stream = io.BytesIO()
            np.savez_compressed(stream, **a)
            with self.assertRaises(ValueError):
                Network(stream.getvalue(), family)

    def test_malicious_header_rejected_before_allocation(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for k, shape in shapes("g1").items():
                f = io.BytesIO()
                np.lib.format.write_array_header_1_0(
                    f, {"descr": "<f4", "fortran_order": False, "shape": (10**12,) if k == "mean" else shape}
                )
                z.writestr(k + ".npy", f.getvalue())
        with self.assertRaises(ValueError):
            Network(out.getvalue(), "g1")

    def test_banks_disjoint_and_stratified(self):
        for f in FAMILIES:
            v = spec(f, 0)
            banks = v["bank"]
            a = {(x["plant_seed"], x["episode_seed"]) for x in banks["adaptation"]}
            b = {(x["plant_seed"], x["episode_seed"]) for x in banks["held_out"]}
            self.assertFalse(a & b)
            if f == "yam":
                self.assertEqual({x["episode_seed"] % 9 for x in banks["adaptation"]}, set(range(9)))

    def test_hidden_plant_persists_across_rounds_and_held_out(self):
        for family in FAMILIES:
            first, second = spec(family, 0), spec(family, 1)
            plants = {c["plant_seed"] for cases in first["bank"].values() for c in cases}
            self.assertEqual(len(plants), 1)
            self.assertEqual(first["transfer_track"], "same-plant")
            self.assertNotIn(second["bank"]["adaptation"][0]["plant_seed"], plants)

    def test_same_plant_bank_cannot_silently_change_dynamics(self):
        v = spec("neural-fly", 0)
        v["bank"]["held_out"][0]["plant_seed"] += 1
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            Session(d, v, render=False)

    def test_feedback_excludes_privileged_fields(self):
        with tempfile.TemporaryDirectory() as d:
            r = {
                "feedback": {
                    "telemetry": [{"t": 0.0, "values": [0.1] * 29}],
                    "commands": [{"t": 0.0, "values": [0.0, 0.0, 0.0]}],
                },
                "metrics": {"score": 100},
                "dynamics": {"secret": 42},
            }
            self.assertEqual(set(feedback("g1", r, d)), {"telemetry", "commands", "images"})
            r["feedback"]["true_state"] = [1]
            with self.assertRaises(ValueError):
                feedback("g1", r, d)

    def test_named_sensor_vectors_cannot_hide_additional_values(self):
        row = {"t": 0.0, "quaternion": [1.0, 0.0, 0.0, 0.0]}
        row.update(
            {
                name: [0.0] * 3
                for name in (
                    "position",
                    "velocity",
                    "omega",
                    "target_position",
                    "target_velocity",
                    "target_acceleration",
                )
            }
        )
        with tempfile.TemporaryDirectory() as folder:
            value = {"feedback": {"telemetry": [row]}}
            self.assertEqual(len(feedback("neural-fly", value, folder)["telemetry"]), 1)
            row["position"].append(123.0)
            with self.assertRaises(ValueError):
                feedback("neural-fly", value, folder)

    def test_nop_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            v = spec("spacecraft", 0)
            s = Session(Path(d) / "run", v, render=False)
            self.assertIsNone(s.state["deadline"])
            s.call("describe", {})
            deadline = s.state["deadline"]
            restored = Session(Path(d) / "run", v, render=False)
            self.assertEqual(restored.state["deadline"], deadline)
            restored.finalize()
            p = Path(d) / "instance.json"
            atomic(p, v)
            r = verdict(s.root, p)
            self.assertEqual(r["infra_error"], 0)
            self.assertEqual(r["success"], 0)

    def test_operator_cutoff_survives_service_restart(self):
        from scripts.control_transfer.trusted.service import Runtime

        with tempfile.TemporaryDirectory() as d, patch("signal.signal"):
            root = Path(d)
            instance = root / "instance.json"
            atomic(instance, spec("spacecraft", 0))
            runtime = Runtime(root / "data", instance, 3600)
            self.assertNotIn("error", runtime.call("describe", {}))
            runtime.request_finalize()
            cutoff = runtime.cutoff
            restored = Runtime(root / "data", instance, 3600)
            self.assertEqual(restored.cutoff, cutoff)
            self.assertIn("error", restored.call("describe", {}))
            self.assertIn("error", restored.session.call("describe", {}))
            self.assertEqual(restored.session.close(cutoff + 100), cutoff)

    def test_interrupted_finalization_replays_frozen_bank_and_preserves_partial_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            value = spec("spacecraft", 0)
            session = Session(d, value, render=False)
            fake = {
                "metrics": {"score": 80.0, "success": True},
                "feedback": {"telemetry": [{"t": 0.0, "values": [0.0] * 13}]},
                "state_sha256": "a" * 64,
            }
            with patch.object(session, "episode", return_value=fake):
                deployed = session.call(
                    "deploy", {"policy": value["public"]["default_policy"], "diagnosis": "baseline"}
                )
            calls = []

            def interrupted(policy, case, out, render, track=True):
                out.mkdir()
                (out / "partial.txt").write_text("retained")
                calls.append(case)
                if len(calls) == 3:
                    raise KeyboardInterrupt()
                return fake

            with patch.object(session, "episode", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
                session.finalize()
            cutoff = session.close()
            restored = Session(d, value, render=False)
            self.assertIn("error", restored.call("describe", {}))
            with patch.object(restored, "episode", return_value=fake) as episode:
                final = restored.finalize()
                self.assertEqual(episode.call_count, 2 * len(value["bank"]["held_out"]))
            self.assertFalse(final["infra_error"])
            self.assertEqual(final["policy_sha256"], deployed["policy_sha256"])
            self.assertEqual(restored.close(), cutoff)
            # the held-out cases run concurrently: the interrupted run left at least the three episodes it reached
            self.assertGreaterEqual(len(list(Path(d).glob("held-out-interrupted-*/case-*/partial.txt"))), 3)
            with patch.object(restored, "episode", side_effect=AssertionError("must not replay completed final")):
                self.assertEqual(restored.finalize(), final)

    def test_interrupted_round_is_not_reset(self):
        with tempfile.TemporaryDirectory() as d:
            v = spec("spacecraft", 0)
            s = Session(d, v, render=False)
            s.state["rounds"] = [{"status": "running"}]
            s.persist()
            s = Session(d, v, render=False)
            self.assertTrue(s.state["infra_error"])
            self.assertIn("error", s.call("describe", {}))

    def test_bad_instance_and_bad_evidence_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            v = spec("spacecraft", 0)
            p = Path(d) / "instance.json"
            atomic(p, v)
            s = Session(Path(d) / "run", v, render=False)
            s.finalize()
            v["index"] = 9
            atomic(p, v)
            self.assertEqual(verdict(s.root, p)["infra_error"], 1)

    def test_official_verifier_requires_cpu_evidence(self):
        v = spec("spacecraft", 0)
        v["bank"]["held_out"] = v["bank"]["held_out"][:1]
        v["evaluation_requirements"] = {"physics": "mujoco-cpu", "device_isolation_verified": True, "gpu_devices": []}
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            atomic(data / "instance.json", v)
            session = Session(data / "session", v, render=False)
            fake = {
                "metrics": {"score": 80.0, "success": True},
                "feedback": {"telemetry": [{"t": 0.0, "values": [0.0] * 13}]},
                "state_sha256": "a" * 64,
            }
            with patch.object(session, "episode", return_value=fake):
                session.call("deploy", {"policy": v["public"]["default_policy"], "diagnosis": "baseline"})
                session.finalize()
            self.assertEqual(verdict(session.root, data / "instance.json")["infra_error"], 1)
            for replay in ("a", "b"):
                atomic(
                    session.root / "held-out" / f"case-0-{replay}.runtime.json",
                    {**v["evaluation_requirements"], "software_renderer_verified": replay == "a"},
                )
            self.assertEqual(verdict(session.root, data / "instance.json")["success"], 1)
            atomic(
                session.root / "held-out" / "case-0-a.runtime.json",
                {**v["evaluation_requirements"], "gpu_devices": ["/dev/nvidia0"], "software_renderer_verified": True},
            )
            self.assertEqual(verdict(session.root, data / "instance.json")["infra_error"], 1)

    def test_no_shell_paths_as_policy(self):
        for family in ("g1", "linearbot"):
            with self.assertRaises(ValueError):
                validate(family, {"path": "/srv/instance.json"})

    def test_budget_and_seal(self):
        with tempfile.TemporaryDirectory() as d:
            v = spec("spacecraft", 0)
            s = Session(d, v, render=False)
            fake = {
                "metrics": {"score": 80.0, "success": True},
                "feedback": {"telemetry": [{"t": 0.0, "values": [0.0] * 13}]},
                "state_sha256": "a" * 64,
            }
            with patch.object(s, "episode", return_value=fake):
                for i in range(3):
                    self.assertEqual(
                        s.call(
                            "deploy",
                            {"policy": v["public"]["default_policy"], "diagnosis": "Observed drift; increase damping."},
                        )["round_id"],
                        i,
                    )
                self.assertIn(
                    "error", s.call("deploy", {"policy": v["public"]["default_policy"], "diagnosis": "fourth"})
                )
                self.assertTrue(s.call("seal", {"round_id": 1, "summary": "Choose second."})["sealed"])
                self.assertIn("error", s.call("describe", {}))
                result = s.finalize()
                self.assertFalse(result["infra_error"])
                self.assertEqual(len(result["episodes"]), 6)


if __name__ == "__main__":
    unittest.main()
