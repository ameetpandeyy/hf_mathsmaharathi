#!/usr/bin/env python3
"""
Maths Maharathi — Heavy Load Batch Pipeline Runner
Designed to run in background cron schedules (e.g. GitHub Actions free runners / Hugging Face cron).
Processes PYQ blueprints, generates verified original mocks, checks mathematical accuracy,
deduplicates question banks, and builds validated offline content packs.

Security Guardrails:
- Zero secrets committed to source. All credentials read strictly from os.environ.
- Operates fully offline if external LLM/Supabase APIs are absent.
- Enforces strict copyright barrier: source_type='pyq_reference' is NEVER exported to content packs.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add parent directory to path so pipeline & schemas can be imported directly
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline.analyse.pattern_analyzer import PatternAnalyzer
from pipeline.classify.classifier import QuestionClassifier
from pipeline.dedupe.hasher import DedupeEngine
from pipeline.export.pack_builder import ContentPackBuilder
from pipeline.export.supabase_exporter import SupabaseExporter
from pipeline.generate.builder import MockBuilder
from pipeline.ingest.loader import PaperIngestor
from pipeline.parse.bilingual_parser import BilingualPaperParser
from pipeline.verify.solver import MathSolver
from schemas.enums import ExamType, ReviewStatus, SourceType
from schemas.models import Blueprint, Paper, Question

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("batch_pipeline_cron")


def run_cron_job():
    start_time = time.time()
    logger.info("=================================================================")
    logger.info("Starting Maths Maharathi Heavy Load Batch Pipeline Execution")
    logger.info("Timestamp: %s UTC", datetime.datetime.now(datetime.timezone.utc).isoformat())
    logger.info("=================================================================")

    # Ensure required data folders exist
    blueprints_dir = REPO_ROOT / "data" / "blueprints"
    generated_dir = REPO_ROOT / "data" / "generated"
    exports_dir = REPO_ROOT / "exports"
    logs_dir = REPO_ROOT / "logs"

    for directory in [blueprints_dir, generated_dir, exports_dir, logs_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    summary = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "exams_processed": [],
        "total_generated": 0,
        "total_verified": 0,
        "total_deduped": 0,
        "total_exported": 0,
        "status": "SUCCESS",
    }

    # Step 1: Ingest and analyze available sample papers if blueprints are missing
    samples_dir = REPO_ROOT / "samples"
    if samples_dir.exists():
        for sample_file in samples_dir.glob("*.txt"):
            stem = sample_file.stem.lower()
            if "ssc_chsl" in stem:
                exam = ExamType.SSC_CHSL
            elif "ssc_cgl" in stem:
                exam = ExamType.SSC_CGL
            elif "sbi_po" in stem:
                exam = ExamType.SBI_PO
            elif "sbi_clerk" in stem:
                exam = ExamType.SBI_CLERK
            elif "ibps_clerk" in stem:
                exam = ExamType.IBPS_CLERK
            elif "ibps_po" in stem:
                exam = ExamType.IBPS_PO
            elif "rrb_ntpc" in stem:
                exam = ExamType.RRB_NTPC
            elif "rrb_group_d" in stem:
                exam = ExamType.RRB_GROUP_D
            else:
                exam = ExamType.SSC_CGL

            bp_file = blueprints_dir / f"{exam.value}_blueprint.json"
            if not bp_file.exists():
                logger.info("Blueprint missing for %s. Analyzing sample %s...", exam.value, sample_file.name)
                try:
                    text = sample_file.read_text(encoding="utf-8")
                    questions = BilingualPaperParser.parse_paper_text(
                        text=text,
                        exam=exam,
                        year=2023,
                        shift="Batch Cron Analysis",
                    )
                    paper = Paper(
                        id=f"sample_{sample_file.stem}",
                        title=f"{exam.value.upper()} Sample Reference",
                        exam=exam,
                        year=2023,
                        questions=questions,
                    )
                    bp = PatternAnalyzer.analyze_paper(paper)
                    bp_file.write_text(bp.model_dump_json(indent=2), encoding="utf-8")
                    logger.info("Saved blueprint for %s with %d topic weightages.", exam.value, len(bp.topic_weightages))
                except Exception as exc:
                    logger.warning("Could not derive blueprint from %s: %s", sample_file.name, exc)

    # Step 2: Determine target exams to process
    target_exams = [
        (ExamType.SSC_CGL, 25),
        (ExamType.SSC_CHSL, 25),
        (ExamType.IBPS_PO, 35),
        (ExamType.SBI_PO, 35),
        (ExamType.SBI_CLERK, 35),
        (ExamType.RRB_NTPC, 30),
    ]

    exam_filter = os.environ.get("EXAM_FILTER", "all").strip().lower()
    if exam_filter != "all":
        target_exams = [
            item for item in target_exams
            if item[0].value == exam_filter or exam_filter in item[0].value
        ]

    use_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    logger.info("Gemini LLM API: %s", "ENABLED (Key detected)" if use_gemini else "OFFLINE TEMPLATES (No key provided)")

    all_papers: list[Paper] = []
    global_dedupe = DedupeEngine()

    for exam, target_count in target_exams:
        logger.info("--- Processing Exam: %s (Target: %d questions) ---", exam.value.upper(), target_count)
        seed = int(time.time()) % 100000 + target_count

        bp_file = blueprints_dir / f"{exam.value}_blueprint.json"
        if bp_file.exists():
            try:
                bp = Blueprint.model_validate_json(bp_file.read_text(encoding="utf-8"))
            except Exception:
                bp = PatternAnalyzer.analyze_questions(questions=[], exam=exam)
        else:
            bp = PatternAnalyzer.analyze_questions(questions=[], exam=exam)

        bp.total_questions = target_count

        builder = MockBuilder(seed=seed, dedupe_engine=global_dedupe)
        paper = builder.build_mock_paper(
            blueprint=bp,
            title=f"{exam.value.upper()} Daily Speed Mock (Batch {datetime.datetime.now().strftime('%Y%m%d')})",
            enable_llm_rewording=use_gemini,
        )

        # Step 3: SymPy Math Proofing & Machine Verification
        verified_in_paper = 0
        deduped_questions = []
        dupe_count = 0
        seen_in_paper = set()

        for q in paper.questions:
            q = QuestionClassifier.classify_question(q)
            is_ok, solver_details = MathSolver.verify_question(q)
            q.machine_verified = is_ok
            q.solver_output = solver_details
            if is_ok:
                verified_in_paper += 1

            h = q.calculate_dedupe_hash()
            if h in seen_in_paper:
                dupe_count += 1
            else:
                seen_in_paper.add(h)
                deduped_questions.append(q)

        paper.questions = deduped_questions
        paper.total_questions = len(deduped_questions)

        # Save paper to data/generated
        gen_path = generated_dir / f"{paper.id}.json"
        gen_path.write_text(paper.model_dump_json(indent=2), encoding="utf-8")

        all_papers.append(paper)
        summary["total_generated"] += len(paper.questions)
        summary["total_verified"] += verified_in_paper
        summary["total_deduped"] += dupe_count
        summary["exams_processed"].append({
            "exam": exam.value,
            "questions": len(paper.questions),
            "verified": verified_in_paper,
            "duplicates_purged": dupe_count,
        })
        logger.info("Generated %d questions (%d verified, %d duplicates purged)", len(paper.questions), verified_in_paper, dupe_count)

    # Step 4: Build Content Pack for Each Exam
    for exam, _ in target_exams:
        exam_papers = [p for p in all_papers if p.exam == exam]
        if not exam_papers:
            continue

        exam_questions = []
        for p in exam_papers:
            for q in p.questions:
                # Mark generated original verified questions as approved for distribution
                if q.machine_verified and q.source_type == SourceType.ORIGINAL:
                    q.review_status = ReviewStatus.APPROVED
                exam_questions.append(q)

        version_str = datetime.datetime.now(datetime.timezone.utc).strftime("1.%Y%m%d.%H%M")
        pack, stats = ContentPackBuilder.build_pack(
            pack_id=f"pack_{exam.value}",
            version=version_str,
            exam=exam,
            title=f"Maths Maharathi {exam.value.upper()} Daily Pack",
            candidate_questions=exam_questions,
            papers=exam_papers,
            enforce_approval=True,
        )

        exporter = SupabaseExporter()
        export_file = exporter.export_pack_to_file(pack, exports_dir)
        summary["total_exported"] += pack.question_count

        if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
            push_res = exporter.push_to_supabase(pack)
            logger.info("Supabase push result for %s: %s", exam.value, push_res.get("status"))

        logger.info("Exported Pack for %s: %s (Questions: %d, SHA-256: %s)", exam.value, export_file.name, pack.question_count, pack.checksum_sha256[:12])
        logger.info("  Copyright Legal Gate: %d PYQ questions blocked, %d unverified blocked.", stats.get("blocked_pyq_copyright", 0), stats.get("blocked_unverified", 0))

    duration = round(time.time() - start_time, 2)
    summary["duration_seconds"] = duration
    logger.info("=================================================================")
    logger.info("Batch Pipeline Completed Successfully in %s seconds", duration)
    logger.info("Summary: %d generated, %d verified, %d exported across %d exams", summary["total_generated"], summary["total_verified"], summary["total_exported"], len(summary["exams_processed"]))
    logger.info("=================================================================")

    # Write execution log summary
    summary_path = logs_dir / "last_cron_run.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    try:
        run_cron_job()
    except Exception as e:
        logger.exception("Critical error in batch pipeline cron: %s", e)
        sys.exit(1)
