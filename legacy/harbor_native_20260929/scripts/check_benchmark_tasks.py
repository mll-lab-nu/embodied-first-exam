#!/usr/bin/env python3
"""Read-only structural and source-isolation validation of exported tasks."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import yaml
from harbor.models.dataset.manifest import DatasetManifest
from harbor.models.task.config import TaskConfig
from harbor.publisher.packager import Packager

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from topogym.benchmark.evidence import digest


def check_verifier_entrypoint(directory):
    """Check our generated image contract; building/running remains a separate check.

    Harbor skips tests upload for separate verifiers. Merely publishing test.sh
    beside the Dockerfile is insufficient: the image must install it at /tests.
    """
    tests=Path(directory)/"tests"
    script=tests/"test.sh"
    assert script.is_file() and not script.is_symlink(),f"Missing verifier entrypoint: {script}"
    assert script.stat().st_mode & 0o111,f"Verifier entrypoint is not executable: {script}"
    instructions=[shlex.split(line,comments=True) for line in (tests/"Dockerfile").read_text().splitlines()]
    assert ["COPY","--chmod=755","test.sh","/tests/test.sh"] in instructions, (
        f"{tests/'Dockerfile'} must install /tests/test.sh with executable permissions; "
        "re-export this task with the current TopoGym exporter"
    )
    syntax=subprocess.run(["sh","-n",str(script)],capture_output=True,text=True)
    assert syntax.returncode==0,f"Invalid verifier shell script {script}: {syntax.stderr}"


def check(root):
    root=Path(root)
    dataset=DatasetManifest.from_toml_file(root/"dataset.toml")
    bundle_cache={}
    for row in dataset.tasks:
        directory=root/row.short_name
        config=TaskConfig.model_validate_toml((directory/"task.toml").read_text())
        assert config.task.name==row.name,"Dataset/task names differ"
        assert config.verifier.environment_mode.value=="separate"
        check_verifier_entrypoint(directory)
        compose=yaml.safe_load((directory/"environment/docker-compose.yaml").read_text())
        mode=config.metadata["mode"]
        services=compose["services"]
        assert all(not service.get("volumes") for service in services.values()),"Writable/shared host mounts forbidden"
        if mode=="limited":
            assert set(services)=={"main","sim"} and config.verifier.collect[0].service=="sim"
            assert not services["sim"].get("ports") and not services["sim"].get("expose")
            assert not list((directory/"environment").glob("runtime.tar.gz"))
            assert (directory/"environment/topogym_client.py").is_file()
        source=json.loads((directory/"tests/source-manifest.json").read_text())
        if (directory/"source-manifest.json").exists():
            assert json.loads((directory/"source-manifest.json").read_text())==source,"Source manifests differ"
        for bundle in directory.rglob("runtime.tar.gz"):
            checksum=hashlib.sha256(bundle.read_bytes()).hexdigest()
            if checksum not in bundle_cache:
                found={}
                with tarfile.open(bundle) as archive:
                    for member in archive:
                        assert member.isfile() and not Path(member.name).is_absolute() and ".." not in Path(member.name).parts
                        assert not set(Path(member.name).parts)&{"planning","agents","legacy","deferred","rollout_simulation"}
                        contents=archive.extractfile(member).read()
                        if member.name.endswith(".py"):
                            compile(contents,member.name,"exec")
                        assert b"from robot_coding_bench" not in contents and b"import harbor_runners" not in contents
                        found[member.name]=hashlib.sha256(contents).hexdigest()
                bundle_cache[checksum]=found
            assert bundle_cache[checksum]==source,"Runtime differs from frozen source manifest"
        for instance_file in directory.rglob("instance.json"):
            instance=json.loads(instance_file.read_text())
            assert instance["source_sha256"]==digest(source)
            assert instance["simulator"]["max_physics_steps"] is None
            assert instance["simulator"]["history_storage"]=="disk"
        content_hash,_=Packager.compute_content_hash(directory)
        assert "sha256:"+content_hash==row.digest,"Task digest changed after export"
    return dict(tasks=len(dataset.tasks),runtime_bundles=len(bundle_cache),status="passed")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    print(json.dumps(check(parser.parse_args().root),indent=2))
