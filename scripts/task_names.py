"""Task names across protocol versions: jobs run before protocol v1.0 used `<task>` (privileged) and `<task>-limited`
(standard); since v1.0 every task directory ends in its mode, `-privileged` or `-standard`, and since v1.1 also
`-standard-realtime` (docs/PROTOCOL.md §2.2, D12). A mode is recognised by its whole suffix only."""

MODES = ("standard-realtime", "privileged", "standard")   # longest suffix first


def mode(name: str) -> str:
    """privileged, standard or standard-realtime."""
    n = canonical(name)
    return next(m for m in MODES if n.endswith(f"-{m}"))


def canonical(name: str) -> str:
    """The v1.x directory name of a task name from any protocol version."""
    if name.endswith(tuple(f"-{m}" for m in MODES)):
        return name
    if name.endswith("-limited"):
        return name[: -len("-limited")] + "-standard"
    return name + "-privileged"


def base(name: str) -> str:
    """The name without its mode suffix."""
    n = canonical(name)
    return n[: -len(mode(n)) - 1]


def is_standard(name: str) -> bool:
    return mode(name) == "standard"


def is_standard_realtime(name: str) -> bool:
    return mode(name) == "standard-realtime"
