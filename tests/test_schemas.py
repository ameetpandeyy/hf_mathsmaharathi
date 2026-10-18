"""Unit tests for pipeline schemas and legal guardrails."""

import pytest
from schemas.enums import DifficultyLevel, ExamType, ReviewStatus, SourceType, TopicSlug
from schemas.models import ContentPack, Option, Question


def test_question_legal_guardrail():
    """Validates that pyq_reference questions CANNOT be exported without rights_cleared=True."""
    # 1. Unapproved original question -> Not eligible
    q_orig_unapproved = Question(
        id="q1",
        source_type=SourceType.ORIGINAL,
        rights_cleared=True,
        exam=ExamType.SSC_CGL,
        text_en="What is 5 + 5?",
        options=[Option(id="A", text_en="10"), Option(id="B", text_en="12")],
        correct_option="A",
        topic_slug=TopicSlug.SIMPLIFICATION,
        machine_verified=True,
        review_status=ReviewStatus.DRAFT,
    )
    assert not q_orig_unapproved.is_export_eligible()

    # 2. Approved original question with machine verification -> Eligible
    q_orig_unapproved.review_status = ReviewStatus.APPROVED
    assert q_orig_unapproved.is_export_eligible()

    # 3. Approved PYQ reference without rights cleared -> STRICTLY BLOCKED
    q_pyq = Question(
        id="q2",
        source_type=SourceType.PYQ_REFERENCE,
        rights_cleared=False,  # Protected
        exam=ExamType.SSC_CGL,
        text_en="Previous year exam question text",
        options=[Option(id="A", text_en="1"), Option(id="B", text_en="2")],
        correct_option="A",
        topic_slug=TopicSlug.SIMPLIFICATION,
        machine_verified=True,
        review_status=ReviewStatus.APPROVED,
    )
    assert not q_pyq.is_export_eligible(), "PYQ reference must NOT be export eligible without rights_cleared!"

    # 4. Approved PYQ reference with manual rights clearance -> Eligible
    q_pyq.rights_cleared = True
    assert q_pyq.is_export_eligible()


def test_content_pack_checksum():
    """Validates deterministic SHA-256 calculation for content packs."""
    q = Question(
        id="q_test_1",
        source_type=SourceType.ORIGINAL,
        rights_cleared=True,
        exam=ExamType.SSC_CGL,
        text_en="What is 10 + 10?",
        options=[Option(id="A", text_en="20"), Option(id="B", text_en="30")],
        correct_option="A",
        topic_slug=TopicSlug.SIMPLIFICATION,
        machine_verified=True,
        review_status=ReviewStatus.APPROVED,
    )
    pack = ContentPack(
        pack_id="pack_ssc_cgl",
        version="1.0.0",
        exam=ExamType.SSC_CGL,
        title="SSC CGL Pack",
        questions=[q],
    )
    cs1 = pack.calculate_checksum()
    cs2 = pack.calculate_checksum()
    assert cs1 == cs2
    assert len(cs1) == 64
