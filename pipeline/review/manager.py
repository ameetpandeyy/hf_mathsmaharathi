"""Editorial review queue and CRM sync manager."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
import uuid

from schemas.enums import ReviewStatus
from schemas.models import Question, ReviewItem


class ReviewManager:
    """Manages the editorial workflow and question review lifecycle."""

    def __init__(self):
        self._items: Dict[str, ReviewItem] = {}
        self._questions: Dict[str, Question] = {}

    def register_question(self, question: Question) -> ReviewItem:
        """Enrolls a question into the review queue."""
        self._questions[question.id] = question
        item = ReviewItem(
            id=f"rev_{uuid.uuid4().hex[:8]}",
            question_id=question.id,
            status=question.review_status,
            notes=question.reviewer_notes,
        )
        self._items[question.id] = item
        return item

    def approve_question(
        self,
        question_id: str,
        reviewer_id: str,
        notes: Optional[str] = None,
    ) -> Question:
        """Approves a question for publication."""
        if question_id not in self._questions:
            raise KeyError(f"Question {question_id} not found in review queue")

        q = self._questions[question_id]
        q.review_status = ReviewStatus.APPROVED
        q.reviewer_notes = notes

        if question_id in self._items:
            rev_item = self._items[question_id]
            rev_item.status = ReviewStatus.APPROVED
            rev_item.reviewer_id = reviewer_id
            rev_item.notes = notes
            rev_item.reviewed_at = datetime.utcnow().isoformat()

        return q

    def reject_question(
        self,
        question_id: str,
        reviewer_id: str,
        reasons: List[str],
        notes: Optional[str] = None,
    ) -> Question:
        """Rejects a question with flagged quality or mathematical reasons."""
        if question_id not in self._questions:
            raise KeyError(f"Question {question_id} not found in review queue")

        q = self._questions[question_id]
        q.review_status = ReviewStatus.REJECTED
        q.reviewer_notes = notes

        if question_id in self._items:
            rev_item = self._items[question_id]
            rev_item.status = ReviewStatus.REJECTED
            rev_item.reviewer_id = reviewer_id
            rev_item.flagged_reasons = reasons
            rev_item.notes = notes
            rev_item.reviewed_at = datetime.utcnow().isoformat()

        return q

    def get_pending(self) -> List[Question]:
        """Returns all questions pending editorial review."""
        return [
            q for q in self._questions.values()
            if q.review_status in (ReviewStatus.DRAFT, ReviewStatus.VERIFIED)
        ]

    def get_item_for_question(self, question_id: str) -> Optional[ReviewItem]:
        """Fetches the ReviewItem state."""
        return self._items.get(question_id)
