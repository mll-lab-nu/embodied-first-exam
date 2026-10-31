"""Task sub-packages (one directory per task: cfg.yaml, task.py, policy.py).

Importing this package registers nothing by itself: the registry ``tactilelab_tasks.TASKS``
is filled lazily by ``tactilelab_tasks/__init__.py`` so that no simulator is imported here.
"""
