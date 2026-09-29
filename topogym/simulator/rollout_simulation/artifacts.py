"""Capability IDs for files: callers never supply filesystem paths."""
from pathlib import Path
from uuid import uuid4

from topogym.utils.io import relative_file, sha256_file


class ArtifactStore:
    def __init__(self, root):
        self.root = Path(root)
        self.entries = {}

    def add(self, relative, *, private=False, required_state_fields=()):
        if set(required_state_fields) - {"robot", "world", "task"}:
            raise ValueError("Unknown artifact state permission")
        path = relative_file(self.root, relative)
        if not path.is_file():
            raise ValueError("Artifact is not a regular file")
        identity = uuid4().hex
        self.entries[identity] = dict(relative=str(relative), private=private or bool(required_state_fields),
                                      required_state_fields=tuple(required_state_fields),
                                      sha256=sha256_file(path), size_bytes=path.stat().st_size)
        return dict(artifact_id=identity, sha256=self.entries[identity]["sha256"],
                    size_bytes=self.entries[identity]["size_bytes"])

    def read(self, identity, *, privileged=False):
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            raise ValueError("Artifact root cannot be a symlink")
        if not isinstance(identity, str) or identity not in self.entries:
            raise ValueError("Unknown artifact ID")
        entry = self.entries[identity]
        if entry["private"] and not privileged:
            raise PermissionError("Detailed artifacts require privilege")
        path = relative_file(self.root, entry["relative"])
        if not path.is_file() or sha256_file(path) != entry["sha256"]:
            raise ValueError("Artifact has changed")
        return path.read_bytes()
