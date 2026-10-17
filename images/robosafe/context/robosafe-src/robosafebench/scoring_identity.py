"""Scoring-code provenance, independent of a record's historical service version.

This fingerprints the installed Python source, not a Git label, an image, a scene,
or the environment. Runtime code is immutable: restart a process after editing its
package. The cached fingerprint avoids rereading every source file on every save.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re


SCHEMA = "robosafebench-scoring/1"
EFFECTIVE_VERSION = "0.5.4"
CODE_SCOPE = "installed-package-python/1"
_REQUIRED = frozenset({"__init__.py", "scoring_identity.py", "episode/episode.py", "families/base.py",
                       "hazard/view.py", "verify/__init__.py", "assets/kit.py", "assets/labels.py"})


def _fingerprint(root: Path) -> dict:
    """Hash sorted package-relative names and the real bytes of every installed .py file."""
    base = {"schema": SCHEMA, "effective_version": EFFECTIVE_VERSION, "code_scope": CODE_SCOPE,
            "algorithm": "sha256"}
    try:
        manifest = [{"path": p.relative_to(root).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in sorted(root.rglob("*.py")) if p.is_file()]
        if not _REQUIRED.issubset({item["path"] for item in manifest}):
            return {**base, "status": "unavailable", "code_sha256": None, "reason": "required_source_unavailable"}
        data = json.dumps({"scope": CODE_SCOPE, "files": manifest}, sort_keys=True, separators=(",", ":")).encode()
        return {**base, "status": "available", "code_sha256": hashlib.sha256(data).hexdigest(),
                "file_count": len(manifest)}
    except OSError:
        return {**base, "status": "unavailable", "code_sha256": None, "reason": "source_read_failed"}


@lru_cache(maxsize=1)
def _installed_identity() -> dict:
    return _fingerprint(Path(__file__).resolve().parent)


def current_scoring() -> dict:
    """A caller-owned copy of this process's actual installed-code fingerprint."""
    return deepcopy(_installed_identity())


def _comparable(value) -> bool:
    return (isinstance(value, dict) and value.get("schema") == SCHEMA and value.get("code_scope") == CODE_SCOPE
            and value.get("algorithm") == "sha256" and value.get("status") == "available"
            and isinstance(value.get("effective_version"), str)
            and isinstance(value.get("code_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", value["code_sha256"]) is not None
            and type(value.get("file_count")) is int and value["file_count"] > 0)


def judgement_metadata(record: dict) -> dict:
    """Separate the producer's unverified claim from the actual current judge.

    Identity never changes pass, physics, or replay validity. A legacy record's
    missing identity stays unknown; even a matching declared hash is no proof of
    what an old producer really ran without independent source/image evidence.
    """
    recorded = deepcopy(record.get("recorded_scoring"))
    judged = current_scoring()
    comparable = _comparable(recorded) and _comparable(judged)
    fields = ("schema", "effective_version", "code_scope", "algorithm", "code_sha256")
    comparison = ("same" if all(recorded[k] == judged[k] for k in fields) else "different") if comparable else "unknown"
    return {"recorded_scoring": recorded, "judged_by": judged,
            "scoring_identity": {"recorded_status": "unknown" if recorded is None else "claimed",
                                 "recorded_is_authenticated": False, "comparison": comparison}}
