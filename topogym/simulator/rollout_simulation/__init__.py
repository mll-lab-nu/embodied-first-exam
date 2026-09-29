"""Local policy/segment execution; importing this package has no runtime effects."""

__all__ = ["SegmentRunner"]


def __getattr__(name):
    if name == "SegmentRunner":
        from .segment import SegmentRunner
        return SegmentRunner
    raise AttributeError(name)
