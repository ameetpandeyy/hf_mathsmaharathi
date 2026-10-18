"""Unit tests for deterministic question generators and mock builder."""

import random
from pipeline.generate.builder import MockBuilder
from pipeline.generate.generators import (
    InterestGenerator,
    ProfitLossGenerator,
    SimplificationGenerator,
    SpeedDistanceGenerator,
    TimeWorkGenerator,
)
from schemas.enums import DifficultyLevel, ExamType, SourceType, TopicSlug
from schemas.models import Blueprint, TopicWeightage


def test_generator_deterministic_reproducibility():
    """Validates that a fixed seed produces identical questions and values."""
    rng1 = random.Random(12345)
    rng2 = random.Random(12345)

    gen1 = SimplificationGenerator(rng1)
    gen2 = SimplificationGenerator(rng2)

    q1 = gen1.generate(exam=ExamType.SSC_CGL, difficulty=DifficultyLevel.EASY)
    q2 = gen2.generate(exam=ExamType.SSC_CGL, difficulty=DifficultyLevel.EASY)

    assert q1.text_en == q2.text_en
    assert q1.correct_option == q2.correct_option
    assert [o.text_en for o in q1.options] == [o.text_en for o in q2.options]
    assert q1.machine_verified is True
    assert q2.machine_verified is True


def test_all_topic_generators_produce_verified_questions():
    """Tests each topic generator to guarantee solver verification and correct option keys."""
    rng = random.Random(42)
    generators = [
        SimplificationGenerator(rng),
        ProfitLossGenerator(rng),
        InterestGenerator(rng),
        TimeWorkGenerator(rng),
        SpeedDistanceGenerator(rng),
    ]

    for gen in generators:
        q = gen.generate(exam=ExamType.SSC_CGL, difficulty=DifficultyLevel.MEDIUM)
        assert q.source_type == SourceType.ORIGINAL
        assert q.rights_cleared is True
        assert len(q.options) == 4
        assert q.correct_option in ["A", "B", "C", "D"]
        assert q.machine_verified is True, f"Failed verification for {gen.__class__.__name__}"
        assert q.solver_output is not None
        assert q.solver_output["solved"] is True


def test_mock_builder_matches_blueprint():
    """Validates that MockBuilder accurately constructs papers matching blueprint constraints."""
    bp = Blueprint(
        id="bp_test",
        exam=ExamType.SSC_CGL,
        title="Test Blueprint",
        total_questions=10,
        duration_minutes=15,
        total_marks=20.0,
        positive_mark_per_q=2.0,
        negative_mark_per_q=0.5,
        topic_weightages=[
            TopicWeightage(topic_slug=TopicSlug.SIMPLIFICATION, count=5, percentage=50.0),
            TopicWeightage(topic_slug=TopicSlug.PROFIT_LOSS, count=3, percentage=30.0),
            TopicWeightage(topic_slug=TopicSlug.TIME_WORK, count=2, percentage=20.0),
        ],
    )

    builder = MockBuilder(seed=999)
    mock = builder.build_mock_paper(blueprint=bp)

    assert len(mock.questions) == 10
    assert mock.exam == ExamType.SSC_CGL
    assert mock.source_type == SourceType.ORIGINAL
    assert all(q.machine_verified for q in mock.questions)
