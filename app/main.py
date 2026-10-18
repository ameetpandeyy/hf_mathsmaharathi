"""FastAPI application for Maths Maharathi pipeline service."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.auth import verify_admin_auth
from app.admin_ui import build_gradio_app, HAS_GRADIO
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
from schemas.models import Blueprint, ContentPack, Paper, Question, ReviewItem

logger = logging.getLogger("maths_maharathi_api")

app = FastAPI(
    title="Maths Maharathi AI Pipeline API",
    description="PYQ analysis, pattern discovery, machine-verified mock generation, and content pack exports.",
    version="1.0.0",
)

# In-memory application state stores (can be backed by Supabase / Postgres)
_PAPERS_DB: Dict[str, Paper] = {}
_QUESTIONS_DB: Dict[str, Question] = {}
_BLUEPRINTS_DB: Dict[str, Blueprint] = {}
_REVIEW_MANAGER = ReviewManager()
_DEDUPE_ENGINE = DedupeEngine()
_EXPORTER = SupabaseExporter()


class GenerateRequest(BaseModel):
    exam: ExamType
    blueprint_id: Optional[str] = None
    count: Optional[int] = None
    seed: int = 42
    enable_llm_rewording: bool = False


class ReviewRequest(BaseModel):
    status: ReviewStatus
    reviewer_id: str = "admin_reviewer"
    notes: Optional[str] = None
    flagged_reasons: List[str] = Field(default_factory=list)
    rights_cleared: Optional[bool] = None


class ExportRequest(BaseModel):
    exam: ExamType
    version: str = "1.0.0"
    title: str = "Maths Maharathi Release Pack"
    push_to_supabase: bool = False
    enforce_approval: bool = True


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "maths-maharathi-pipeline",
        "papers_count": len(_PAPERS_DB),
        "questions_count": len(_QUESTIONS_DB),
    }


@app.post("/ingest", response_model=Dict[str, Any])
async def ingest_paper(
    file: UploadFile = File(...),
    exam: ExamType = Form(...),
    year: int = Form(...),
    shift: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    admin: str = Depends(verify_admin_auth),
):
    """Ingests previous year question paper, splits into questions, classifies, and verifies."""
    suffix = Path(file.filename or "paper.pdf").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        # 1. Ingest raw text with OCR fallback if necessary
        doc_data = PaperIngestor.load_document(tmp_path)
        full_text = doc_data["full_text"]

        # 2. Parse into bilingual questions
        parsed_questions = BilingualPaperParser.parse_paper_text(
            text=full_text,
            exam=exam,
            year=year,
            shift=shift,
            source_url=source_url,
        )

        # 3. Classify and verify each question
        processed_questions: List[Question] = []
        for q in parsed_questions:
            # Topic classification & difficulty
            q = QuestionClassifier.classify_question(q)
            
            # Solver verification
            is_ok, details = MathSolver.verify_question(q)
            q.machine_verified = is_ok
            q.solver_output = details

            # Register in dedupe & review queue
            _DEDUPE_ENGINE.register(q)
            _REVIEW_MANAGER.register_question(q)
            _QUESTIONS_DB[q.id] = q
            processed_questions.append(q)

        paper_id = f"paper_{exam.value}_{year}_{len(_PAPERS_DB) + 1}"
        paper = Paper(
            id=paper_id,
            title=f"{exam.value.upper()} {year} {shift or ''}".strip(),
            exam=exam,
            year=year,
            shift=shift,
            source_url=source_url,
            source_type=SourceType.PYQ_REFERENCE,
            total_questions=len(processed_questions),
            total_marks=len(processed_questions) * 2.0,
            questions=processed_questions,
        )
        _PAPERS_DB[paper_id] = paper

        return {
            "status": "success",
            "paper_id": paper_id,
            "questions_extracted": len(processed_questions),
            "machine_verified_count": sum(1 for q in processed_questions if q.machine_verified),
            "legal_guardrail": {
                "source_type": SourceType.PYQ_REFERENCE.value,
                "rights_cleared": False,
                "export_eligible": False,
                "policy": "PYQ reference questions are retained strictly for statistical analysis and solver training. Verbatim publishing blocked.",
            },
        }
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.get("/papers", response_model=List[Dict[str, Any]])
def list_papers(admin: str = Depends(verify_admin_auth)):
    """Lists all ingested and generated test papers."""
    return [
        {
            "id": p.id,
            "title": p.title,
            "exam": p.exam,
            "year": p.year,
            "shift": p.shift,
            "source_type": p.source_type,
            "total_questions": p.total_questions,
            "duration_minutes": p.duration_minutes,
        }
        for p in _PAPERS_DB.values()
    ]


@app.get("/questions", response_model=List[Question])
def list_questions(
    exam: Optional[ExamType] = Query(None),
    topic_slug: Optional[TopicSlug] = Query(None),
    difficulty: Optional[DifficultyLevel] = Query(None),
    source_type: Optional[SourceType] = Query(None),
    review_status: Optional[ReviewStatus] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    admin: str = Depends(verify_admin_auth),
):
    """Retrieves questions with multi-attribute filtering."""
    results: List[Question] = []
    for q in _QUESTIONS_DB.values():
        if exam and q.exam != exam:
            continue
        if topic_slug and q.topic_slug != topic_slug:
            continue
        if difficulty and q.difficulty != difficulty:
            continue
        if source_type and q.source_type != source_type:
            continue
        if review_status and q.review_status != review_status:
            continue
        results.append(q)
        if len(results) >= limit:
            break
    return results


@app.post("/analyse", response_model=Blueprint)
def analyse_pattern(
    exam: ExamType = Query(...),
    paper_id: Optional[str] = Query(None),
    admin: str = Depends(verify_admin_auth),
):
    """Analyzes question patterns for an exam or specific paper and generates a Blueprint."""
    if paper_id:
        if paper_id not in _PAPERS_DB:
            raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
        target_paper = _PAPERS_DB[paper_id]
        bp = PatternAnalyzer.analyze_paper(target_paper)
    else:
        # Collect all questions matching exam
        matching = [q for q in _QUESTIONS_DB.values() if q.exam == exam]
        bp = PatternAnalyzer.analyze_questions(questions=matching, exam=exam)

    _BLUEPRINTS_DB[bp.id] = bp
    return bp


@app.post("/generate", response_model=Dict[str, Any])
def generate_mock(
    request: GenerateRequest,
    admin: str = Depends(verify_admin_auth),
):
    """Generates a new, original, solver-verified mock paper matching an exam blueprint."""
    if request.blueprint_id:
        if request.blueprint_id not in _BLUEPRINTS_DB:
            raise HTTPException(status_code=404, detail=f"Blueprint {request.blueprint_id} not found")
        bp = _BLUEPRINTS_DB[request.blueprint_id]
    else:
        # Default blueprint for exam
        bp = PatternAnalyzer.analyze_questions(questions=[], exam=request.exam)

    if request.count:
        bp.total_questions = request.count

    builder = MockBuilder(seed=request.seed, dedupe_engine=_DEDUPE_ENGINE)
    mock_paper = builder.build_mock_paper(
        blueprint=bp,
        enable_llm_rewording=request.enable_llm_rewording,
    )

    # Store generated questions and paper
    for q in mock_paper.questions:
        _QUESTIONS_DB[q.id] = q
        _REVIEW_MANAGER.register_question(q)

    _PAPERS_DB[mock_paper.id] = mock_paper

    return {
        "status": "success",
        "mock_paper_id": mock_paper.id,
        "title": mock_paper.title,
        "total_questions": mock_paper.total_questions,
        "machine_verified_count": sum(1 for q in mock_paper.questions if q.machine_verified),
        "source_type": SourceType.ORIGINAL.value,
        "legal_clearance": "Eligible for publishing once approved by human reviewer",
    }


@app.post("/review/{question_id}", response_model=Dict[str, Any])
def review_question(
    question_id: str,
    request: ReviewRequest,
    admin: str = Depends(verify_admin_auth),
):
    """Updates review status, notes, and rights clearance for a question."""
    if question_id not in _QUESTIONS_DB:
        raise HTTPException(status_code=404, detail=f"Question {question_id} not found")

    q = _QUESTIONS_DB[question_id]

    if request.status == ReviewStatus.APPROVED:
        q = _REVIEW_MANAGER.approve_question(question_id, request.reviewer_id, request.notes)
    elif request.status == ReviewStatus.REJECTED:
        q = _REVIEW_MANAGER.reject_question(question_id, request.reviewer_id, request.flagged_reasons, request.notes)
    else:
        q.review_status = request.status
        q.reviewer_notes = request.notes

    if request.rights_cleared is not None:
        q.rights_cleared = request.rights_cleared

    return {
        "status": "success",
        "question_id": q.id,
        "review_status": q.review_status.value,
        "rights_cleared": q.rights_cleared,
        "export_eligible": q.is_export_eligible(),
    }


@app.post("/export", response_model=Dict[str, Any])
def export_content_pack(
    request: ExportRequest,
    admin: str = Depends(verify_admin_auth),
):
    """Packages approved, solver-verified questions into a versioned content pack."""
    candidate_questions = [q for q in _QUESTIONS_DB.values() if q.exam == request.exam]
    candidate_papers = [p for p in _PAPERS_DB.values() if p.exam == request.exam]

    pack_id = f"pack_{request.exam.value}"
    pack, stats = ContentPackBuilder.build_pack(
        pack_id=pack_id,
        version=request.version,
        exam=request.exam,
        title=request.title,
        candidate_questions=candidate_questions,
        papers=candidate_papers,
        enforce_approval=request.enforce_approval,
    )

    # Save locally to output folder
    export_dir = Path("exports")
    local_path = _EXPORTER.export_pack_to_file(pack, export_dir)

    supabase_result = None
    if request.push_to_supabase:
        supabase_result = _EXPORTER.push_to_supabase(pack)

    return {
        "status": "success",
        "pack_id": pack.pack_id,
        "version": pack.version,
        "checksum_sha256": pack.checksum_sha256,
        "exported_questions_count": pack.question_count,
        "local_file": str(local_path),
        "audit_stats": stats,
        "supabase_sync": supabase_result or "skipped",
    }


# Mount Gradio Admin Dashboard on /admin if installed
if HAS_GRADIO:
    try:
        import gradio as gr
        admin_dashboard = build_gradio_app()
        if admin_dashboard:
            app = gr.mount_gradio_app(app, admin_dashboard, path="/admin")
    except Exception as e:
        logger.warning("Could not mount Gradio dashboard: %s", e)

