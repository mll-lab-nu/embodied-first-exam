"""python -m topogym.agent_bridge --output runs/agent_bridge/my_episode"""
import argparse

from .registry import TASKS, factory_for
from .server import BridgeServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New directory; existing directories are rejected")
    parser.add_argument("--task", choices=TASKS, default="counter")
    parser.add_argument("--factory", help="Trusted custom adapter factory: package.module:function(asset_dir)")
    parser.add_argument("--mode", choices=("manual", "metered"), default="manual")
    parser.add_argument("--token-limit", type=int, default=2_000_000)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--renderer", choices=("nyx", "rasterizer"), default="nyx")
    parser.add_argument("--objective", choices=("assemble", "disassemble"), default="assemble")
    parser.add_argument("--allow-internet", action=argparse.BooleanOptionalAction, default=True,
                        help="Declare solver internet permission (default on); enforced by the host harness")
    args = parser.parse_args()
    factory = factory_for(args.task, args.backend, args.renderer, args.factory, objective=args.objective)
    server = BridgeServer(("127.0.0.1", args.port), factory, args.output,
        token_limit=args.token_limit, mode=args.mode, max_steps=args.max_steps, allow_internet=args.allow_internet)
    print(f"TopoGym agent bridge: http://127.0.0.1:{server.server_port}\nArtifacts: {server.session.root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
