"""The Newton sidecar: a separate Python 3.12 process that runs Newton (warp >= 1.17) for the soft, dough and FEM tasks.

``protocol.py`` (wire format) and ``host.py`` (service loop) need only the standard library and numpy; ``services.py`` and
``worlds/`` import ``newton`` / ``warp`` lazily and run in the sidecar interpreter only.  The Isaac side talks to the sidecar
through ``tactilelab_tasks.backends.newton_client``.
"""
