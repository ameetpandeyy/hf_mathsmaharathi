"""Unit tests for bilingual paper parser using sample papers."""

from pathlib import Path
from pipeline.parse.bilingual_parser import (
    BilingualPaperParser,
    split_bilingual_text,
    standardize_latex_math,
)
from schemas.enums import ExamType, SourceType


def test_split_bilingual_text():
    """Tests slash-separated and inline bilingual text splitting."""
    en, hi = split_bilingual_text("Find the sum of 10 and 20. / 10 और 20 का योग ज्ञात कीजिए।")
    assert "Find the sum of 10 and 20." in en
    assert "10 और 20 का योग ज्ञात कीजिए।" in hi

    # Pure English
    en_only, hi_none = split_bilingual_text("Evaluate the expression 5 * 10.")
    assert en_only == "Evaluate the expression 5 * 10."
    assert hi_none is None


def test_standardize_latex_math():
    """Tests conversion of common math patterns into LaTeX."""
    out = standardize_latex_math("sqrt(16) + x^2")
    assert "\\sqrt{16}" in out
    assert "x^{2}" in out


def test_parse_golden_sample_papers():
    """Tests parsing across all 5 golden sample exam files."""
    samples = [
        ("samples/ssc_cgl_tier1_2023.txt", ExamType.SSC_CGL),
        ("samples/sbi_po_prelims_2023.txt", ExamType.SBI_PO),
        ("samples/ibps_clerk_prelims_2023.txt", ExamType.IBPS_CLERK),
        ("samples/rrb_ntpc_stage1_2022.txt", ExamType.RRB_NTPC),
        ("samples/ssc_chsl_tier1_2023.txt", ExamType.SSC_CHSL),
    ]

    for rel_path, exam in samples:
        path = Path(rel_path)
        assert path.exists(), f"Sample file {rel_path} must exist"
        text = path.read_text(encoding="utf-8")
        
        questions = BilingualPaperParser.parse_paper_text(
            text=text,
            exam=exam,
            year=2023,
        )
        assert len(questions) == 5, f"Expected 5 questions in {rel_path}, got {len(questions)}"

        for q in questions:
            # Legal provenance check
            assert q.source_type == SourceType.PYQ_REFERENCE
            assert q.rights_cleared is False
            assert len(q.options) >= 2
            assert q.correct_option in ["A", "B", "C", "D"]
            assert len(q.text_en) > 5
