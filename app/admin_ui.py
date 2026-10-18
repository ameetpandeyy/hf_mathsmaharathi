"""Gradio Admin CRM & Operator Dashboard for Maths Maharathi.

Enables non-technical editorial reviewers and administrators to:
1. Upload and ingest previous-year papers with immediate bilingual preview.
2. Inspect empirical topic weightages and difficulty curves.
3. Generate machine-verified original mock tests deterministically.
4. Review questions, flag mathematical discrepancies, and toggle legal rights clearance.
5. Export versioned, checksummed content packs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import gradio as gr
    HAS_GRADIO = True
except ImportError:
    HAS_GRADIO = False

from pipeline.analyse.pattern_analyzer import PatternAnalyzer
from pipeline.classify.classifier import QuestionClassifier
from pipeline.dedupe.hasher import DedupeEngine
from pipeline.export.pack_builder import ContentPackBuilder
from pipeline.export.supabase_exporter import SupabaseExporter
from pipeline.generate.builder import MockBuilder
from pipeline.ingest.loader import PaperIngestor
from pipeline.parse.bilingual_parser import BilingualPaperParser
from pipeline.review.manager import ReviewManager
from pipeline.verify.solver import MathSolver
from schemas.enums import DifficultyLevel, ExamType, ReviewStatus, SourceType, TopicSlug
from schemas.models import Blueprint, Paper, Question

# Shared in-memory dashboard state
dashboard_papers: Dict[str, Paper] = {}
dashboard_questions: Dict[str, Question] = {}
dashboard_blueprints: Dict[str, Blueprint] = {}
dashboard_review = ReviewManager()
dashboard_dedupe = DedupeEngine()
dashboard_exporter = SupabaseExporter()


def handle_ingest(file_obj, exam_val: str, year_val: int, shift_val: str, source_url: str):
    """Processes uploaded paper document."""
    if not file_obj:
        return "Please upload a paper file (PDF, TXT, or Image).", []
    
    exam = ExamType(exam_val)
    path = Path(file_obj.name)
    doc_data = PaperIngestor.load_document(path)
    
    parsed_q = BilingualPaperParser.parse_paper_text(
        text=doc_data["full_text"],
        exam=exam,
        year=int(year_val),
        shift=shift_val or None,
        source_url=source_url or None,
    )

    verified_cnt = 0
    records = []
    for q in parsed_q:
        q = QuestionClassifier.classify_question(q)
        is_ok, details = MathSolver.verify_question(q)
        q.machine_verified = is_ok
        q.solver_output = details
        if is_ok:
            verified_cnt += 1
        
        dashboard_dedupe.register(q)
        dashboard_review.register_question(q)
        dashboard_questions[q.id] = q

        records.append([
            q.id,
            q.text_en[:60] + "...",
            q.topic_slug.value,
            q.difficulty.value,
            q.correct_option,
            "✅ Verified" if q.machine_verified else "⚠️ Pending Review",
            q.source_type.value,
            "False (Protected)" if not q.rights_cleared else "True (Cleared)",
        ])

    paper_id = f"paper_{exam.value}_{year_val}"
    paper = Paper(
        id=paper_id,
        title=f"{exam.value.upper()} {year_val} {shift_val or ''}",
        exam=exam,
        year=int(year_val),
        shift=shift_val,
        source_type=SourceType.PYQ_REFERENCE,
        total_questions=len(parsed_q),
        total_marks=len(parsed_q) * 2.0,
        questions=parsed_q,
    )
    dashboard_papers[paper_id] = paper

    summary = (
        f"### Paper Ingested Successfully\n"
        f"- **Paper ID**: `{paper_id}`\n"
        f"- **Questions Extracted**: {len(parsed_q)}\n"
        f"- **Machine Verified**: {verified_cnt}\n"
        f"- **Legal Status**: `source_type: pyq_reference` (NEVER published to content packs by default)\n"
    )
    return summary, records


def handle_analyse(exam_val: str):
    """Analyzes patterns and generates Blueprint."""
    exam = ExamType(exam_val)
    matching = [q for q in dashboard_questions.values() if q.exam == exam]
    bp = PatternAnalyzer.analyze_questions(questions=matching, exam=exam)
    dashboard_blueprints[bp.id] = bp

    rows = []
    for tw in bp.topic_weightages:
        rows.append([
            tw.topic_slug.value,
            tw.count,
            f"{tw.percentage}%",
            f"{tw.avg_target_seconds}s",
        ])

    diff_summary = ", ".join([f"{k.value}: {round(v*100)}%" for k, v in bp.target_difficulty_curve.items()])
    summary = (
        f"### Blueprint: {bp.title}\n"
        f"- **Total Questions**: {bp.total_questions}\n"
        f"- **Duration**: {bp.duration_minutes} mins\n"
        f"- **Marking Scheme**: +{bp.positive_mark_per_q} / -{bp.negative_mark_per_q}\n"
        f"- **Difficulty Mix**: {diff_summary}\n"
    )
    return summary, rows


def handle_generate(exam_val: str, q_count: int, seed: int):
    """Generates mock test based on blueprint."""
    exam = ExamType(exam_val)
    bp = PatternAnalyzer.analyze_questions(questions=[], exam=exam)
    bp.total_questions = int(q_count)

    builder = MockBuilder(seed=int(seed), dedupe_engine=dashboard_dedupe)
    mock = builder.build_mock_paper(blueprint=bp)
    
    dashboard_papers[mock.id] = mock
    rows = []
    for q in mock.questions:
        dashboard_questions[q.id] = q
        dashboard_review.register_question(q)
        rows.append([
            q.id,
            q.text_en[:70] + "...",
            q.topic_slug.value,
            q.difficulty.value,
            q.correct_option,
            "✅ Verified" if q.machine_verified else "❌ Mismatch",
            q.source_type.value,
        ])

    summary = (
        f"### Generated Mock: {mock.title}\n"
        f"- **Paper ID**: `{mock.id}`\n"
        f"- **Questions**: {mock.total_questions}\n"
        f"- **Deterministic Seed**: `{seed}`\n"
        f"- **Source Provenance**: `original` (Eligible for packs once approved)\n"
    )
    return summary, rows


def handle_review(q_id: str, action: str, reviewer_name: str, notes: str, rights_flag: bool):
    """Applies review action to question."""
    if q_id not in dashboard_questions:
        return f"Error: Question `{q_id}` not found."

    q = dashboard_questions[q_id]
    if action == "Approve":
        dashboard_review.approve_question(q_id, reviewer_name or "admin", notes)
    elif action == "Reject":
        dashboard_review.reject_question(q_id, reviewer_name or "admin", ["Reviewer flagged"], notes)

    q.rights_cleared = bool(rights_flag)
    eligible = q.is_export_eligible()

    return (
        f"Updated Question `{q.id}`:\n"
        f"- Status: **{q.review_status.value.upper()}**\n"
        f"- Rights Cleared: `{q.rights_cleared}`\n"
        f"- Export Eligible: **{eligible}**\n"
        f"- Notes: {q.reviewer_notes or 'None'}"
    )


def handle_export(exam_val: str, version: str):
    """Builds content pack and reports legal compliance audit."""
    exam = ExamType(exam_val)
    candidates = [q for q in dashboard_questions.values() if q.exam == exam]
    papers = [p for p in dashboard_papers.values() if p.exam == exam]

    pack, stats = ContentPackBuilder.build_pack(
        pack_id=f"pack_{exam.value}",
        version=version or "1.0.0",
        exam=exam,
        title=f"Maths Maharathi {exam.value.upper()} Pack",
        candidate_questions=candidates,
        papers=papers,
        enforce_approval=True,
    )

    export_path = dashboard_exporter.export_pack_to_file(pack, Path("exports"))

    summary = (
        f"### Content Pack v{pack.version} Export Complete\n"
        f"- **Pack File**: `{export_path.name}`\n"
        f"- **SHA-256 Checksum**: `{pack.checksum_sha256}`\n"
        f"- **Questions Published**: **{pack.question_count}**\n\n"
        f"#### Legal & Quality Gate Audit:\n"
        f"- Total Candidates Inspected: {stats['total_candidates']}\n"
        f"- 🚫 Blocked PYQ Reference (No Rights Cleared): **{stats['blocked_pyq_copyright']}**\n"
        f"- 🚫 Blocked Unverified (Solver Failed): **{stats['blocked_unverified']}**\n"
        f"- 🚫 Blocked Unapproved (Pending Review): **{stats['blocked_unapproved']}**\n"
        f"- ✅ Eligible & Published: **{stats['eligible']}**\n"
    )
    return summary


def build_gradio_app():
    """Constructs the Gradio interface."""
    if not HAS_GRADIO:
        return None

    with gr.Blocks(title="Maths Maharathi - AI Content & Exam Pipeline") as demo:
        gr.Markdown("# ⚔️ Maths Maharathi - Exam Pipeline & Content Ops")
        gr.Markdown("Extract PYQs, analyze blueprints, generate machine-verified mocks, and export legal content packs.")

        with gr.Tab("1. Ingest Papers"):
            with gr.Row():
                with gr.Column():
                    file_input = gr.File(label="Upload Paper (PDF, TXT, Images)")
                    exam_select = gr.Dropdown(choices=[e.value for e in ExamType], value="ssc_cgl", label="Target Exam")
                    year_input = gr.Number(value=2023, label="Year")
                    shift_input = gr.Textbox(value="Shift 1", label="Shift")
                    url_input = gr.Textbox(value="", label="Source Provenance URL (Optional)")
                    ingest_btn = gr.Button("Ingest & Process Paper", variant="primary")
                with gr.Column():
                    ingest_summary = gr.Markdown()
                    ingest_table = gr.Dataframe(
                        headers=["ID", "Question", "Topic", "Diff", "Ans", "Solver", "Source", "Rights"],
                        label="Extracted Questions Preview",
                    )
            ingest_btn.click(
                handle_ingest,
                inputs=[file_input, exam_select, year_input, shift_input, url_input],
                outputs=[ingest_summary, ingest_table],
            )

        with gr.Tab("2. Pattern Blueprints"):
            with gr.Row():
                with gr.Column():
                    bp_exam = gr.Dropdown(choices=[e.value for e in ExamType], value="ssc_cgl", label="Select Exam")
                    analyse_btn = gr.Button("Analyze Exam Patterns", variant="primary")
                with gr.Column():
                    bp_summary = gr.Markdown()
                    bp_table = gr.Dataframe(
                        headers=["Topic", "Question Count", "Weightage %", "Avg Solving Seconds"],
                        label="Topic Distribution",
                    )
            analyse_btn.click(handle_analyse, inputs=[bp_exam], outputs=[bp_summary, bp_table])

        with gr.Tab("3. Mock Generator"):
            with gr.Row():
                with gr.Column():
                    gen_exam = gr.Dropdown(choices=[e.value for e in ExamType], value="ssc_cgl", label="Exam")
                    gen_count = gr.Slider(minimum=5, maximum=50, step=5, value=25, label="Question Count")
                    gen_seed = gr.Number(value=42, label="Deterministic Seed")
                    gen_btn = gr.Button("Generate Verified Mock Test", variant="primary")
                with gr.Column():
                    gen_summary = gr.Markdown()
                    gen_table = gr.Dataframe(
                        headers=["ID", "Stem", "Topic", "Diff", "Key", "Solver Verified", "Source Type"],
                        label="Generated Questions",
                    )
            gen_btn.click(handle_generate, inputs=[gen_exam, gen_count, gen_seed], outputs=[gen_summary, gen_table])

        with gr.Tab("4. Editorial Review & Legal Rights"):
            with gr.Row():
                with gr.Column():
                    rev_qid = gr.Textbox(label="Question ID to Review")
                    rev_action = gr.Radio(choices=["Approve", "Reject"], value="Approve", label="Review Action")
                    rev_name = gr.Textbox(value="editorial_admin", label="Reviewer ID")
                    rev_notes = gr.Textbox(label="Editorial Notes / Feedback")
                    rev_rights = gr.Checkbox(label="Rights Cleared (Mandatory to export pyq_reference)", value=False)
                    rev_submit = gr.Button("Submit Review Decision", variant="primary")
                with gr.Column():
                    rev_result = gr.Markdown()
            rev_submit.click(
                handle_review,
                inputs=[rev_qid, rev_action, rev_name, rev_notes, rev_rights],
                outputs=[rev_result],
            )

        with gr.Tab("5. Content Pack Exporter"):
            with gr.Row():
                with gr.Column():
                    exp_exam = gr.Dropdown(choices=[e.value for e in ExamType], value="ssc_cgl", label="Exam")
                    exp_version = gr.Textbox(value="1.0.0", label="Pack Version")
                    exp_btn = gr.Button("Build & Audit Content Pack", variant="primary")
                with gr.Column():
                    exp_summary = gr.Markdown()
            exp_btn.click(handle_export, inputs=[exp_exam, exp_version], outputs=[exp_summary])

    return demo
