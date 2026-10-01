from __future__ import annotations
import ast

class GuardExpressionError(ValueError):
    pass

_CMP_OPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_LITERAL_NAMES = {"true", "false", "none"}

def _parse(expression: str):
    try:
        return ast.parse(expression, mode="eval").body
    except SyntaxError as e:
        raise GuardExpressionError(f"invalid guard expression {expression!r}: {e}") from e

def evaluate_guard(expression: str, state: dict) -> bool:
    """Safely evaluate a guard/invariant boolean expression against `state`.

    Supports comparisons, and/or/not (short-circuiting, like Python), names
    resolved from `state`, and literals. Everything else (calls, attributes,
    subscripts, arithmetic) is rejected because the walker has no branch for it.
    Type problems (e.g. comparing a str to a number) surface as
    GuardExpressionError so callers have exactly one exception type to handle.
    """
    node = _parse(expression)
    try:
        return bool(_eval(node, state))
    except TypeError as e:
        raise GuardExpressionError(f"type error evaluating {expression!r}: {e}") from e

def referenced_names(expression: str) -> set[str]:
    """Identifiers an expression reads from state (literals excluded)."""
    tree = _parse(expression)
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id.lower() not in _LITERAL_NAMES}

def _eval(node, state):
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for v in node.values:
                if not _eval(v, state):
                    return False
            return True
        for v in node.values:
            if _eval(v, state):
                return True
        return False
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand, state)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, state)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, state)
            fn = _CMP_OPS.get(type(op))
            if fn is None:
                raise GuardExpressionError(f"unsupported comparison operator: {type(op).__name__}")
            if not fn(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        low = node.id.lower()
        if low == "true":
            return True
        if low == "false":
            return False
        if low == "none":
            return None
        if node.id not in state:
            raise GuardExpressionError(f"unknown identifier {node.id!r} in guard expression")
        return state[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    raise GuardExpressionError(f"unsupported expression node: {type(node).__name__} (only comparisons, boolean logic, names and literals are allowed)")
