"""The duel's source fingerprint (every .py file and the scene), shared by the service and the fresh-process replay."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent


def fingerprint():
    h = hashlib.sha256()
    paths = list(HERE.glob("*.py")) + list((HERE / "scene").rglob("*"))
    for p in sorted(set(paths)):
        if p.is_file():
            h.update(str(p.relative_to(HERE)).encode()); h.update(p.read_bytes())
    return h.hexdigest()
