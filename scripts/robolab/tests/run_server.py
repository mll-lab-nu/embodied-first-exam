"""Run a benchmark's real environment/sim/server.py on the fake simulator: argv = server.py, stub dir, layer dir."""
import os, runpy, sys
sys.dont_write_bytecode = True
server, stub, layer = sys.argv[1:4]
sys.path[:0] = [stub, os.path.dirname(stub), layer]
import types
try:
    import imageio.v2  # noqa: F401
except ImportError:                      # this host's python has no imageio: a stand-in encoder (the test is not about mp4 bytes)
    class _W:
        def __init__(self, path, **kw): self.f = open(path, "wb")
        def append_data(self, fr): self.f.write(b"frame")
        def __enter__(self): return self
        def __exit__(self, *a): self.f.close()
    v2 = types.ModuleType("imageio.v2"); v2.get_writer = lambda path, **kw: _W(path, **kw)
    pkg = types.ModuleType("imageio"); pkg.v2 = v2; sys.modules["imageio"] = pkg; sys.modules["imageio.v2"] = v2
import rcb_limited as L
_serve = L.serve
L.serve = lambda svc, port=8000: _serve(svc, port=int(os.environ["TEST_PORT"]))
runpy.run_path(server, run_name="__main__")
