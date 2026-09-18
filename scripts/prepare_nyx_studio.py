"""Download the CC0 studio HDRI and wood maps for TopoGym's Nyx demo.

Source: https://polyhaven.com/a/studio_small_09 (Sergej Majboroda).
"""

import hashlib
from pathlib import Path
import urllib.request


def main():
    root = Path(__file__).resolve().parents[1] / ".external" / "nyx-assets"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "studio_small_09_2k.hdr"
    expected = "36724313c0fc66dab126ff90f081b85a0b1ef47be65eda1417bd20b033f0573f"
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        url = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/studio_small_09_2k.hdr"
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("HDRI checksum mismatch")
        path.write_bytes(data)
    (root / "CREDITS.txt").write_text(
        "Studio Small 09 by Sergej Majboroda / Poly Haven\n"
        "https://polyhaven.com/a/studio_small_09\nLicense: CC0\n\n"
        "Wood Table 001 by Dimitrios Savva and Rico Cilliers / Poly Haven\n"
        "https://polyhaven.com/a/wood_table_001\nLicense: CC0\n"
    )
    for key, checksum in (
        ("diff", "aef45ab36d9f258b80edf278d417920b7326ad77c341d6618498d4598c59fd2c"),
        ("nor_gl", "3d1dc2cc14cd9a3d2bc0035560aa715f4f8786902b4b72e78135f1d097428f98"),
    ):
        name = f"wood_table_001_{key}_1k.png"
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            url = f"https://dl.polyhaven.org/file/ph-assets/Textures/png/1k/wood_table_001/{name}"
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != checksum:
                raise RuntimeError(f"Wood texture checksum mismatch: {name}")
            path.write_bytes(data)
    print(f"Nyx studio and wood assets ready: {root}")


if __name__ == "__main__":
    main()
