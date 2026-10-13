#!/usr/bin/env python3
"""eai-policy/1.0 trust boundary and copied tooling checks (PROTOCOL §4p)."""

import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts/quadrotor_landing"
PUBLIC = ("model.py", "policy.py", "nominal.py", "client.py")
BASE = next(
    line.split("=", 1)[1]
    for line in (ROOT / "scripts/eai_standard/client.env").read_text().splitlines()
    if line.startswith("CLIENT_IMAGE=")
)


def check(task):
    data = tomllib.loads((task / "task.toml").read_text())
    meta = data["metadata"]
    if not (
        meta.get("task_type") == "policy"
        or meta.get("protocol") == "eai-policy/1.0"
        or task.name.startswith("quadrotor-landing-")
    ):
        return []
    errors = []

    def require(ok, message):
        if not ok:
            errors.append(message)

    require(
        meta.get("task_type") == "policy"
        and meta.get("mode") == "standard"
        and meta.get("protocol") == "eai-policy/1.0",
        "policy task must declare standard policy / eai-policy/1.0",
    )
    expected = {f"scripts/quadrotor_landing/public/{name}": (SRC / "public" / name).read_bytes() for name in PUBLIC}
    expected.update(
        {
            p: b""
            for p in (
                "scripts/__init__.py",
                "scripts/quadrotor_landing/__init__.py",
                "scripts/quadrotor_landing/public/__init__.py",
            )
        }
    )
    public = task / "environment/public"
    actual = {str(p.relative_to(public)): p.read_bytes() for p in public.rglob("*") if p.is_file()}
    require(
        actual == expected and not any(p.is_symlink() for p in public.rglob("*")),
        "public payload differs from nominal-only allowlist",
    )
    for sub in ("environment", "tests"):
        docker = (task / sub / "Dockerfile").read_text()
        require(
            re.findall(r"^\s*FROM\s+(\S+)", docker, re.M | re.I) == [BASE],
            "policy client/verifier must use pinned client base",
        )
    compose = (task / "environment/docker-compose.yaml").read_text()
    main = re.search(r"(?ms)^  main:\n(.*?)(?=^  [A-Za-z_]|\Z)", compose)
    main = main.group(1) if main else ""
    require(
        "    healthcheck:" in main
        and "http://127.0.0.1:8000/health" in main
        and "start_period: 1800s" in main
        and "    depends_on:" not in main,
        "policy client must start for monitoring and health-gate the agent on calibration",
    )
    docker = (task / "environment/Dockerfile").read_text()
    require(
        re.findall(r"^\s*(?:COPY|ADD)\s+(.+)", docker, re.M | re.I)
        == ["nominal-requirements.txt /tmp/nominal-requirements.txt", "public/scripts /app/scripts"],
        "agent COPY sources must contain only nominal public tooling",
    )
    require(
        (task / "environment/nominal-requirements.txt").read_bytes() == (SRC / "requirements.txt").read_bytes(),
        "nominal dependency pins differ",
    )
    require(
        (task / "tests/grade.py").read_bytes() == (SRC / "native/verify.py").read_bytes(),
        "policy verifier identity differs",
    )
    for part in ("trusted", "native"):
        for p in (SRC / part).glob("*.py"):
            dst = task / "environment/sim/scripts/quadrotor_landing" / part / p.name
            require(dst.is_file() and dst.read_bytes() == p.read_bytes(), "private tooling identity differs: " + p.name)
    a, b = task / "environment/sim/instance.json", task / "tests/instance.json"
    require(
        a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes(), "policy instance copies differ or are missing"
    )
    if a.is_file():
        instance = json.loads(a.read_text())
        bank = instance["bank"]
        require(
            len(bank["adaptation"]) == 3 and len(bank["held_out"]) == 6,
            "policy requires three adaptation and six held-out cases",
        )
        seeds = [r["seed"] for rows in bank.values() for r in rows]
        require(len(set(seeds)) == 9, "case banks must be disjoint")
    artifacts = data.get("artifacts", [])
    require({"source": "/data/", "service": "sim"} in artifacts, "policy evidence must be collected from sim /data/")
    for a in artifacts:
        source = a if isinstance(a, str) else a.get("source", "")
        if source.rstrip("/") == "/data" or source.startswith("/data/"):
            require(
                isinstance(a, dict) and a.get("service") == "sim", "private evidence cannot be collected from the agent"
            )
    hooks = data.get("verifier", {}).get("collect", [])
    require(
        any(
            h.get("service") == "sim" and h.get("command") == "python -m scripts.quadrotor_landing.native.collect"
            for h in hooks
        ),
        "policy trusted collect hook missing",
    )
    return errors


def main():
    bad = []
    tasks = [Path(p) for p in sys.argv[1:]] or sorted((ROOT / "tasks").glob("*"))
    for task in tasks:
        if (task / "task.toml").is_file():
            try:
                bad.extend(f"FAIL {task.name}: {msg}" for msg in check(task))
            except (OSError, KeyError, ValueError, TypeError) as error:
                bad.append(f"FAIL {task.name}: invalid policy package ({error})")
    print("\n".join(bad) if bad else "ok policy task contract")
    return int(bool(bad))


if __name__ == "__main__":
    sys.exit(main())
