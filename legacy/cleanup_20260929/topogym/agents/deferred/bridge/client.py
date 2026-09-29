"""Small transport client reusable by any coding-agent harness."""
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class Client:
    def __init__(self, base_url="http://127.0.0.1:8765"):
        self.base_url = base_url.rstrip("/")

    def request(self, path, payload=None, *, raw=False):
        if self.base_url.startswith("local://"):
            return self._local_request(path, payload, raw=raw)
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        request = Request(self.base_url+path, data=data,
                          headers={"Content-Type": "application/json", "X-TopoGym": "1"})
        try:
            with urlopen(request, timeout=3600) as response:
                content = response.read()
        except HTTPError as exc:
            raise ValueError(exc.read().decode()) from exc
        return content if raw else json.loads(content)

    def _local_request(self, path, payload, *, raw):
        """Standalone file RPC; a stopped owner is never restarted or restored."""
        import base64
        import os
        from pathlib import Path
        import time
        import uuid
        root = Path(self.base_url[len("local://"):])
        owner_path = root/"owner.json"

        def alive():
            try:
                owner = json.loads(owner_path.read_text())
                if owner.get("state") == "stopped":
                    return False
                independent = root/"heartbeat.json"
                if independent.exists():
                    pulse = json.loads(independent.read_text())
                    if (pulse.get("pid"), pulse.get("starttime")) == (owner["pid"], owner["starttime"]):
                        return pulse["alive"] and time.time()-pulse["heartbeat"] < 60
                # IDE tools may live in a different PID namespace from the
                # operator's worker. Shared-file heartbeat is the portable check.
                if "heartbeat" in owner:
                    return time.time()-owner["heartbeat"] < 60
                os.kill(owner["pid"], 0)
                stat = Path(f"/proc/{owner['pid']}/stat")
                return not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[19] == owner["starttime"]
            except (OSError, KeyError, ValueError):
                return False

        if not alive():
            raise ValueError("Local simulator process is unavailable; no automatic restart/rollback. Inspect the operator log.")
        request_id = uuid.uuid4().hex
        request = dict(path=path, payload=payload, raw=raw)
        temp = root/"inbox"/(request_id+".tmp")
        temp.write_text(json.dumps(request, allow_nan=False))
        temp.replace(temp.with_suffix(".json"))
        response = root/"outbox"/(request_id+".json")
        deadline = time.monotonic()+3600
        while not response.exists():
            if not alive():
                # Recheck the response after observing shutdown.
                if response.exists():
                    break
                raise ValueError("Local simulator stopped; action outcome may be unknown. Never restart this episode.")
            if time.monotonic() > deadline:
                raise TimeoutError("Local request timed out; retry actions only with the SAME request-id and code")
            time.sleep(.05)
        result = json.loads(response.read_text())
        response.unlink()
        if "error" in result:
            raise ValueError(result["error"])
        return base64.b64decode(result["bytes"]) if raw else result["result"]

    def state(self):
        return self.request("/v1/session")

    def submit(self, code, *, request_id, expected_segment, call_id=None):
        return self.request("/v1/segments", dict(code=code, request_id=request_id,
            expected_segment=expected_segment, call_id=call_id))


def main(argv=None):
    """Standalone solver CLI; this file can be copied without the repository."""
    import argparse
    from pathlib import Path, PurePosixPath
    import re
    from urllib.parse import quote
    import uuid

    parser = argparse.ArgumentParser(description="Read observations and submit irreversible action scripts")
    parser.add_argument("--url", help="Defaults to bridge_config.json beside this file, then localhost:8765")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("brief", help="Read this package's task brief and policy without contacting the environment")
    commands.add_parser("status")
    observe = commands.add_parser("observe")
    observe.add_argument("--all-frames", action="store_true", help="Download every frame of the latest segment")
    fetch = commands.add_parser("fetch")
    fetch.add_argument("path", help="Public artifact path from a manifest")
    submit = commands.add_parser("submit")
    submit.add_argument("policy", type=Path)
    submit.add_argument("--expected-segment", type=int, required=True)
    submit.add_argument("--request-id", required=True)
    submit.add_argument("--call-id", help="Finalized usage receipt for metered mode")
    retry = commands.add_parser("retry")
    retry.add_argument("--request-id", required=True)
    stop = commands.add_parser("stop")
    stop.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    config_path = Path(__file__).with_name("bridge_config.json")
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    client = Client(args.url or config.get("url", "http://127.0.0.1:8765"))

    def local_brief():
        root = config_path.parent.resolve()
        files = {}
        for key in ("task_spec", "task_brief", "solver_instructions"):
            if key in config:
                path = (root/config[key]).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("Task brief path escapes package")
                files[key] = path
        return files

    def save_json(path, value):
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n")

    def download(relative):
        parts = PurePosixPath(relative).parts
        if not parts or PurePosixPath(relative).is_absolute() or ".." in parts:
            raise ValueError("Expected a relative public artifact path")
        if parts[0] == "public_assets" and PurePosixPath(relative).suffix not in (".json", ".md"):
            raise ValueError("Reference images/geometry are not task inputs; use this episode's camera frames")
        data = client.request("/artifacts/"+quote(relative, safe="/"), raw=True)
        root = Path("feedback").resolve()
        target = root.joinpath(*parts).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Local artifact path escapes feedback directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return str(target)

    if args.command == "brief":
        files = local_brief()
        result = dict(config=config, files={k: str(v) for k, v in files.items()})
        if "task_spec" in files:
            result["task"] = json.loads(files["task_spec"].read_text())
    elif args.command == "status":
        result = client.state()
    elif args.command == "observe":
        state = client.state()
        if state["task"].get("goal_reference"):
            raise ValueError("Legacy server exposes object reference data; ask the operator for a fresh run with the current adapter")
        prompt = client.request("/v1/prompt")["prompt"]
        server_prompt = prompt
        if config.get("task_id", state["task"]["task_id"]) != state["task"]["task_id"]:
            raise ValueError("Package task_id does not match the server")
        if "tool_policy" in config and "tool_policy" in state and config["tool_policy"] != state["tool_policy"]:
            raise ValueError("Package/server tool policies differ; ask the operator to align the package before solving")
        files = local_brief()
        # Existing completed v1 episodes stay immutable. A later public brief is
        # clearly labelled, and never masquerades as an original server prompt.
        if config.get("post_run_supplement") and "task_spec" in files and state["task"].get("task_spec_version", 1) < 3:
            spec = json.loads(files["task_spec"].read_text())
            if spec["objective"] != state["task"].get("objective"):
                raise ValueError("Package objective does not match the server")
            prompt = ("POST-RUN TASK BRIEF SUPPLEMENT: not part of the original trial input. "
                      "This does not reopen a terminal episode. Follow current SOLVER_INSTRUCTIONS.md.\n"
                      + json.dumps(dict(task=spec, tool_policy=config.get("tool_policy")), ensure_ascii=False)
                      + "\nOriginal server prompt follows (manual ledger balances are not measured usage):\n"+prompt)
        folder = Path("observations")/str(uuid.uuid4())
        folder.mkdir(parents=True)
        save_json(folder/"session.json", state)
        (folder/"prompt.txt").write_text(prompt, encoding="utf-8")
        if prompt != server_prompt:
            (folder/"server_prompt.txt").write_text(server_prompt, encoding="utf-8")
        manifest_path = download(state["latest_manifest"])
        manifest = json.loads(Path(manifest_path).read_text())
        frames = manifest["frames"] if args.all_frames else manifest["frames"][-1:]
        downloaded = [download(item["path"]) for frame in frames for item in frame["cameras"].values()]
        assets = [download(item["path"]) for item in state["task"].get("public_assets", [])]
        result = dict(state=state["state"], tick=state["tick"], expected_segment=state["next_segment"],
                      prompt=str((folder/"prompt.txt").resolve()), manifest=manifest_path, images=downloaded,
                      budget=state["budget"], task_assets=assets,
                      task_brief={k: str(v) for k, v in files.items()},
                      tool_policy=state.get("tool_policy", config.get("tool_policy")))
    elif args.command == "fetch":
        result = dict(path=download(args.path))
    elif args.command in ("submit", "retry"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", args.request_id):
            raise ValueError("request-id must contain 1..100 letters, digits, underscores or hyphens")
        folder = Path("requests")
        folder.mkdir(exist_ok=True)
        path = folder/(args.request_id+".json")
        if args.command == "submit":
            request = dict(request_id=args.request_id, expected_segment=args.expected_segment,
                           code=args.policy.read_text(encoding="utf-8"), call_id=args.call_id)
            if path.exists():
                if json.loads(path.read_text()) != request:
                    raise ValueError("This request-id is already bound to different code or metadata")
            else:
                with path.open("x", encoding="utf-8") as stream:
                    json.dump(request, stream, indent=2, ensure_ascii=False)
        else:
            request = json.loads(path.read_text())
        # Persist before sending; a lost response can be retried with exact content.
        result = client.request("/v1/segments", request)
        save_json(folder/(args.request_id+".result.json"), result)
    else:
        result = client.request("/v1/finish", dict(reason=args.reason))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
