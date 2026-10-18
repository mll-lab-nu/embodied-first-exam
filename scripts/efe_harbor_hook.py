"""Loaded at interpreter start by efe-harbor.pth (installed with this repo: `uv tool install --force -e .`): when
Harbor's CLI module is imported, its `app` is wrapped so that `harbor run` takes --core / --all / --privileged /
--standard / --standard-realtime (scripts/efe.py). Harbor's own options and subcommands are unchanged."""
import importlib.abc, importlib.machinery, sys


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name != "harbor.cli.main":
            return None
        sys.meta_path.remove(self)
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None:
            return spec
        exec_module = spec.loader.exec_module

        def wrapped(module):
            exec_module(module)
            app = module.app

            def harbor_app(*a, **kw):
                if not a and not kw and sys.argv[1:2] == ["run"]:
                    import efe
                    return efe.run(sys.argv[2:], app=app)
                return app(*a, **kw)
            harbor_app.__wrapped_app__ = app
            module.app = harbor_app
        spec.loader.exec_module = wrapped
        return spec


if not any(isinstance(f, _Finder) for f in sys.meta_path):
    sys.meta_path.insert(0, _Finder())
