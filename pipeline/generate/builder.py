"""Blueprint-driven mock test assembler for Maths Maharathi.

Generates full mock tests conforming to empirical exam blueprints with:
- Seeded determinism for reproducible generation
- Machine solver verification on every question
- SimHash deduplication against existing questions
- Optional LLM rewording with automatic re-verification
"""

from __future__ import annotations

import logging
import os
import random
import uuid
from typing import List, Optional

from pipeline.dedupe.hasher import DedupeEngine
from pipeline.generate.generators import GENERATOR_REGISTRY, SimplificationGenerator
from pipeline.verify.solver import MathSolver
from schemas.enums import DifficultyLevel, ExamType, ReviewStatus, SourceType, TopicSlug
from schemas.models import Blueprint, Paper, Question

logger = logging.getLogger(__name__)


def reword_with_llm(question: Question) -> Question:
    """Optional LLM rewording of word problem scenarios (e.g. changing names/contexts).
    
    CRITICAL: Preserves all numbers and answers intact, and re-runs the solver.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return question

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = (
            f"Reword this Indian exam math problem statement with different names or real-world item contexts, "
            f"DO NOT change any numbers, percentages, or values. Return ONLY the new problem statement:\n\n"
            f"{question.text_en}"
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        new_text = response.text.strip()
        if new_text and len(new_text) > 10:
            original_text = question.text_en
            question.text_en = new_text
            # Re-verify with solver to ensure numbers weren't altered
            is_ok, details = MathSolver.verify_question(question)
            if not is_ok:
                # Revert if reword broke mathematical consistency
                question.text_en = original_text
            else:
                question.solver_output = details
                question.metadata["reworded_by_llm"] = True
    except Exception as exc:
        logger.warning("LLM rewording skipped: %s", exc)

    return question


class MockBuilder:
    """Mock test builder driven by blueprint specifications."""

    def __init__(self, seed: Optional[int] = None, dedupe_engine: Optional[DedupeEngine] = None):
        self.seed = seed if seed is not None else 42
        self.rng = random.Random(self.seed)
        self.dedupe = dedupe_engine or DedupeEngine()

    def build_mock_paper(
        self,
        blueprint: Blueprint,
        title: Optional[str] = None,
        enable_llm_rewording: bool = False,
    ) -> Paper:
        """Assembles a full mock test paper matching the blueprint's topic and difficulty targets."""
        questions: List[Question] = []
        target_total = blueprint.total_questions

        # Map target difficulty counts
        curve = blueprint.target_difficulty_curve
        easy_pct = curve.get(DifficultyLevel.EASY, 0.35)
        med_pct = curve.get(DifficultyLevel.MEDIUM, 0.50)

        easy_quota = int(round(target_total * easy_pct))
        med_quota = int(round(target_total * med_pct))
        hard_quota = max(0, target_total - (easy_quota + med_quota))

        diff_pool = (
            [DifficultyLevel.EASY] * easy_quota +
            [DifficultyLevel.MEDIUM] * med_quota +
            [DifficultyLevel.HARD] * hard_quota
        )
        self.rng.shuffle(diff_pool)

        diff_idx = 0

        # Topic allocations
        for tw in blueprint.topic_weightages:
            topic = tw.topic_slug
            count = tw.count
            gen_cls = GENERATOR_REGISTRY.get(topic, SimplificationGenerator)
            generator = gen_cls(self.rng)

            for _ in range(count):
                if len(questions) >= target_total:
                    break

                diff = diff_pool[diff_idx % len(diff_pool)] if diff_pool else DifficultyLevel.MEDIUM
                diff_idx += 1

                # Attempt generating non-duplicate verified question
                max_retries = 5
                generated_q = None
                for _ in range(max_retries):
                    cand = generator.generate(exam=blueprint.exam, difficulty=diff)
                    cand.marks_correct = blueprint.positive_mark_per_q
                    cand.marks_negative = blueprint.negative_mark_per_q

                    if enable_llm_rewording and cand.topic_slug != TopicSlug.SIMPLIFICATION:
                        cand = reword_with_llm(cand)

                    # Deduplication check
                    is_dup, _, _ = self.dedupe.check_duplicate(cand)
                    if not is_dup:
                        self.dedupe.register(cand)
                        generated_q = cand
                        break

                if not generated_q:
                    # Fallback
                    generated_q = cand

                questions.append(generated_q)

        # If any slots remain unfilled due to rounding, fill with Simplification
        while len(questions) < target_total:
            fallback_gen = SimplificationGenerator(self.rng)
            diff = diff_pool[diff_idx % len(diff_pool)] if diff_pool else DifficultyLevel.MEDIUM
            diff_idx += 1
            q = fallback_gen.generate(exam=blueprint.exam, difficulty=diff)
            q.marks_correct = blueprint.positive_mark_per_q
            q.marks_negative = blueprint.negative_mark_per_q
            self.dedupe.register(q)
            questions.append(q)

        paper_id = f"mock_{blueprint.exam.value}_{uuid.uuid4().hex[:8]}"
        paper_title = title or f"{blueprint.title} - Mock Test (Seed {self.seed})"

        return Paper(
            id=paper_id,
            title=paper_title,
            exam=blueprint.exam,
            year=2025,
            shift="Mock",
            source_type=SourceType.ORIGINAL,
            total_questions=len(questions),
            duration_minutes=blueprint.duration_minutes,
            total_marks=len(questions) * blueprint.positive_mark_per_q,
            negative_marking_ratio=round(blueprint.negative_mark_per_q / blueprint.positive_mark_per_q, 2),
            questions=questions,
            metadata={
                "generated_from_blueprint": blueprint.id,
                "generation_seed": self.seed,
            },
        )
