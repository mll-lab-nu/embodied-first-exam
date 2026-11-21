"""Reference solution of a standard-mcp task: with EFE_MCP_ORACLE=1 (solution/solve.sh), `import rcb_client` gives
rcb_client_mcp (the same Robot API through the efe-robot MCP tools) and `import ro_client` (an Embodied Olympics
match's seat client) the task's own ro_client with its calls sent through the tools (ro_client_mcp), whatever
sys.path the oracle sets up."""
import importlib.abc
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHIMS = {"rcb_client": "rcb_client_mcp.py", "ro_client": "ro_client_mcp.py"}


class _ShimFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Loads the shim module the first time the client is imported (then it is in sys.modules)."""

    def find_spec(self, name, path=None, target=None):
        if name in SHIMS and os.path.isfile(os.path.join(HERE, SHIMS[name])):
            return importlib.util.spec_from_loader(name, self)
        return None

    def create_module(self, spec):
        shim = importlib.util.spec_from_file_location(SHIMS[spec.name][:-3], os.path.join(HERE, SHIMS[spec.name]))
        mod = importlib.util.module_from_spec(shim)
        shim.loader.exec_module(mod)
        return getattr(mod, "real", mod)       # ro_client_mcp patches and exports the task's own module

    def exec_module(self, module):
        pass


if os.environ.get("EFE_MCP_ORACLE") == "1":
    sys.meta_path.insert(0, _ShimFinder())
