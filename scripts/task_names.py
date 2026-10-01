"""Task names across protocol versions: jobs run before protocol v1.0 used `<task>` (privileged) and `<task>-limited`
(standard); since v1.0 every task directory ends in `-privileged` or `-standard` (docs/PROTOCOL.md §2.2)."""


def canonical(name: str) -> str:
    """The v1.0 directory name of a task name from any protocol version."""
    if name.endswith(("-privileged", "-standard")):
        return name
    if name.endswith("-limited"):
        return name[: -len("-limited")] + "-standard"
    return name + "-privileged"


def base(name: str) -> str:
    """The name without its mode suffix."""
    n = canonical(name)
    return n.rsplit("-", 1)[0]


def is_standard(name: str) -> bool:
    return canonical(name).endswith("-standard")
