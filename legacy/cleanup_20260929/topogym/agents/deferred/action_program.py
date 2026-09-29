"""A bounded Python action-script subset, interpreted without exec/eval.

The script plans a whole segment from its starting observation. It can use
assignments, for/range, numeric arithmetic, lists/dicts/indexing and env.step.
Arbitrary Python belongs in the external harness, which submits this subset.
"""
import ast
import copy
import math
import operator


class PolicyError(ValueError):
    pass


def integer(value, name, minimum=0, maximum=2_000_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def compile_policy(source, observation, max_steps=1000):
    if not isinstance(source, str) or not 1 <= len(source.encode()) <= 65_536:
        raise PolicyError("code must contain 1..65536 bytes")
    try:
        tree = ast.parse(source)
    except (SyntaxError, RecursionError) as exc:
        raise PolicyError(str(exc)) from exc
    if sum(1 for _ in ast.walk(tree)) > 8000:
        raise PolicyError("Script is too complex")
    # Validate even dead loop bodies; forbidden syntax never passes silently.
    allowed = (ast.Module, ast.Assign, ast.For, ast.Expr, ast.Name, ast.Load,
               ast.Store, ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Subscript,
               ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
               ast.USub, ast.UAdd, ast.Call, ast.Attribute, ast.keyword)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise PolicyError(f"Unsupported syntax: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and not (
            isinstance(node.value, ast.Name) and node.value.id == "env" and node.attr == "step"
        ):
            raise PolicyError("Only env.step is available")
    variables = {"obs": copy.deepcopy(observation)}
    actions, fuel = [], 100_000

    def spend():
        nonlocal fuel
        fuel -= 1
        if fuel < 0:
            raise PolicyError("Script computation limit exceeded")

    def expr(node, depth=0):
        spend()
        if depth > 64:
            raise PolicyError("Expression nesting limit exceeded")
        sub = lambda n: expr(n, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (str, int, float, bool, type(None)):
            return node.value
        if isinstance(node, ast.Name) and node.id in variables:
            return variables[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            return [sub(n) for n in node.elts]
        if isinstance(node, ast.Dict) and all(k is not None for k in node.keys):
            return {sub(k): sub(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.Subscript):
            return sub(node.value)[sub(node.slice)]
        if isinstance(node, (ast.BinOp, ast.UnaryOp)):
            values = [sub(node.left), sub(node.right)] if isinstance(node, ast.BinOp) else [sub(node.operand)]
            if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e12 for v in values):
                raise PolicyError("Arithmetic requires bounded finite numbers")
            ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                   ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos}
            result = ops[type(node.op)](*values)
            if not math.isfinite(result) or abs(result) > 1e12:
                raise PolicyError("Arithmetic result exceeds limits")
            return result
        raise PolicyError(f"Unsupported expression: {type(node).__name__}")

    def assign(target, value):
        if not isinstance(target, ast.Name) or target.id in ("env", "obs", "range") or target.id.startswith("_"):
            raise PolicyError("Assign only to ordinary local variable names")
        variables[target.id] = value

    def block(nodes, depth=0):
        if depth > 32:
            raise PolicyError("Loop nesting limit exceeded")
        for node in nodes:
            spend()
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                assign(node.targets[0], expr(node.value))
            elif isinstance(node, ast.For) and not node.orelse:
                call = node.iter
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                        and call.func.id == "range" and not call.keywords and 1 <= len(call.args) <= 3):
                    raise PolicyError("Loops must use range(start, stop, step)")
                args = [expr(n) for n in call.args]
                if any(type(n) is not int or abs(n) > 100_000 for n in args):
                    raise PolicyError("range bounds must be integers within 100000")
                for n in range(*args):
                    spend()
                    assign(node.target, n)
                    block(node.body, depth + 1)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if not (isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                        and call.func.value.id == "env" and call.func.attr == "step"
                        and len(call.args) == 1 and len(call.keywords) <= 1
                        and all(k.arg == "steps" for k in call.keywords)):
                    raise PolicyError("Use env.step(action, steps=positive_integer)")
                action = expr(call.args[0])
                count = expr(call.keywords[0].value) if call.keywords else 1
                integer(count, "steps", 1, max_steps)
                if not isinstance(action, dict) or len(actions) + count > max_steps:
                    raise PolicyError(f"Expected action dict and at most {max_steps} steps")
                actions.extend(copy.deepcopy(action) for _ in range(count))
            else:
                raise PolicyError(f"Unsupported statement: {type(node).__name__}")
    try:
        block(tree.body)
    except (TypeError, KeyError, IndexError, ZeroDivisionError, OverflowError, RecursionError) as exc:
        raise PolicyError(str(exc)) from exc
    if not actions:
        raise PolicyError("Segment must execute at least one step")
    return actions
