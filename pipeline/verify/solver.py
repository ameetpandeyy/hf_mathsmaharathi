"""Mathematical solver and verification engine for Maths Maharathi.

Uses SymPy for exact symbolic and algebraic evaluation, with safe arithmetic fallbacks
to verify question answer keys deterministically.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import sympy
    from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
    HAS_SYMPY = True
except ImportError:
    HAS_SYMPY = False

from schemas.models import Option, Question


# Safe arithmetic operator mapping for non-eval AST evaluation
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval_expr(expr_str: str) -> float:
    """Safely evaluates basic arithmetic expressions without eval() or code execution."""
    cleaned = expr_str.replace("×", "*").replace("÷", "/").replace("^", "**")
    
    def _eval(node: ast.AST) -> Union[int, float]:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_OPERATORS:
                raise ValueError(f"Operator {op_type} not permitted")
            left = _eval(node.left)
            right = _eval(node.right)
            return _ALLOWED_OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_OPERATORS:
                raise ValueError(f"Operator {op_type} not permitted")
            operand = _eval(node.operand)
            return _ALLOWED_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported AST node: {type(node)}")

    parsed = ast.parse(cleaned, mode="eval")
    return float(_eval(parsed))


class MathSolver:
    """Deterministic mathematical problem solver and answer-key verifier."""

    @classmethod
    def extract_numbers_from_text(cls, text: str) -> List[float]:
        """Extracts floating point or integer values from text."""
        tokens = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", text)
        return [float(t) for t in tokens]

    @classmethod
    def solve_expression(cls, expr_str: str) -> float:
        """Solves a pure algebraic/arithmetic expression."""
        if HAS_SYMPY:
            transformations = standard_transformations + (implicit_multiplication_application,)
            clean = expr_str.replace("×", "*").replace("÷", "/").replace("^", "**")
            parsed = parse_expr(clean, transformations=transformations)
            val = float(parsed.evalf())
            return val
        return safe_eval_expr(expr_str)

    @classmethod
    def solve_quadratic(cls, a: float, b: float, c: float) -> Tuple[float, float]:
        """Finds roots of a*x^2 + b*x + c = 0."""
        d = b**2 - 4 * a * c
        if d < 0:
            raise ValueError("No real roots for the given quadratic parameters")
        r1 = (-b + math.isqrt(int(d)) if int(d) == d else (-b + math.sqrt(d))) / (2 * a)
        r2 = (-b - math.isqrt(int(d)) if int(d) == d else (-b - math.sqrt(d))) / (2 * a)
        return sorted([float(r1), float(r2)])

    @classmethod
    def solve_simple_interest(cls, p: float, r: float, t: float) -> float:
        """SI = (P * R * T) / 100."""
        return (p * r * t) / 100.0

    @classmethod
    def solve_compound_interest(cls, p: float, r: float, t: float) -> float:
        """CI = P * (1 + R/100)^T - P."""
        return p * ((1.0 + r / 100.0) ** t) - p

    @classmethod
    def solve_time_and_work(cls, days_a: float, days_b: float) -> float:
        """Combined work time: 1 / (1/a + 1/b) = (a * b) / (a + b)."""
        return (days_a * days_b) / (days_a + days_b)

    @classmethod
    def solve_speed_distance_time(cls, distance: Optional[float], speed: Optional[float], time: Optional[float]) -> float:
        """Solves the missing component in D = S * T."""
        if distance is None and speed is not None and time is not None:
            return speed * time
        if speed is None and distance is not None and time is not None:
            return distance / time
        if time is None and distance is not None and speed is not None:
            return distance / speed
        raise ValueError("Exactly one parameter must be None")

    @classmethod
    def match_value_to_options(cls, expected_val: float, options: List[Option], tolerance: float = 1e-2) -> Optional[str]:
        """Matches a numerical result to one of the given multiple choice options."""
        for opt in options:
            nums = cls.extract_numbers_from_text(opt.text_en)
            if not nums:
                continue
            # If option has a single number or primary number
            for num in nums:
                if math.isclose(num, expected_val, rel_tol=tolerance, abs_tol=tolerance):
                    return opt.id
        return None

    @classmethod
    def verify_question(cls, question: Question) -> Tuple[bool, Dict[str, Any]]:
        """Verifies a question against mathematical solvers.
        
        Returns:
            (is_verified, verification_details_dict)
        """
        details: Dict[str, Any] = {
            "solver": "sympy" if HAS_SYMPY else "safe_ast",
            "solved": False,
            "calculated_value": None,
            "matched_option": None,
            "expected_option": question.correct_option,
            "mismatch": False,
            "notes": "",
        }

        # Check metadata for generator hints if generated question
        gen_meta = question.metadata.get("generator_info")
        if gen_meta and "exact_answer" in gen_meta:
            exact_val = float(gen_meta["exact_answer"])
            matched = cls.match_value_to_options(exact_val, question.options)
            details["calculated_value"] = exact_val
            details["matched_option"] = matched
            if matched == question.correct_option:
                details["solved"] = True
                details["notes"] = "Verified via generator exact answer specification"
                return True, details
            else:
                details["mismatch"] = True
                details["notes"] = f"Key mismatch! Solver got option {matched}, key says {question.correct_option}"
                return False, details

        # For arithmetic / simplification questions
        if question.topic_slug.value in ("simplification", "algebra"):
            # Attempt to extract mathematical expression from question text
            # e.g., "What is the value of: 25 * 4 + (100 / 5)?"
            expr_match = re.search(r"[:?]\s*([0-9\+\-\*\/\^\(\)\.\s×÷]+)", question.text_en)
            if not expr_match:
                expr_match = re.search(r"([0-9\+\-\*\/\^\(\)\.\s×÷]{5,})", question.text_en)
            
            if expr_match:
                raw_expr = expr_match.group(1).strip()
                try:
                    val = cls.solve_expression(raw_expr)
                    details["calculated_value"] = val
                    matched = cls.match_value_to_options(val, question.options)
                    details["matched_option"] = matched
                    if matched == question.correct_option:
                        details["solved"] = True
                        return True, details
                    elif matched is not None:
                        details["mismatch"] = True
                        details["notes"] = f"Mismatch: computed {val} -> option {matched}, but correct_option is {question.correct_option}"
                        return False, details
                except Exception as exc:
                    details["notes"] = f"Expression parser error: {str(exc)}"

        # General solver fallback: check if option key exists in options
        opt_keys = {o.id for o in question.options}
        if question.correct_option not in opt_keys:
            details["mismatch"] = True
            details["notes"] = f"Invalid answer key: {question.correct_option} not in options {sorted(opt_keys)}"
            return False, details

        details["notes"] = "Option key structure validated; requires domain solver or human review"
        return False, details
