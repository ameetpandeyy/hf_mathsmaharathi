"""Exam pattern analyzer and blueprint generation engine."""

from __future__ import annotations

import collections
from typing import Dict, List, Optional
import uuid

from schemas.enums import DifficultyLevel, ExamType, TopicSlug
from schemas.models import Blueprint, Paper, Question, TopicWeightage


# Standard exam defaults when extracting blueprints
EXAM_DEFAULTS = {
    ExamType.SSC_CGL: {
        "title": "SSC CGL Tier-1 Quantitative Aptitude",
        "total_questions": 25,
        "duration_minutes": 20,  # 20 mins allocated to math out of 60 mins composite
        "positive_mark_per_q": 2.0,
        "negative_mark_per_q": 0.50,
    },
    ExamType.SSC_CHSL: {
        "title": "SSC CHSL Tier-1 Quantitative Aptitude",
        "total_questions": 25,
        "duration_minutes": 20,
        "positive_mark_per_q": 2.0,
        "negative_mark_per_q": 0.50,
    },
    ExamType.SBI_PO: {
        "title": "SBI PO Prelims Quantitative Aptitude",
        "total_questions": 35,
        "duration_minutes": 20,
        "positive_mark_per_q": 1.0,
        "negative_mark_per_q": 0.25,
    },
    ExamType.IBPS_PO: {
        "title": "IBPS PO Prelims Quantitative Aptitude",
        "total_questions": 35,
        "duration_minutes": 20,
        "positive_mark_per_q": 1.0,
        "negative_mark_per_q": 0.25,
    },
    ExamType.IBPS_CLERK: {
        "title": "IBPS Clerk Prelims Numerical Ability",
        "total_questions": 35,
        "duration_minutes": 20,
        "positive_mark_per_q": 1.0,
        "negative_mark_per_q": 0.25,
    },
    ExamType.RRB_NTPC: {
        "title": "RRB NTPC Mathematics",
        "total_questions": 30,
        "duration_minutes": 30,
        "positive_mark_per_q": 1.0,
        "negative_mark_per_q": 0.33,
    },
    ExamType.RRB_GROUP_D: {
        "title": "RRB Group D Mathematics",
        "total_questions": 25,
        "duration_minutes": 25,
        "positive_mark_per_q": 1.0,
        "negative_mark_per_q": 0.33,
    },
}


class PatternAnalyzer:
    """Analyzes previous year papers to extract empirical exam pattern blueprints."""

    @classmethod
    def analyze_paper(
        cls,
        paper: Paper,
        blueprint_id: Optional[str] = None,
    ) -> Blueprint:
        """Derives an empirical Blueprint from a single parsed paper."""
        return cls.analyze_questions(
            questions=paper.questions,
            exam=paper.exam,
            year=paper.year,
            blueprint_id=blueprint_id,
        )

    @classmethod
    def analyze_questions(
        cls,
        questions: List[Question],
        exam: ExamType,
        year: Optional[int] = None,
        blueprint_id: Optional[str] = None,
    ) -> Blueprint:
        """Derives an empirical Blueprint from a collection of questions."""
        defaults = EXAM_DEFAULTS.get(
            exam,
            {
                "title": f"{exam.value.upper()} Math Section",
                "total_questions": len(questions) or 25,
                "duration_minutes": 25,
                "positive_mark_per_q": 2.0,
                "negative_mark_per_q": 0.5,
            },
        )

        total_q = len(questions)
        if total_q == 0:
            total_q = defaults["total_questions"]

        # Group by topic
        topic_counts: Dict[TopicSlug, List[Question]] = collections.defaultdict(list)
        diff_counts: Dict[DifficultyLevel, int] = collections.defaultdict(int)

        for q in questions:
            topic_counts[q.topic_slug].append(q)
            diff_counts[q.difficulty] += 1

        # Build TopicWeightage list
        weightages: List[TopicWeightage] = []
        for topic, q_list in topic_counts.items():
            cnt = len(q_list)
            pct = round((cnt / total_q) * 100.0, 2) if total_q > 0 else 0.0
            
            diff_breakdown: Dict[DifficultyLevel, int] = collections.defaultdict(int)
            total_secs = 0
            for item in q_list:
                diff_breakdown[item.difficulty] += 1
                total_secs += item.target_seconds

            avg_secs = round(total_secs / cnt, 1) if cnt > 0 else 45.0
            weightages.append(
                TopicWeightage(
                    topic_slug=topic,
                    count=cnt,
                    percentage=pct,
                    difficulty_breakdown=dict(diff_breakdown),
                    avg_target_seconds=avg_secs,
                )
            )

        # Sort weightages descending by count
        weightages.sort(key=lambda w: w.count, reverse=True)

        # Difficulty curve
        diff_curve: Dict[DifficultyLevel, float] = {}
        for diff in DifficultyLevel:
            count_diff = diff_counts.get(diff, 0)
            diff_curve[diff] = round(count_diff / total_q, 3) if total_q > 0 else 0.33

        pos_mark = defaults["positive_mark_per_q"]
        neg_mark = defaults["negative_mark_per_q"]
        tot_marks = total_q * pos_mark

        b_id = blueprint_id or f"bp_{exam.value}_{year or 'standard'}_{uuid.uuid4().hex[:6]}"
        title = f"{defaults['title']} Pattern ({year or 'Standard'})"

        return Blueprint(
            id=b_id,
            exam=exam,
            title=title,
            total_questions=total_q,
            duration_minutes=defaults["duration_minutes"],
            total_marks=tot_marks,
            positive_mark_per_q=pos_mark,
            negative_mark_per_q=neg_mark,
            topic_weightages=weightages,
            target_difficulty_curve=diff_curve,
            metadata={
                "analyzed_questions_count": len(questions),
                "exam_year": year,
            },
        )
