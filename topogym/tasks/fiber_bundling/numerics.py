"""Explicit solver selection, separate from cable material parameters."""


def constraint_solver_name(task):
    name=str(task.get("numerics",{}).get("constraint_solver","Newton"))
    if name not in ("Newton","CG"):
        raise ValueError(f"Unsupported constraint solver: {name}")
    return name


def require_solver_evidence(task,gate):
    name=constraint_solver_name(task)
    if gate.get("constraint_solver","Newton") != name:
        raise RuntimeError("Stability evidence must match the constraint solver")
    return name
