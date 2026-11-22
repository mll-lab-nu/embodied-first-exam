"""The sim container's entry in an ablation's standard task dir: core/lockstep.py unchanged, its service class with the
ablation's routes (rcb_ablation/service.py) and the ablation's HTTP layer and seats (rcb_ablation/serve.py, which
patches core/serve.py's server, the platform seats and the built-in seats as for core/launch.py)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))         # /srv: core/ and rcb_ablation/
sys.path.insert(0, ROOT)


if __name__ == "__main__":
    import core.lockstep as L
    from rcb_ablation import ANY, service
    import rcb_ablation.serve  # noqa: F401  (patches core.serve: make_server, platform and built-in seats)
    if ANY:
        L.LockstepService = service.make(L.LockstepService)   # core.lockstep.main() builds this class
    L.main()
