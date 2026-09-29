"""Agent CLI. A wait timeout never cancels an accepted request."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
from uuid import uuid4

from .protocol import API_VERSION, SOCKET, dumps, loads, receive, send


def call(message, socket_path=SOCKET):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(10)
        connection.connect(str(socket_path))
        with connection.makefile("rwb") as stream:
            send(stream, {"api_version": API_VERSION, **message})
            return receive(stream)


def check_initial(state, *, check_rgb=True):
    if state.get("phase") not in {"ready", "executing", "terminal"}:
        raise ValueError("Session is not ready")
    spec = loads(Path(state["spec_path"]).read_bytes())
    initial = loads(Path(state["initial_path"]).read_bytes())
    manifest = loads(Path(state["artifacts_manifest"]).read_bytes())["artifacts"]
    if initial["segment_id"] != 0 or initial["episode_id"] != state["episode_id"]:
        raise ValueError("Initial episode mismatch")
    videos = initial["media"]["videos"]
    if not initial["evidence_complete"] or initial["status"] != "complete":
        raise ValueError("Initial evidence is incomplete")
    if check_rgb and (not videos or set(videos) - {"combined"} != set(spec["observation_spec"]["rgb"])):
        raise ValueError("Initial video is missing")
    descriptors = [*videos.values(), *initial["logs"].values()]
    if videos:
        descriptors.append(initial["media"]["frame_map"])
    for descriptor in descriptors:
        artifact = manifest[descriptor["artifact_id"]]
        path = Path(artifact["path"])
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if path.stat().st_size != descriptor["size_bytes"] or digest.hexdigest() != descriptor["sha256"]:
            raise ValueError("Initial artifact integrity failure")
    return state


def wait_result(receipt, timeout, socket_path=SOCKET):
    end = time.monotonic() + timeout
    while receipt.get("request_status") in {"accepted", "running", "publishing"}:
        if time.monotonic() >= end:
            raise TimeoutError(receipt["request_id"])
        time.sleep(.2)
        receipt = call({"operation": "result", "request_id": receipt["request_id"]}, socket_path)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default=SOCKET)
    parser.add_argument("--public-root", type=Path, default=Path("/rollout"))
    sub = parser.add_subparsers(dest="command", required=True)
    ready = sub.add_parser("ready")
    ready.add_argument("--check-initial", action="store_true")
    sub.add_parser("status")
    sub.add_parser("history")
    logs = sub.add_parser("logs")
    logs.add_argument("--segment", type=int, required=True)
    logs.add_argument("--kind", choices=["steps", "events", "frames"], default="steps")
    logs.add_argument("--start", type=int, default=0)
    logs.add_argument("--limit", type=int, default=20)
    for name in ("video", "frames"):
        command = sub.add_parser(name)
        command.add_argument("--segment", type=int, required=True)
        command.add_argument("--camera", default="combined")
        if name == "frames":
            command.add_argument("--frame-index", type=int, nargs="+")
            command.add_argument("--output", type=Path, required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("file", type=Path)
    submit.add_argument("--params", type=Path)
    submit.add_argument("--request-id", default=None)
    result = sub.add_parser("result")
    result.add_argument("--request-id", required=True)
    for command in (submit, result):
        command.add_argument("--wait", action="store_true")
        command.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args(argv)
    try:
        if args.command in {"history", "logs", "video", "frames"}:
            from .history import HistoryReader
            reader = HistoryReader(args.public_root)
            if args.command == "history":
                answer = reader.index()
            elif args.command == "logs":
                answer = reader.page(args.segment, args.kind, args.start, args.limit)
            elif args.command == "video":
                answer = reader.video(args.segment, args.camera)
            else:
                answer = reader.frames(args.segment, args.camera, args.frame_index, args.output)
        elif args.command in {"ready", "status"}:
            answer = call({"operation": "status"}, args.socket)
            if args.command == "ready":
                check_initial(answer, check_rgb=args.check_initial)
        elif args.command == "submit":
            state = call({"operation": "status"}, args.socket)
            identifier = args.request_id or uuid4().hex
            answer = call(dict(operation="submit_policy", episode_id=state["episode_id"],
                request_id=identifier, policy=dict(source_utf8=args.file.read_text(),
                    filename=args.file.name, factory="create_policy",
                    parameters=loads(args.params.read_bytes()) if args.params else {})), args.socket)
        else:
            answer = call({"operation": "result", "request_id": args.request_id}, args.socket)
        if getattr(args, "wait", False):
            answer = wait_result(answer, args.timeout, args.socket)
        print(dumps(answer))
        return 2 if answer.get("request_status") == "rejected" else 1 if answer.get("request_status") == "error" else 0
    except TimeoutError as error:
        print(dumps({"error": "wait_timeout", "request_id": str(error)}))
        return 3
    except (OSError, ValueError, KeyError, EOFError) as error:
        print(dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
