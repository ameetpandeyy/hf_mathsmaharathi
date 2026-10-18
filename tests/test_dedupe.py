"""Unit tests for deduplication and canonical hashing."""

from pipeline.dedupe.hasher import (
    DedupeEngine,
    compute_simhash_64,
    hamming_distance,
    jaccard_similarity,
    normalize_math_text,
)
from schemas.enums import ExamType, SourceType, TopicSlug
from schemas.models import Option, Question


def test_text_normalization():
    """Validates math text normalization."""
    t1 = "What is the value of: 25 × 4 + 10?"
    t2 = "what  is the value of   25 * 4 + 10"
    assert normalize_math_text(t1) == normalize_math_text(t2)


def test_simhash_and_jaccard():
    """Validates near duplicate detection using SimHash and Jaccard."""
    s1 = "A can finish a work in 10 days and B in 15 days."
    s2 = "A can finish a work in 10 days and B can finish the work in 15 days."
    
    sh1 = compute_simhash_64(s1)
    sh2 = compute_simhash_64(s2)
    dist = hamming_distance(sh1, sh2)
    assert dist <= 6, f"SimHash distance {dist} should be small for near-identical sentences"


def test_dedupe_engine_collision_detection():
    """Validates DedupeEngine flagging identical and near duplicate questions."""
    engine = DedupeEngine()

    q1 = Question(
        id="q1",
        source_type=SourceType.ORIGINAL,
        exam=ExamType.SSC_CGL,
        text_en="An article is purchased for ₹500 and sold at 20% profit.",
        options=[Option(id="A", text_en="₹600"), Option(id="B", text_en="₹550")],
        correct_option="A",
        topic_slug=TopicSlug.PROFIT_LOSS,
    )
    engine.register(q1)

    # Identical question candidate
    q_identical = Question(
        id="q_copy",
        source_type=SourceType.ORIGINAL,
        exam=ExamType.SSC_CGL,
        text_en="An article is purchased for ₹500 and sold at 20% profit.",
        options=[Option(id="A", text_en="₹600"), Option(id="B", text_en="₹550")],
        correct_option="A",
        topic_slug=TopicSlug.PROFIT_LOSS,
    )
    is_dup, dup_id, score = engine.check_duplicate(q_identical)
    assert is_dup is True
    assert score == 1.0

    # Completely different question candidate
    q_different = Question(
        id="q_diff",
        source_type=SourceType.ORIGINAL,
        exam=ExamType.SSC_CGL,
        text_en="Find the hypotenuse of triangle with legs 3 and 4.",
        options=[Option(id="A", text_en="5"), Option(id="B", text_en="6")],
        correct_option="A",
        topic_slug=TopicSlug.GEOMETRY,
    )
    is_dup2, _, _ = engine.check_duplicate(q_different)
    assert is_dup2 is False
