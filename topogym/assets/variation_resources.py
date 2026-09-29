"""Verified, installable inputs for frozen historical geometry representatives."""

import json
from pathlib import Path
import zipfile

from .library import resource_path


def read_json(resource_id):
    return json.loads(resource_path(resource_id).read_text())


def unpack_assets(resource_id, output):
    """Copy a catalog-verified bundle into the episode's owned asset directory."""
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(resource_path(resource_id)) as bundle:
        for member in bundle.infolist():
            target = (root / member.filename).resolve()
            if not target.is_relative_to(root) or member.is_dir():
                raise ValueError(f"Invalid asset bundle member: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(member))

