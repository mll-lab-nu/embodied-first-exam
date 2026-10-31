try:
    from .policy import ClothEdgeFeedPolicy
except ImportError:  # not part of this copy
    pass
from .task import ClothEdgeFeedTask

__all__ = ["ClothEdgeFeedTask", "ClothEdgeFeedPolicy"]
