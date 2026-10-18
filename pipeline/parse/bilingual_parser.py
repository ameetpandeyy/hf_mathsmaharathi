"""Bilingual question paper parser for Maths Maharathi.

Splits extracted exam text into structured Question objects:
- English and Hindi text separation
- Options extraction (A, B, C, D)
- Answer key and step-by-step solutions
- Preserves math expressions as Unicode and LaTeX
- Flags tables, charts, or figure dependencies
- Enforces strict legal provenance: source_type='pyq_reference', rights_cleared=False
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from schemas.enums import DifficultyLevel, ExamType, ReviewStatus, SourceType, TopicSlug
from schemas.models import Option, Question


# Regex patterns for question detection and option matching
QUESTION_START_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:Q(?:uestion)?\.?\s*(\d+)|\((\d+)\)|(\d+)\.)\s*[:\-\)]?\s*",
    re.IGNORECASE,
)
OPTION_PATTERN = re.compile(
    r"(?:^|\s)(?:\(?([A-Da-d1-4])\)|\b([A-Da-d1-4])\.)\s+([^\n\(\)A-D1-4]+)",
)
ANSWER_KEY_PATTERN = re.compile(
    r"(?:Ans(?:wer)?|Correct\s+Option|उत्तर)[:\s]+(?:\(?([A-Da-d1-4])\)|\b([A-Da-d1-4])\b)",
    re.IGNORECASE,
)
SOLUTION_PATTERN = re.compile(
    r"(?:Solution|Explanation|हल)[:\s]+([\s\S]+?)(?=(?:\n\s*(?:Q(?:uestion)?\.?\s*\d+|\(\d+\)|\d+\.)|$))",
    re.IGNORECASE,
)


def standardize_latex_math(text: str) -> str:
    """Standardizes mathematical notation into clean Unicode / LaTeX formatting."""
    t = text
    # Exponents: x^2, y^3
    t = re.sub(r"(\w+)\^(\d+)", r"\1^{\2}", t)
    # Square roots: sqrt(x) -> \sqrt{x}
    t = re.sub(r"sqrt\((.*?)\)", r"\\sqrt{\1}", t, flags=re.IGNORECASE)
    # Fractions: a/b when surrounded by parens -> \frac{a}{b}
    t = re.sub(r"\((\d+)\/(\d+)\)", r"\\frac{\1}{\2}", t)
    # Standard multiplication and division signs
    t = t.replace("*", " × ").replace("/", " ÷ ")
    # Clean up redundant spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t


def split_bilingual_text(text: str) -> Tuple[str, Optional[str]]:
    """Splits English and Hindi content when delimited by '/', '\\n\\n', or Devanagari blocks."""
    # Check for explicit '/' separator between languages
    if " / " in text:
        parts = text.split(" / ", 1)
        return parts[0].strip(), parts[1].strip()

    # Check for Devanagari Unicode range: \u0900-\u097F
    devanagari_chars = re.findall(r"[\u0900-\u097F]", text)
    if devanagari_chars:
        # Separate blocks with Latin chars from blocks with Devanagari
        lines = text.splitlines()
        en_lines = []
        hi_lines = []
        for line in lines:
            if re.search(r"[\u0900-\u097F]", line):
                hi_lines.append(line.strip())
            else:
                en_lines.append(line.strip())
        en_str = " ".join(en_lines).strip()
        hi_str = " ".join(hi_lines).strip() if hi_lines else None
        return en_str if en_str else text.strip(), hi_str

    return text.strip(), None


class BilingualPaperParser:
    """Parses raw text papers into structured, provenance-tagged Question records."""

    @classmethod
    def parse_options(cls, raw_options_block: str) -> List[Option]:
        """Extracts options from an option text block."""
        options: List[Option] = []
        # Mapping 1-4 to A-D if numerical
        num_to_letter = {"1": "A", "2": "B", "3": "C", "4": "D"}

        matches = OPTION_PATTERN.findall(raw_options_block)
        for opt_match in matches:
            opt_id = (opt_match[0] or opt_match[1]).upper()
            opt_id = num_to_letter.get(opt_id, opt_id)
            val_text = opt_match[2].strip()
            en_val, hi_val = split_bilingual_text(val_text)
            options.append(
                Option(
                    id=opt_id,
                    text_en=en_val,
                    text_hi=hi_val,
                    latex=standardize_latex_math(en_val) if any(c in en_val for c in "+-×÷=^") else None,
                )
            )

        # Fallback if regex missed single line options
        if len(options) < 2:
            lines = raw_options_block.splitlines()
            for line in lines:
                l = line.strip()
                m = re.match(r"^[\(\[]?([A-Da-d1-4])[\)\]\.\s]+(.*)", l)
                if m:
                    opt_id = m.group(1).upper()
                    opt_id = num_to_letter.get(opt_id, opt_id)
                    opt_val = m.group(2).strip()
                    en_val, hi_val = split_bilingual_text(opt_val)
                    if not any(o.id == opt_id for o in options):
                        options.append(
                            Option(
                                id=opt_id,
                                text_en=en_val,
                                text_hi=hi_val,
                                latex=standardize_latex_math(en_val),
                            )
                        )

        # Sort options by ID (A, B, C, D)
        return sorted(options, key=lambda o: o.id)

    @classmethod
    def parse_paper_text(
        cls,
        text: str,
        exam: ExamType,
        year: Optional[int] = None,
        shift: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> List[Question]:
        """Parses full paper text into Question models."""
        questions: List[Question] = []
        
        # Split text into chunks using question numbering
        splits = list(QUESTION_START_PATTERN.finditer(text))
        if not splits:
            return questions

        for i in range(len(splits)):
            start_pos = splits[i].end()
            end_pos = splits[i + 1].start() if i + 1 < len(splits) else len(text)
            q_chunk = text[start_pos:end_pos].strip()

            # Extract answer key
            ans_match = ANSWER_KEY_PATTERN.search(q_chunk)
            correct_opt = "A"
            if ans_match:
                key_raw = (ans_match.group(1) or ans_match.group(2)).upper()
                correct_opt = {"1": "A", "2": "B", "3": "C", "4": "D"}.get(key_raw, key_raw)
                body_before_ans = q_chunk[: ans_match.start()]
            else:
                body_before_ans = q_chunk

            # Extract solution if present
            sol_match = SOLUTION_PATTERN.search(q_chunk)
            solution_en = None
            solution_hi = None
            if sol_match:
                sol_raw = sol_match.group(1).strip()
                solution_en, solution_hi = split_bilingual_text(sol_raw)

            # Check for table or figure dependencies
            has_table = bool(re.search(r"(?:table|chart|graph|figure|diagram|तालिका|चित्र)", body_before_ans, re.IGNORECASE))

            # Split question stem and options
            # Options typically start with A) or (A) or 1)
            first_opt_match = re.search(r"(?:^|\n)\s*(?:\(?([A-Da-d1-4])\)|\b([A-Da-d1-4])\.)\s+", body_before_ans)
            if first_opt_match:
                q_stem = body_before_ans[: first_opt_match.start()].strip()
                opts_block = body_before_ans[first_opt_match.start() :].strip()
            else:
                q_stem = body_before_ans.strip()
                opts_block = ""

            options = cls.parse_options(opts_block)
            if len(options) < 2:
                # Provide standard fallback choices if parsing failed to extract all options
                options = [
                    Option(id="A", text_en="Data Insufficient / Missing Option A"),
                    Option(id="B", text_en="Data Insufficient / Missing Option B"),
                ]

            q_en, q_hi = split_bilingual_text(q_stem)
            q_id = f"pyq_{exam.value}_{year or 'unknown'}_{uuid.uuid4().hex[:8]}"

            question = Question(
                id=q_id,
                # STRICT LEGAL GUARDRAIL
                source_type=SourceType.PYQ_REFERENCE,
                rights_cleared=False,
                exam=exam,
                year=year,
                shift=shift,
                source_url=source_url,
                text_en=q_en if q_en else "Unparsed question statement",
                text_hi=q_hi,
                options=options,
                correct_option=correct_opt,
                solution_en=solution_en,
                solution_hi=solution_hi,
                topic_slug=TopicSlug.SIMPLIFICATION,  # Placeholder before classifier step
                difficulty=DifficultyLevel.MEDIUM,
                target_seconds=45,
                review_status=ReviewStatus.DRAFT,
                metadata={
                    "has_table_or_figure": has_table,
                    "raw_length": len(q_chunk),
                },
            )
            question.dedupe_hash = question.calculate_dedupe_hash()
            questions.append(question)

        return questions
