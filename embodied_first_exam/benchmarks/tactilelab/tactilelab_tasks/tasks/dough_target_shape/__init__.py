try:
    from .policy import DoughTargetShapePolicy  # noqa: F401
except ImportError:  # not part of this copy
    pass
from .task import DoughTargetShapeTask  # noqa: F401
