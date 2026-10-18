"""Unit tests strictly validating the legal copyright gate and quality publishing filters."""

from pipeline.export.pack_builder import ContentPackBuilder
from schemas.enums import ExamType, ReviewStatus, SourceType, TopicSlug
from schemas.models import Option, Question


def test_export_blocks_unauthorized_pyq_and_unverified():
    """Validates that:
    1. PYQ references are NEVER published unless rights_cleared=True.
    2. Unverified or unapproved questions are NEVER published.
    3. Audit counts accurately reflect blocked items.
    """
    # 1. PYQ Question WITHOUT rights cleared (MUST BE BLOCKED)
    q_pyq_protected = Question(
        id="pyq_1",
        source_type=SourceType.PYQ_REFERENCE,
        rights_cleared=False,
        exam=ExamType.SSC_CGL,
        text_en="PYQ math question text",
        options=[Option(id="A", text_en="1"), Option(id="B", text_en="2")],
        correct_option="A",
        topic_slug=TopicSlug.SIMPLIFICATION,
        machine_verified=True,
        review_status=ReviewStatus.APPROVED,
    )

    # 2. PYQ Question WITH rights cleared and approved (ALLOWED)
    q_pyq_cleared = Question(
        id="pyq_2",
        source_type=SourceType.PYQ_REFERENCE,
        rights_cleared=True,
        exam=ExamType.SSC_CGL,
        text_en="PYQ with license cleared",
        options=[Option(id="A", text_en="10"), Option(id="B", text_en="20")],
        correct_option="A",
        topic_slug=TopicSlug.SIMPLIFICATION,
        machine_verified=True,
        review_status=ReviewStatus.APPROVED,
    )

    # 3. Original question but UNVERIFIED by solver (MUST BE BLOCKED)
    q_orig_unverified = Question(
        id="orig_1",
        source_type=SourceType.ORIGINAL,
        rights_cleared=True,
        exam=ExamType.SSC_CGL,
        text_en="Unverified question",
        options=[Option(id="A", text_en="5"), Option(id="B", text_en="6")],
        correct_option="A",
        topic_slug=TopicSlug.SIMPLIFICATION,
        machine_verified=False,  # Unverified
        review_status=ReviewStatus.APPROVED,
    )

    # 4. Original question verified but UNAPPROVED (MUST BE BLOCKED)
    q_orig_unapproved = Question(
        id="orig_2",
        source_type=SourceType.ORIGINAL,
        rights_cleared=True,
        exam=ExamType.SSC_CGL,
        text_en="Unapproved draft question",
        options=[Option(id="A", text_en="7"), Option(id="B", text_en="8")],
        correct_option="A",
        topic_slug=TopicSlug.SIMPLIFICATION,
        machine_verified=True,
        review_status=ReviewStatus.DRAFT,  # Draft
    )

    # 5. Original question verified and approved (ALLOWED)
    q_orig_valid = Question(
        id="orig_3",
        source_type=SourceType.ORIGINAL,
        rights_cleared=True,
        exam=ExamType.SSC_CGL,
        text_en="Valid verified approved question",
        options=[Option(id="A", text_en="100"), Option(id="B", text_en="200")],
        correct_option="A",
        topic_slug=TopicSlug.SIMPLIFICATION,
        machine_verified=True,
        review_status=ReviewStatus.APPROVED,
    )

    candidates = [
        q_pyq_protected,
        q_pyq_cleared,
        q_orig_unverified,
        q_orig_unapproved,
        q_orig_valid,
    ]

    pack, stats = ContentPackBuilder.build_pack(
        pack_id="test_pack",
        version="1.0.0",
        exam=ExamType.SSC_CGL,
        title="Test Pack",
        candidate_questions=candidates,
        enforce_approval=True,
    )

    # Audit stats verification
    assert stats["total_candidates"] == 5
    assert stats["blocked_pyq_copyright"] == 1, "Must block pyq_1 due to rights_cleared=False"
    assert stats["blocked_unverified"] == 1, "Must block orig_1 due to machine_verified=False"
    assert stats["blocked_unapproved"] == 1, "Must block orig_2 due to draft status"
    assert stats["eligible"] == 2, "Only pyq_2 and orig_3 must pass into the pack"

    # Verify published question IDs
    published_ids = {q.id for q in pack.questions}
    assert published_ids == {"pyq_2", "orig_3"}
    assert "pyq_1" not in published_ids
    assert "orig_1" not in published_ids
    assert "orig_2" not in published_ids
