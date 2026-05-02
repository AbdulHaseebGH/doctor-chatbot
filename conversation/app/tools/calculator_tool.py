# --------------------------------------------------------------------------
# conversation/app/tools/calculator_tool.py
#
# Safe Calculator Tool — evaluates arithmetic expressions.
# Uses a restricted AST-based evaluator to prevent code injection.
# --------------------------------------------------------------------------

import ast
import operator


# Allowed operators — only safe arithmetic
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def _safe_eval(node) -> float:
    """Recursively evaluate an AST node — only arithmetic allowed."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Unsupported constant: {node.value}")

    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return _ALLOWED_OPERATORS[op_type](left, right)

    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _safe_eval(node.operand)
        return _ALLOWED_OPERATORS[op_type](operand)

    else:
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")


async def calculate(expression: str) -> dict:
    """
    Safely evaluate an arithmetic expression.

    Args:
        expression: Math expression string e.g. "2 + 2", "10 * 5 / 2", "2 ** 8"

    Returns:
        {"result": 4.0, "expression": "2 + 2"} or {"error": "..."}
    """
    expression = expression.strip()
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        # Return integer if result is a whole number
        display = int(result) if result == int(result) else round(result, 6)
        return {"result": display, "expression": expression}
    except ZeroDivisionError:
        return {"error": "Division by zero"}
    except Exception as e:
        return {"error": f"Cannot evaluate '{expression}': {str(e)}"}


# Tool schema
CALCULATOR_TOOL_SCHEMA = {
    "name": "calculator",
    "description": "Evaluate arithmetic expressions. Useful for age calculations, date math, dosage calculations.",
    "functions": {
        "calculate": {"args": ["expression"], "description": "Calculate arithmetic expression"},
    }
}
