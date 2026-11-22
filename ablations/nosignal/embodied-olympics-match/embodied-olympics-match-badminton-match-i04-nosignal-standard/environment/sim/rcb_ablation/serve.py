"""python -m rcb_ablation.serve (cwd /srv): core.serve's main() with the ablation's service class and HTTP layer."""
import core.serve as S

from . import ANY, OPS
from . import httpx
from . import platform_ops
from . import service

if OPS:
    platform_ops.install()          # a core with platform seats: the opponent's program can be saved and replaced
if ANY:
    S.RealtimeService = service.make(S.RealtimeService)
    S.TurnService = service.make(S.TurnService)
    _make_server = S.make_server

    def make_server(svc, seats, hosts, port=8000):
        return httpx.patch(_make_server(svc, seats, hosts, port), svc, seats)

    S.make_server = make_server
    if hasattr(S, "builtin_seat"):
        service.patch_builtin(S.builtin_seat)

if __name__ == "__main__":
    S.main()
