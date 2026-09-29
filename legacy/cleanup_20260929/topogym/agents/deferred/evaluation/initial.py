"""Separate physical initialization identity from rasterization noise."""
import json

from topogym.agent_bridge.session import write_json
from .suite import digest


def audit_initial(session, preset, private, reference=None):
    frame = json.loads((session.root / "initial/manifest.json").read_text())["frames"][0]
    adapter = session.adapter.adapter
    state = adapter.initial_state() if hasattr(adapter, "initial_state") else adapter.observe()
    audit = dict(state=state, state_sha256=digest(dict(state=state, preset=preset["sha256"])),
                 scope="adapter_initial_state" if hasattr(adapter, "initial_state") else "adapter_observation",
                 cameras={name: dict(path=str(session.root / info["path"]), sha256=info["sha256"])
                          for name, info in frame["cameras"].items()})
    target = private / "initial_audit.json"
    write_json(target, audit)
    comparison = {}
    if reference:
        from pathlib import Path
        expected = json.loads(Path(reference).read_text())
        if expected["state_sha256"] != audit["state_sha256"]:
            raise RuntimeError("Repeat physical initialization differs from the frozen variant reference")
        if set(expected["cameras"]) != set(audit["cameras"]):
            raise RuntimeError("Repeat camera set differs")
        tolerance = preset.get("initial_rgb_tolerance", {})
        for name, info in audit["cameras"].items():
            if info["sha256"] == expected["cameras"][name]["sha256"]:
                comparison[name] = dict(exact=True)
                continue
            import numpy as np
            from PIL import Image
            with Image.open(info["path"]) as image:
                actual = np.asarray(image.convert("RGB"), dtype=np.int16)
            with Image.open(expected["cameras"][name]["path"]) as image:
                previous = np.asarray(image.convert("RGB"), dtype=np.int16)
            if actual.shape != previous.shape:
                raise RuntimeError("Repeat camera resolution differs")
            error = np.abs(actual-previous)
            metrics = dict(mean_absolute=float(error.mean()), max_channel=int(error.max()),
                           changed_fraction=float(np.any(error != 0, axis=2).mean()))
            comparison[name] = dict(exact=False, **metrics)
            if any(value > tolerance.get(key, 0) for key, value in metrics.items()):
                raise RuntimeError(f"Repeat initial RGB differs beyond prepared tolerance: {name}, {metrics}")
    return dict(initial_state_sha256=audit["state_sha256"], initial_audit=str(target),
                initial_observation_sha256=digest(dict(state=state, preset=preset["sha256"],
                    cameras={k: v["sha256"] for k, v in audit["cameras"].items()})),
                initial_rgb_comparison=comparison, initial_state_scope=audit["scope"])
