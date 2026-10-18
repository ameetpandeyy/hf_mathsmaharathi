"""Content pack builder with mandatory legal and quality guardrails."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
import uuid

from schemas.enums import ExamType, ReviewStatus, SourceType
from schemas.models import ContentPack, Paper, Question

logger = logging.getLogger(__name__)


class ContentPackBuilder:
    """Builds versioned, checksummed content packs adhering to strict legal publishing rules."""

    @classmethod
    def build_pack(
        cls,
        pack_id: str,
        version: str,
        exam: ExamType,
        title: str,
        candidate_questions: List[Question],
        papers: Optional[List[Paper]] = None,
        enforce_approval: bool = True,
    ) -> Tuple[ContentPack, Dict[str, int]]:
        """Constructs a content pack, enforcing legal rights clearance and solver verification.
        
        Returns:
            (ContentPack, audit_statistics_dict)
        """
        eligible_questions: List[Question] = []
        stats = {
            "total_candidates": len(candidate_questions),
            "eligible": 0,
            "blocked_pyq_copyright": 0,
            "blocked_unverified": 0,
            "blocked_unapproved": 0,
        }

        for q in candidate_questions:
            # 1. Check legal copyright guardrail
            if q.source_type == SourceType.PYQ_REFERENCE and not q.rights_cleared:
                stats["blocked_pyq_copyright"] += 1
                continue

            # 2. Check machine verification solver gate
            if not q.machine_verified:
                stats["blocked_unverified"] += 1
                continue

            # 3. Check human editorial review approval gate
            if enforce_approval and q.review_status != ReviewStatus.APPROVED:
                stats["blocked_unapproved"] += 1
                continue

            eligible_questions.append(q)

        stats["eligible"] = len(eligible_questions)

        pack = ContentPack(
            pack_id=pack_id,
            version=version,
            exam=exam,
            title=title,
            question_count=len(eligible_questions),
            mock_papers_count=len(papers or []),
            papers=papers or [],
            questions=eligible_questions,
            metadata={
                "audit_stats": stats,
            },
        )
        pack.checksum_sha256 = pack.calculate_checksum()
        return pack, stats
