"""Immutable JSON/NPZ plan cache and state-bound, fail-closed preparation."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from uuid import uuid4
from zipfile import BadZipFile

import numpy as np

from .contracts import digest, json_value
from .tracking import pose_error, relative
from topogym.utils.io import write_json_atomic


class CacheMiss(ValueError):
    pass


class PlanCache:
    def __init__(self, root):
        self.root = Path(root).absolute()
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError("Cache directory must not traverse symlinks")
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, bundle):
        bundle = json_value(bundle)
        required = {"identity", "start", "joint_names", "qpos", "request", "coverage"}
        if not isinstance(bundle, dict) or not required <= bundle.keys():
            raise ValueError(f"Plan bundle needs {sorted(required)}")
        if set(bundle["identity"]) != {"geometry", "joints", "execution"}:
            raise ValueError("identity declares geometry, joints and execution dependencies")
        names = bundle["joint_names"]
        q = np.asarray(bundle["qpos"], dtype=np.float64)
        if not names or len(set(names)) != len(names) or any(not isinstance(n, str) for n in names):
            raise ValueError("joint_names must be unique ordered strings")
        if q.ndim != 2 or not 0 < len(q) <= 10000 or q.shape[1] != len(names) or not np.isfinite(q).all():
            raise ValueError("qpos needs 1..10000 finite full robot samples in joint_names order")
        if np.asarray(bundle["start"]["qpos"]).shape != (len(names),):
            raise ValueError("Start qpos must use the same joint order")
        # Hash canonical values, not ZIP timestamps; equal plans have equal IDs.
        bundle["qpos"] = q.tolist()
        key = digest(bundle)
        final = self.root / key
        if final.exists():
            try:
                self.get(key)
                return self.describe(key)
            except CacheMiss:
                # Preserve corrupt bytes for diagnosis; regenerated data gets a fresh commit.
                os.rename(final, self.root / (".corrupt-"+key+"-"+uuid4().hex))
        temporary = Path(tempfile.mkdtemp(prefix=".writing-", dir=self.root))
        try:
            with (temporary / "arrays.npz").open("wb") as stream:
                np.savez_compressed(stream, qpos=q)
                stream.flush()
                os.fsync(stream.fileno())
            manifest = dict(schema_version=1, plan_id=key,
                arrays_sha256=hashlib.sha256((temporary / "arrays.npz").read_bytes()).hexdigest(),
                bundle={k: v for k, v in bundle.items() if k != "qpos"})
            write_json_atomic(temporary / "manifest.json", manifest, mode=0o600)
            try:
                os.rename(temporary, final)
            except OSError:
                if not final.exists():
                    raise
                self.get(key)
            return self.describe(key)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def get(self, key):
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
            raise CacheMiss("invalid_plan_id")
        folder = self.root / key
        try:
            if folder.is_symlink() or any((folder / n).is_symlink() for n in ("manifest.json", "arrays.npz")):
                raise ValueError("symlink entry")
            manifest = json.loads((folder / "manifest.json").read_text())
            if manifest["schema_version"] != 1 or manifest["plan_id"] != key:
                raise ValueError("identity mismatch")
            if hashlib.sha256((folder / "arrays.npz").read_bytes()).hexdigest() != manifest["arrays_sha256"]:
                raise ValueError("array checksum mismatch")
            with np.load(folder / "arrays.npz", allow_pickle=False) as arrays:
                bundle = dict(manifest["bundle"], qpos=arrays["qpos"].tolist())
            if digest(bundle) != key:
                raise ValueError("content checksum mismatch")
            return bundle
        except (OSError, ValueError, KeyError, TypeError, EOFError, BadZipFile) as exc:
            raise CacheMiss(f"missing_or_corrupt: {exc}") from exc

    def describe(self, key):
        return dict(plan_id=key, manifest=str(self.root / key / "manifest.json"),
                    coverage=self.get(key)["coverage"], reuse_authorized=False)

    def find(self, request):
        signature = digest(request)
        for folder in sorted(self.root.iterdir(), key=lambda p: p.name):
            if not re.fullmatch(r"[0-9a-f]{64}", folder.name):
                continue
            try:
                bundle = self.get(folder.name)
            except CacheMiss:
                continue
            if digest(bundle["request"]) == signature:
                yield folder.name


def state_differences(start, current):
    if set(start) != set(current):
        return None
    if np.asarray(start["qpos"]).shape != np.asarray(current["qpos"]).shape:
        return None
    result = {"joint_rad": float(np.max(np.abs(np.asarray(start["qpos"])-current["qpos"]))) }
    for collection, prefix in (("objects", "object"), ("grasps", "grasp")):
        if set(start[collection]) != set(current[collection]):
            return None
        errors = [pose_error(current[collection][n], p) for n, p in start[collection].items()]
        result[prefix+"_m"] = max((e["translation_m"] for e in errors), default=0.)
        result[prefix+"_rad"] = max((e["rotation_rad"] for e in errors), default=0.)
    names = list(start["objects"])
    errors = [pose_error(relative(current["objects"][a], current["objects"][b]),
                         relative(start["objects"][a], start["objects"][b]))
              for i, a in enumerate(names) for b in names[i+1:]]
    result["relative_m"] = max((e["translation_m"] for e in errors), default=0.)
    result["relative_rad"] = max((e["rotation_rad"] for e in errors), default=0.)
    result["contacts_changed"] = start["contacts"] != current["contacts"]
    return result


def validate_tolerances(tolerances):
    keys = {"joint_rad", "object_m", "object_rad", "relative_m", "relative_rad", "grasp_m", "grasp_rad"}
    if not isinstance(tolerances, dict) or set(tolerances) != keys | {"source", "repair_multiplier"}:
        raise ValueError(f"tolerances needs {sorted(keys)} plus source and repair_multiplier")
    if not tolerances["source"]:
        raise ValueError("Explain the clearance/tracking budget in tolerances.source")
    for key in keys | {"repair_multiplier"}:
        v = tolerances[key]
        if isinstance(v, bool) or not np.isfinite(v) or v < (1 if key == "repair_multiplier" else 0):
            raise ValueError("Tolerances must be finite and nonnegative; repair_multiplier >= 1")
    return keys


class PlanPreparation:
    """Adapter protocol: identity, snapshot, validate, plan, optional repair.

    Each call runs in the owning worker. Adapters receive read-only queries,
    never recursively submit work to that worker's CalibrationSession.
    """
    def __init__(self, cache, adapter, state_ref, cancelled=lambda: False):
        self.cache, self.adapter, self.state_ref, self.cancelled = cache, adapter, state_ref, cancelled

    def _validate(self, bundle):
        if self.cancelled():
            raise InterruptedError("Planning cancelled at validation boundary")
        result = json_value(self.adapter.validate(bundle))
        if type(result.get("passed")) is not bool or not isinstance(result.get("coverage"), list):
            raise ValueError("validate returns boolean passed and a list of coverage names")
        required = set(self.adapter.required_coverage)
        result["sufficient"] = bool(required <= set(result.get("coverage", [])))
        return result

    def check(self, key, tolerances):
        limits = validate_tolerances(tolerances)
        bound = json_value(self.state_ref())
        result = dict(plan_id=key, decision="miss", reasons=[], bound_state=bound,
                      valid_until="next state/branch/grasp/config change; call check_cached_plan again before consumption",
                      physical_success=False)
        try:
            bundle = self.cache.get(key)
        except CacheMiss as exc:
            return dict(result, reasons=[str(exc)])
        identity = self.adapter.identity(bundle["request"])
        if set(identity) != {"geometry", "joints", "execution"}:
            raise ValueError("Adapter identity must declare geometry, joints and execution")
        changed = [layer for layer in identity if identity[layer] != bundle["identity"].get(layer)]
        if changed:
            return dict(result, decision="seed_only" if changed == ["execution"] else "miss",
                        reasons=["dependency_changed:"+layer for layer in changed],
                        reusable_layers=[layer for layer in identity if layer not in changed])
        current = json_value(self.adapter.snapshot(bundle["request"]))
        result["bound_snapshot_digest"] = digest(current)
        differences = state_differences(bundle["start"], current)
        result["differences"] = differences
        if differences is None or differences["contacts_changed"]:
            return dict(result, reasons=["start_structure_or_contacts_changed"])
        outside = [name for name in limits if differences[name] > tolerances[name]]
        if outside:
            repairable = (callable(getattr(self.adapter, "repair", None)) and
                          all(differences[n] <= tolerances[n]*tolerances["repair_multiplier"] for n in limits))
            return dict(result, decision="repair" if repairable else "miss", reasons=["start_delta:"+n for n in outside])
        validation = self._validate(bundle)
        if json_value(self.state_ref()) != bound or digest(self.adapter.snapshot(bundle["request"])) != result["bound_snapshot_digest"]:
            return dict(result, reasons=["state_changed_during_check"])
        return dict(result, decision="reuse" if validation.get("passed") and validation["sufficient"] else
                    "seed_only" if not validation["sufficient"] else "miss", validation=validation,
                    reasons=[] if validation.get("passed") and validation["sufficient"] else ["path_validation_incomplete_or_failed"])

    def prepare(self, request, *, tolerances, use_cache=True):
        validate_tolerances(tolerances)
        request = json_value(request)
        timings, attempts, seed, chosen, selected, validation = {}, [], None, None, "planned", None
        start = time.monotonic()
        candidates = list(self.cache.find(request)) if use_cache else []
        timings["lookup_s"] = time.monotonic()-start
        bound = json_value(self.state_ref())
        start_snapshot = json_value(self.adapter.snapshot(request))
        for key in candidates:
            if self.cancelled():
                raise InterruptedError("Planning cancelled at candidate boundary")
            start = time.monotonic()
            check = self.check(key, tolerances)
            timings["check_s"] = timings.get("check_s", 0.)+time.monotonic()-start
            attempts.append(check)
            if check["decision"] == "reuse":
                chosen, selected = self.cache.get(key), "reused"
                break
            if check["decision"] in {"repair", "seed_only"}:
                seed = self.cache.get(key)
            if check["decision"] == "repair":
                start = time.monotonic()
                try:
                    repaired = self.adapter.repair(seed, request)
                    if repaired is not None:
                        validation = self._validate(repaired)
                        check["repair_validation"] = validation
                        if validation.get("passed") and validation["sufficient"]:
                            chosen, selected = repaired, "repaired"
                except (ValueError, NotImplementedError) as exc:
                    check["repair_error"] = str(exc)
                timings["repair_s"] = timings.get("repair_s", 0.)+time.monotonic()-start
                if chosen is not None:
                    break
        if chosen is None:
            if self.cancelled():
                raise InterruptedError("Planning cancelled before full planning")
            start = time.monotonic()
            chosen = self.adapter.plan(request, seed=seed)
            timings["plan_s"] = time.monotonic()-start
        if selected == "planned":
            # Fresh and repaired plans get precisely the same validation contract.
            start = time.monotonic()
            validation = self._validate(chosen)
            timings["validate_s"] = time.monotonic()-start
            if not validation.get("passed") or not validation["sufficient"]:
                raise ValueError("Prepared plan did not pass required validation: "+json.dumps(validation))
        if selected != "reused":
            if chosen["request"] != request or chosen["identity"] != self.adapter.identity(request):
                raise ValueError("Planner returned a different request or stale dependencies")
            if json_value(chosen["start"]) != start_snapshot:
                raise ValueError("Fresh/repaired plan must start from the measured snapshot")
            chosen = dict(chosen, coverage=validation)
        if json_value(self.state_ref()) != bound or json_value(self.adapter.snapshot(request)) != start_snapshot:
            raise ValueError("Measured state changed during plan preparation")
        saved = self.cache.put(chosen)
        return dict(**saved, selection=selected, plan=chosen, attempts=attempts, timings=timings,
                    bound_state=bound, bound_snapshot_digest=digest(start_snapshot),
                    valid_until="next state/branch/grasp/config change", execution_mode_unchanged=True,
                    physical_success=False)
