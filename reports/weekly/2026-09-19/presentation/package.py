"""Package only the self-contained, browser-ready presentation."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json
import re

OUT = Path(__file__).resolve().parent
DEST = OUT.parent / "TopoGym_Spatial_Constraints_2026-09-19.zip"
FILES = ["index.html", "deck.css", "deck.js", "progress.svg", "speaker-notes.md",
         "manifest.json", "README.md", "validation.json", "preview.jpg"]
paths = [OUT/name for name in FILES]
paths += sorted((OUT/"media").glob("*.mp4"))
paths += sorted((OUT/"posters").glob("*.jpg"))
manifest = json.loads((OUT/"manifest.json").read_text())
for movies in manifest["media"].values():
    for m in movies:
        assert OUT/m["src"] in paths
        assert OUT/m["poster"] in paths
assert len(list((OUT/"media").glob("*.mp4"))) == manifest["available_videos"] == 39
for name in ("index.html", "deck.css", "deck.js"):
    text = (OUT/name).read_text()
    assert "/home/jianwen" not in text
    assert not re.search(r'(?:src|href)="https?://', text), name
with ZipFile(DEST, "w", ZIP_DEFLATED, compresslevel=3) as z:
    for p in paths:
        z.write(p, "topogym-presentation/"+str(p.relative_to(OUT)))
with ZipFile(DEST) as z:
    assert z.testzip() is None
    for p in paths:
        assert hashlib.sha256(z.read("topogym-presentation/"+str(p.relative_to(OUT)))).digest() == hashlib.sha256(p.read_bytes()).digest()
print(f"{DEST}: {len(paths)} files, {DEST.stat().st_size/1e6:.2f} MB; ZIP contents and hashes verified.")

