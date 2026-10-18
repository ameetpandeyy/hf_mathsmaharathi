"""Core Pydantic models for Maths Maharathi pipeline and Supabase integration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from schemas.enums import (
    DifficultyLevel,
    ExamType,
    ReviewStatus,
    SourceType,
    TopicSlug,
)


class Option(BaseModel):
    """Single answer option for multiple choice math questions."""
    id: str = Field(..., description="Option identifier, e.g., 'A', 'B', 'C', 'D'")
    text_en: str = Field(..., description="Option text in English")
    text_hi: Optional[str] = Field(None, description="Option text in Hindi")
    latex: Optional[str] = Field(None, description="LaTeX representation if mathematical")


class Question(BaseModel):
    """Primary question representation across parsing, verification, and storage."""
    id: str = Field(..., description="Unique question ID (UUID or content-hash-based)")
    
    # Legal and provenance guardrails (MANDATORY)
    source_type: SourceType = Field(
        ...,
        description="'pyq_reference' (analysis only) or 'original' (eligible for mocks)",
    )
    rights_cleared: bool = Field(
        default=False,
        description="Explicit legal clearance flag. pyq_reference CANNOT be exported unless this is True",
    )
    exam: ExamType = Field(..., description="Target exam (e.g. ssc_cgl, sbi_po)")
    year: Optional[int] = Field(None, description="Exam year if known")
    shift: Optional[str] = Field(None, description="Exam shift if known")
    source_url: Optional[str] = Field(None, description="Source provenance URL if known")

    # Question text & options (Bilingual support)
    text_en: str = Field(..., description="Question statement in English")
    text_hi: Optional[str] = Field(None, description="Question statement in Hindi")
    options: List[Option] = Field(..., min_length=2, max_length=5)
    correct_option: str = Field(..., description="Key of the correct option ('A', 'B', 'C', 'D')")
    solution_en: Optional[str] = Field(None, description="Step-by-step solution in English")
    solution_hi: Optional[str] = Field(None, description="Step-by-step solution in Hindi")

    # Classification metadata
    topic_slug: TopicSlug = Field(..., description="Standardized curriculum topic slug")
    subtopic: Optional[str] = Field(None, description="Granular subtopic name")
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.MEDIUM)
    target_seconds: int = Field(default=45, description="Benchmark solving time in seconds")
    marks_correct: float = Field(default=2.0)
    marks_negative: float = Field(default=0.5)

    # Machine verification & quality control
    machine_verified: bool = Field(default=False, description="True if verified by SymPy/solver")
    solver_output: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured verification result from the solver",
    )
    dedupe_hash: Optional[str] = Field(None, description="SimHash / canonical text hash")

    # Editorial workflow
    review_status: ReviewStatus = Field(default=ReviewStatus.DRAFT)
    reviewer_notes: Optional[str] = Field(None)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def is_export_eligible(self) -> bool:
        """Determines if the question satisfies all legal and quality gates for publishing.
        
        Rules:
        1. Must be APPROVED in review.
        2. Must be machine_verified by the mathematical solver.
        3. If source_type is 'pyq_reference', it is STRICTLY BLOCKED unless rights_cleared is True.
        """
        if self.review_status != ReviewStatus.APPROVED:
            return False
        if not self.machine_verified:
            return False
        if self.source_type == SourceType.PYQ_REFERENCE and not self.rights_cleared:
            return False
        return True

    def calculate_dedupe_hash(self) -> str:
        """Computes a normalized SHA-256 hash based on canonical english text and options."""
        canonical = self.text_en.strip().lower()
        opts = "|".join(opt.text_en.strip().lower() for opt in sorted(self.options, key=lambda o: o.id))
        raw = f"{canonical}::{opts}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Paper(BaseModel):
    """Complete test paper model representing previous year papers or generated mocks."""
    id: str = Field(..., description="Unique paper identifier")
    title: str = Field(..., description="Paper title, e.g., 'SSC CGL 2023 Tier-1 Shift 1'")
    exam: ExamType
    year: int
    shift: Optional[str] = None
    source_url: Optional[str] = None
    source_type: SourceType = Field(default=SourceType.PYQ_REFERENCE)
    total_questions: int = Field(...)
    duration_minutes: int = Field(default=60)
    total_marks: float = Field(...)
    negative_marking_ratio: float = Field(default=0.25)
    questions: List[Question] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TopicWeightage(BaseModel):
    """Weightage and characteristics of a topic within an exam blueprint."""
    topic_slug: TopicSlug
    count: int = Field(..., ge=0)
    percentage: float = Field(..., ge=0.0, le=100.0)
    difficulty_breakdown: Dict[DifficultyLevel, int] = Field(default_factory=dict)
    avg_target_seconds: float = Field(default=45.0)


class Blueprint(BaseModel):
    """Exam pattern blueprint defining mock generation constraints."""
    id: str = Field(...)
    exam: ExamType
    title: str
    total_questions: int
    duration_minutes: int
    total_marks: float
    positive_mark_per_q: float = 2.0
    negative_mark_per_q: float = 0.5
    topic_weightages: List[TopicWeightage]
    target_difficulty_curve: Dict[DifficultyLevel, float] = Field(
        default_factory=lambda: {
            DifficultyLevel.EASY: 0.35,
            DifficultyLevel.MEDIUM: 0.50,
            DifficultyLevel.HARD: 0.15,
        }
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewItem(BaseModel):
    """Review queue record syncing with Supabase Admin CRM."""
    id: str = Field(...)
    question_id: str
    status: ReviewStatus = Field(default=ReviewStatus.DRAFT)
    reviewer_id: Optional[str] = None
    notes: Optional[str] = None
    flagged_reasons: List[str] = Field(default_factory=list)
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ContentPack(BaseModel):
    """Versioned content bundle for distribution to mobile app and Supabase."""
    pack_id: str
    version: str = Field(..., description="Semantic version string, e.g., '1.0.0'")
    exam: ExamType
    title: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    checksum_sha256: str = Field(default="")
    question_count: int = 0
    mock_papers_count: int = 0
    papers: List[Paper] = Field(default_factory=list)
    questions: List[Question] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def calculate_checksum(self) -> str:
        """Calculates a deterministic SHA-256 hash of the questions payload."""
        payload = json.dumps(
            [q.model_dump(mode="json") for q in sorted(self.questions, key=lambda x: x.id)],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
