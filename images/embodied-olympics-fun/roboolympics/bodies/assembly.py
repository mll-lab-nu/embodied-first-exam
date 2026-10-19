"""Assembled configurations (bodies/README.md "三个概念"): a robot of the library + its attachment(s) (bodies/hands)
+ the control libraries a sport declares = one configuration with its own version hash.

The robot's revision (body.toml) says when the robot changed; the configuration's hash says when anything that
decides how the assembled robot behaves changed: the robot's model, meshes, declarations and code, the attachment's
declaration and model, the declared control libraries, and the shared limit / servo path. Tasks and results record
the configuration id, so a result names exactly the robot it was played with.

    from bodies import assemble
    cfg = assemble("unitree_g1", "paddle", controllers=["wholebody"])
    cfg.id          # "unitree_g1@g1-2+paddle+wholebody#3f9c0a1b2c4d"
    cfg.hash        # the full sha256
    cfg.record()    # a dict for configuration.json, a sport's /spec or its results
    cfg.write(sim_dir / "bodies" / "configuration.json")

    from bodies.assembly import recorded
    recorded(sim_dir)   # what tools/generate.py wrote into a task's simulator directory (None if nothing)

Stable: the hash is a sha256 over a canonical JSON of the inputs and the sha256 of every file that takes part
(read as bytes; no timestamps, no paths outside bodies/), so the same files give the same hash in a checkout and in a
task's simulator directory (tools/sportlib.copy_body copies exactly these files).
"""
from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = ("limits.py", "servo.py", "selfcollision.py")         # the trusted limit / servo path, self-collision
ROBOT_FILES = ("body.toml", "model.xml", "*.py", "meshes/*", "meshes_25k/*", "policy/*.npz")   # behaviour, players' images
FILE_NAME = "configuration.json"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def robot_files(robot: str, root: Path = HERE) -> list[Path]:
    """The files of bodies/<robot>/ that decide its behaviour (not the fine meshes, provenance tools, licences)."""
    d = root / robot
    out = set()
    for pat in ROBOT_FILES:
        out.update(p for p in d.glob(pat) if p.is_file() and "__pycache__" not in p.parts)
    return sorted(out)


@dataclass
class Configuration:
    robot: str
    revision: str
    title: str
    status: str
    attachment: str | None
    other_attachment: str | None
    arm: str
    controllers: list
    files: dict = field(default_factory=dict)        # path relative to bodies/ -> sha256
    hash: str = ""

    @property
    def id(self) -> str:
        parts = [f"{self.robot}@{self.revision}", self.attachment or "bare"]
        if self.other_attachment:
            parts.append(f"{self.other_attachment}(other)")
        parts += list(self.controllers)
        return "+".join(parts) + "#" + self.hash[:12]

    def record(self) -> dict:
        return dict(id=self.id, hash=self.hash, robot=self.robot, revision=self.revision, title=self.title,
                    status=self.status, attachment=self.attachment, other_attachment=self.other_attachment,
                    arm=self.arm, controllers=list(self.controllers), files=dict(self.files))

    def write(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.record(), indent=1, sort_keys=True) + "\n")
        return path


def assemble(robot: str, attachment: str | None = None, other_attachment: str | None = None, controllers=(),
             arm: str = "right", root: Path | str | None = None) -> Configuration:
    """robot + attachment(s) + declared controllers -> a Configuration with its hash. root: the bodies/ directory
    (default: this one; a task's sim/bodies works the same)."""
    root = Path(root or HERE)
    decl = tomllib.loads((root / robot / "body.toml").read_text())
    b = decl["body"]
    files = {}
    for p in robot_files(robot, root):
        files[str(p.relative_to(root))] = _sha(p)
    for f in SHARED:
        if (root / f).exists():
            files[f] = _sha(root / f)
    hand_decl = {}
    for h in (attachment, other_attachment):
        if h:
            hands = tomllib.loads((root / "hands" / "hands.toml").read_text())
            if h not in hands:
                raise ValueError(f"unknown attachment {h!r}; one of {sorted(hands)}")
            hand_decl[h] = hands[h]
            files[f"hands/{hands[h]['file']}"] = _sha(root / "hands" / hands[h]["file"])
    controllers = sorted(set(controllers))
    for c in controllers:
        p = root / "control" / f"{c}.py"
        if not p.exists():
            raise ValueError(f"unknown controller {c!r} (bodies/control/{c}.py)")
        files[f"control/{c}.py"] = _sha(p)
    if b.get("kind") == "arm" and (attachment or other_attachment):
        raise ValueError(f"{robot} is a limits-only arm entry: its sport's scene carries the tool")
    canon = dict(robot=robot, revision=b["revision"], attachment=attachment, other_attachment=other_attachment,
                 arm=arm, controllers=controllers, attachments=hand_decl, files=dict(sorted(files.items())))
    h = hashlib.sha256(json.dumps(canon, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return Configuration(robot, b["revision"], b["title"], b.get("status", "library"), attachment, other_attachment,
                         arm, controllers, dict(sorted(files.items())), h)


def recorded(sim_dir) -> dict | None:
    """The configuration a task's simulator directory was generated with (sim/bodies/configuration.json), or None."""
    p = Path(sim_dir) / "bodies" / FILE_NAME
    return json.loads(p.read_text()) if p.exists() else None


def verify(sim_dir) -> tuple[bool, str]:
    """Recompute the recorded configuration from the files in sim_dir/bodies: (same hash?, the id)."""
    rec = recorded(sim_dir)
    if rec is None:
        return False, "no configuration.json"
    cfg = assemble(rec["robot"], rec["attachment"], rec["other_attachment"], rec["controllers"], rec["arm"],
                   root=Path(sim_dir) / "bodies")
    return cfg.hash == rec["hash"], cfg.id
