"""Model server, from the repository root in the model environment:

    vla/.envs/<model>/bin/python -m vla.models.serve --config vla/configs/models/<name>.yaml

Loads ``class_path`` and serves one evaluation client at a time over TCP. A model error is sent back as an
``error`` message and the server keeps running; after a client disconnects it waits for the next one.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from multiprocessing.connection import Listener
import traceback

from omegaconf import OmegaConf

from vla.models.base import load_model
from vla.protocol import Observation, decode, encode


def reply(model, data):
    """The encoded answer to one request; any failure, including an unencodable result, becomes an error."""
    try:
        msg = decode(data)
        kind = msg.pop("type")
        if kind == "reset":
            model.reset(msg["seed"])
            return encode({"type": "ok"})
        if kind == "infer":
            return encode({"type": "chunk", "actions": model.infer(Observation(**msg)).actions})
        raise ValueError(f"Unknown message type: {kind}")
    except Exception:
        return encode({"type": "error", "message": traceback.format_exc()})


def serve(model, address):
    with Listener(address) as listener:
        print(f"Serving {model.spec.name} on {listener.address}", flush=True)
        while True:
            with listener.accept() as conn:
                print(f"Client connected: {listener.last_accepted}", flush=True)
                try:
                    conn.send_bytes(encode({"type": "spec", **asdict(model.spec)}))
                    while True:
                        conn.send_bytes(reply(model, conn.recv_bytes()))
                except (EOFError, OSError):
                    print("Client disconnected", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="model config (vla/configs/models/*.yaml)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, help="defaults to the config's port")
    args = parser.parse_args()
    config = OmegaConf.load(args.config)
    serve(load_model(config), (args.host, args.port or config.port))


if __name__ == "__main__":
    main()
