"""Operator-only asset preparation. Download a pinned checkpoint, never run upstream code."""

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import numpy as np

COMMIT = "30ab04cb5ac3fd4fa55cd2a168ee28aa679f5e9b"
SHA256 = "abcce30c945709ace29c3c68159738717a945b8e87f73d74bd3dcb54f74002e9"
URL = f"https://raw.githubusercontent.com/GuanyaShi/neural_lander_sim_1d/{COMMIT}/Fa_net_12_3_full_Lip16.pth"
SHAPES = [(25, 12), (30, 25), (15, 30), (3, 15)]


def prepare(out):
    import torch  # preparation only; runtime inference is NumPy/CPU

    out.mkdir(parents=True, exist_ok=False)
    raw = urllib.request.urlopen(URL, timeout=60).read()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError("Upstream asset hash mismatch")
    import io

    weights = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=True)
    arrays = {}
    expected = {f"fc{i}.{kind}" for i in range(1, 5) for kind in ("weight", "bias")}
    if set(weights) != expected:
        raise ValueError("Unexpected checkpoint keys")
    for i, shape in enumerate(SHAPES, 1):
        for kind, dims in [("weight", shape), ("bias", (shape[0],))]:
            array = weights[f"fc{i}.{kind}"].detach().numpy()
            if array.shape != dims or not np.isfinite(array).all():
                raise ValueError("Unexpected checkpoint tensor")
            arrays[f"{kind}{i}"] = array.astype(np.float64)
    np.savez(out / "residual.npz", **arrays)
    (out / "provenance.json").write_text(
        json.dumps(
            {
                "url": URL,
                "commit": COMMIT,
                "source_sha256": SHA256,
                "converted_sha256": hashlib.sha256((out / "residual.npz").read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
    return out / "residual.npz"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    print(prepare(p.parse_args().out))
