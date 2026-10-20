from pathlib import Path
import os, hashlib, json

ROOT = Path(os.environ.get("CONTROL_ASSETS", "/opt/control-assets"))


def check(prefix):
    manifest = json.loads((ROOT / "manifest.json").read_text())
    entries = {k: v for k, v in manifest.items() if k.startswith(prefix + "/")}
    if not entries:
        raise RuntimeError("Asset manifest missing")
    for k, v in entries.items():
        if hashlib.sha256((ROOT / k).read_bytes()).hexdigest() != v:
            raise RuntimeError("Asset checksum mismatch")
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
