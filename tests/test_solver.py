"""Unit tests for mathematical solver and verification engine."""

import pytest
from pipeline.verify.solver import MathSolver, safe_eval_expr
from schemas.enums import ExamType, SourceType, TopicSlug
from schemas.models import Option, Question


def test_safe_eval_expr():
    """Validates safe arithmetic evaluator without arbitrary code execution."""
    assert safe_eval_expr("25 * 4 + (120 / 6)") == 120.0
    assert safe_eval_expr("16 * 15 - 140") == 100.0
    assert safe_eval_expr("2^3 + 5") == 13.0


def test_quadratic_solver():
    """Validates roots of quadratic equations."""
    # x^2 - 7x + 12 = 0 -> roots 3 and 4
    r1, r2 = MathSolver.solve_quadratic(1, -7, 12)
    assert r1 == 3.0
    assert r2 == 4.0


def test_domain_solvers():
    """Validates simple interest, time & work, and speed distance time."""
    # SI: P=4000, R=5, T=3 -> 600
    assert MathSolver.solve_simple_interest(4000, 5, 3) == 600.0

    # CI: P=10000, R=10, T=2 -> 2100
    assert round(MathSolver.solve_compound_interest(10000, 10, 2), 2) == 2100.0

    # Time & Work: A=12, B=24 -> combined = (12*24)/(12+24) = 288/36 = 8
    assert MathSolver.solve_time_and_work(12, 24) == 8.0

    # Speed = 150m / 10s = 15 m/s
    assert MathSolver.solve_speed_distance_time(distance=150, speed=None, time=10) == 15.0


def test_solver_detects_answer_key_mismatch():
    """Ensures solver loudly flags discrepancies when an answer key does not match calculation."""
    # 25 * 4 = 100, but options claim correct option is B (which has 200)
    q_mismatch = Question(
        id="q_bad_key",
        source_type=SourceType.ORIGINAL,
        exam=ExamType.SSC_CGL,
        text_en="What is the value of: 25 * 4?",
        options=[
            Option(id="A", text_en="100"),
            Option(id="B", text_en="200"),
            Option(id="C", text_en="300"),
            Option(id="D", text_en="400"),
        ],
        correct_option="B",  # INCORRECT KEY!
        topic_slug=TopicSlug.SIMPLIFICATION,
    )

    is_verified, details = MathSolver.verify_question(q_mismatch)
    assert not is_verified, "Solver must reject mismatched answer key!"
    assert details["mismatch"] is True
    assert "Mismatch" in details["notes"]
