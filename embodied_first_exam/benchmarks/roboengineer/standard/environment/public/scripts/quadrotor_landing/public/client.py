"""Agent CLI. Only accesses the deployment service's public operations."""

import argparse
import json
import os
from pathlib import Path
import urllib.request
from .policy import load


def call(operation, arguments, url=None):
    base = url or os.environ.get("LANDING_SERVICE_URL", "http://sim:8000")
    request = urllib.request.Request(
        base + "/" + operation, json.dumps(arguments, allow_nan=False).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=600) as r:
        return json.load(r)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("operation", choices=["describe", "deploy", "seal"])
    p.add_argument("--policy", type=Path)
    p.add_argument("--round-id")
    p.add_argument("--note", default="")
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    arguments = (
        {}
        if a.operation == "describe"
        else {"policy": load(a.policy), "diagnosis": a.note}
        if a.operation == "deploy"
        else {"round_id": a.round_id, "summary": a.note}
    )
    result = call(a.operation, arguments)
    if a.out:
        a.out.write_text(json.dumps(result))
    else:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
