"""Entry point of the Newton sidecar; run by the Newton interpreter, started by ``tactilelab_tasks.backends.newton_client``::

    <newton python> sidecar/server.py --address /path/to/unix.sock [--shm-dir DIR] [--path DIR ...] [--module DOTTED ...]

``--path`` / ``--module`` preload additional service modules (same as the client's ``load``); the three built-in services
(``softbody.world``, ``mpm.dough``, ``fem.plugpad``, plus ``fem.plug``) are registered by ``sidecar.services`` at start.

Import layout: the repository root goes on ``sys.path`` so ``sidecar.*`` imports as a package, and ``tactilelab_tasks/`` goes on
``sys.path`` so the shared pure-numpy package imports as the top-level ``softbody_geom`` without executing
``tactilelab_tasks/__init__.py`` (which belongs to the Isaac side).
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent  # .../sidecar
REPO = HERE.parent


def _exit_with_parent(period: float = 2.0) -> None:
    """Exit when the client process is gone (also while a long call is running, which would not notice the closed socket
    until it tries to reply).  A watchdog thread instead of ``PR_SET_PDEATHSIG``: no ``preexec_fn`` is needed in the
    multi-threaded simulator process that starts us."""
    parent = os.getppid()

    def watch() -> None:
        while True:
            time.sleep(period)
            if os.getppid() != parent:
                os._exit(0)

    threading.Thread(target=watch, daemon=True, name="parent-watchdog").start()


def setup_path() -> None:
    """``sidecar`` importable as a package, ``softbody_geom`` importable as a top-level package."""
    if sys.path and Path(sys.path[0]).resolve() == HERE:  # the script's own dir would shadow top-level names
        sys.path.pop(0)
    for p in (str(REPO), str(REPO / "tactilelab_tasks")):
        if p not in sys.path:
            sys.path.insert(0, p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True)
    ap.add_argument(
        "--shm-dir", default=None, help="directory of the shared-memory arenas (omit: arrays go through the socket)"
    )
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--module", action="append", default=[])
    ap.add_argument(
        "--no-builtin", action="store_true", help="do not preload sidecar.services (tests of the bare bridge)"
    )
    args = ap.parse_args()
    setup_path()
    from sidecar import host  # noqa: PLC0415

    _exit_with_parent()
    modules = list(args.module)
    if not args.no_builtin:
        modules.insert(0, "sidecar.services")
    host.load_modules(args.path, modules)
    print(f"[newton-host] python {sys.version.split()[0]}, serving {args.address}", flush=True)
    host.serve_socket(args.address, args.shm_dir)
    print("[newton-host] bye", flush=True)


if __name__ == "__main__":
    main()
