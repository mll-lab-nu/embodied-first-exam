"""Task-persistent scientific packages, original resources and managed programs."""
from __future__ import annotations

import ast
import base64
import hashlib
from importlib import metadata
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

from .broker import digest, encoded
from .sandbox import run_program


class Workspace:
    """Keep scientific inputs and outputs across executions in the same task."""

    def __init__(self, directory, discovery, broker):
        """Create a private package tree and immutable resource store."""
        self.directory = Path(directory).resolve()
        self.discovery, self.broker = discovery, broker
        for name in ("dependencies", "resources", "programs", "outputs", "tmp"):
            (self.directory / name).mkdir(parents=True, exist_ok=True)
        self.dependencies, self.resources = {}, {}
        self.save()

    def save(self):
        """Persist the exact dependency and resource identities used by programs."""
        manifest = {"schema": "workspace-manifest-v1", "python": sys.version,
                    "dependencies": self.dependencies, "resources": self.resources,
                    "sources": self.discovery.snapshot(), "outputs": str(self.directory / "outputs")}
        (self.directory / "manifest.json").write_text(encoded(manifest))
        return manifest

    def dependency(self, requirement, install=False):
        """Inspect or copy a pinned package; optionally install a wheel task-locally."""
        started = time.monotonic()
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:==([A-Za-z0-9_.+!-]+))?", requirement)
        if not match:
            raise ValueError("Use a package name for inspection or name==version for setup")
        name, version = match.groups()
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            distribution = None
        if not install:
            return {"name": name, "installed_version": distribution.version if distribution else None,
                    "requirements": distribution.requires if distribution else [],
                    "task_dependency": self.dependencies.get(name)}
        if not version:
            raise ValueError("Dependency setup requires an exact version")
        if name in self.dependencies:
            if self.dependencies[name]["version"] == version:
                return self.dependencies[name]
            raise ValueError("Dependency is pinned for this workspace; use a child task for a different version")
        target = self.directory / "dependencies" / f"{name}-{version}"
        staging = self.directory / "tmp" / f"{name}-{version}"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(exist_ok=True)
        if distribution and distribution.version == version:
            # Copy only distribution-owned files, never an entire host site-packages.
            for file in distribution.files or []:
                relative = Path(str(file))
                if relative.is_absolute() or ".." in relative.parts:
                    continue
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    destination = staging / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
            requirements = distribution.requires or []
            origin = "installed_distribution"
        else:
            index = self.discovery.spec.get("dependency_index", "https://pypi.org/simple")
            self.discovery.allowed(index)
            wheels = staging / "wheels"
            wheels.mkdir(exist_ok=True)
            try:
                subprocess.run([sys.executable, "-m", "pip", "--isolated", "download", "--no-deps",
                                "--only-binary=:all:", "--index-url", index, "--dest", str(wheels), requirement],
                               check=True, capture_output=True, timeout=max(.01, self.broker.deadline - time.monotonic()))
            except subprocess.SubprocessError as exc:
                raise ValueError("Task-local dependency download failed: " + requirement) from exc
            wheel = next(wheels.glob("*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                for item in archive.infolist():
                    if Path(item.filename).is_absolute() or ".." in Path(item.filename).parts:
                        raise ValueError("Invalid package path")
                archive.extractall(staging)
            shutil.rmtree(wheels)
            installed = next(metadata.distributions(path=[str(staging)]))
            requirements, origin = installed.requires or [], "pinned_wheel"
        files = {str(p.relative_to(staging)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(staging.rglob("*")) if p.is_file()}
        if not files:
            raise ValueError("Package has no reusable files")
        staging.rename(target)
        value = {"id": "dependency:" + digest(files), "name": name, "version": version,
                 "path": str(target), "requirements": requirements, "origin": origin, "files_hash": digest(files),
                 "elapsed_seconds": time.monotonic() - started}
        self.dependencies[name] = value
        self.save()
        self.broker.record("workspace.dependency", value)
        return value

    def resource(self, source, path):
        """Read original bytes described by a public manifest, checking actual dimensions."""
        import numpy as np
        from PIL import Image
        descriptor = self.discovery.value(source, path)
        if not isinstance(descriptor, dict) or not isinstance(descriptor.get("uri"), str):
            raise ValueError("Resource pointer must select public metadata with a uri")
        from urllib.parse import urljoin
        uri = urljoin(self.discovery.records[source]["resolved_uri"], descriptor["uri"])
        data, mime, _ = self.discovery.fetch(uri)
        sha = hashlib.sha256(data).hexdigest()
        if descriptor.get("sha256") and descriptor["sha256"] != sha:
            raise ValueError("Resource bytes differ from the public checksum")
        codec = descriptor.get("codec", "bytes")
        array = None
        if codec == "npy":
            array = np.load(io.BytesIO(data), allow_pickle=False)
        elif codec in {"png", "jpeg"}:
            array = np.asarray(Image.open(io.BytesIO(data)))
        elif codec == "raw":
            array = np.frombuffer(data, dtype=np.dtype(descriptor["dtype"])).reshape(descriptor["shape"])
        if array is not None:
            if "shape" in descriptor and list(array.shape) != descriptor["shape"]:
                raise ValueError("Resource dimensions differ from public metadata")
            if "dtype" in descriptor and np.dtype(descriptor["dtype"]) != array.dtype:
                raise ValueError("Resource dtype differs from public metadata")
        ident = "resource:" + digest({"sha256": sha, "metadata": descriptor, "source": source})
        destination = self.directory / "resources" / ident.split(":")[1]
        destination.write_bytes(data)
        value = {"schema": "resource-handle-v1", **descriptor, "id": ident, "uri": uri, "sha256": sha,
                 "mime_type": mime, "bytes": len(data), "path": str(destination), "source": source,
                 "dtype": str(array.dtype) if array is not None else descriptor.get("dtype"),
                 "shape": list(array.shape) if array is not None else descriptor.get("shape"),
                 "units": descriptor.get("units"), "frame": descriptor.get("frame"),
                 "invalid_values": descriptor.get("invalid_values"), "timestamp": descriptor.get("timestamp"),
                 "observation_id": descriptor.get("observation_id"), "calibration": descriptor.get("calibration")}
        self.resources[ident] = value
        self.save()
        self.broker.record("workspace.resource", value)
        return value

    def preview(self, reference):
        """Give Pi an optional RGB preview while preserving the original numerical bytes."""
        import numpy as np
        from PIL import Image
        handle = self.resources[reference]
        if handle.get("codec") == "npy":
            array = np.load(handle["path"], allow_pickle=False)
            if array.dtype != np.uint8 or array.ndim != 3 or array.shape[-1] not in {3, 4}:
                raise ValueError("Use raw arrays for numerical/depth resources; RGB previews require uint8 RGB/RGBA")
            picture = Image.fromarray(array)
        elif handle.get("codec") in {"png", "jpeg"}:
            picture = Image.open(handle["path"])
        else:
            raise ValueError("No RGB preview for this resource codec")
        picture.thumbnail((1024, 1024))
        output = io.BytesIO()
        picture.save(output, format="PNG")
        return {"records": [handle], "content": [{"type": "image", "mimeType": "image/png", "data": base64.b64encode(output.getvalue()).decode()}]}

    def run(self, source, value, *, invoke=None, dependencies=None):
        """Execute scientific code with persistent files and pipe-only environment calls."""
        ast.parse(source)
        ident = digest(source)
        (self.directory / "programs" / (ident + ".py")).write_text(source)
        started = time.monotonic()
        pinned = self.dependencies if dependencies is None else dependencies
        paths = [item["path"] for item in pinned.values()]
        result = run_program(source, value, invoke=invoke,
                             timeout=max(.01, min(60, self.broker.deadline - started)),
                             workspace=self.directory, sources=self.discovery.directory, import_paths=paths)
        self.broker.record("workspace.program", {"source_hash": ident, "dependencies": pinned,
                                               "elapsed_seconds": time.monotonic() - started})
        return result

    def call(self, action, arguments):
        """Expose generic task-local dependency, resource and pure computation operations."""
        if action == "manifest":
            return self.save()
        if action == "dependency":
            return self.dependency(arguments["requirement"], arguments.get("install", False))
        if action == "resource":
            return self.resource(arguments["source"], arguments["pointer"])
        if action == "preview":
            return self.preview(arguments["reference"])
        if action == "run":
            return {"output": self.run(arguments["source"], arguments.get("input"))}
        raise ValueError("Unknown workspace action")
