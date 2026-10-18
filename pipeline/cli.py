"""Command-Line Interface (CLI) for running Maths Maharathi pipeline locally."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
from schemas.enums import ExamType, ReviewStatus, SourceType
from schemas.models import Paper, Question


def cmd_ingest(args):
    """CLI ingest command handler."""
    path = Path(args.file)
    if not path.exists():
        print(f"Error: file '{path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading document: {path}...")
    doc = PaperIngestor.load_document(path)
    exam = ExamType(args.exam)

    print(f"Parsing bilingual questions for {exam.value.upper()}...")
    questions = BilingualPaperParser.parse_paper_text(
        text=doc["full_text"],
        exam=exam,
        year=args.year,
        shift=args.shift,
        source_url=args.source_url,
    )

    print(f"Extracted {len(questions)} questions. Classifying and verifying...")
    verified_count = 0
    for q in questions:
        q = QuestionClassifier.classify_question(q)
        is_ok, details = MathSolver.verify_question(q)
        q.machine_verified = is_ok
        q.solver_output = details
        if is_ok:
            verified_count += 1

    paper_id = f"paper_{exam.value}_{args.year}"
    paper = Paper(
        id=paper_id,
        title=f"{exam.value.upper()} {args.year} {args.shift or ''}".strip(),
        exam=exam,
        year=args.year,
        shift=args.shift,
        source_url=args.source_url,
        source_type=SourceType.PYQ_REFERENCE,
        total_questions=len(questions),
        total_marks=len(questions) * 2.0,
        questions=questions,
    )

    out_dir = Path("data/ingested")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{paper_id}.json"
    out_path.write_text(json.dumps(paper.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n[SUCCESS] Ingested paper saved to: {out_path}")
    print(f"  - Total Questions: {len(questions)}")
    print(f"  - Solver Verified: {verified_count}")
    print(f"  - Source Type: {SourceType.PYQ_REFERENCE.value} (PROTECTED: Not published to packs)")


def cmd_analyse(args):
    """CLI pattern analysis command handler."""
    exam = ExamType(args.exam)
    print(f"Analyzing empirical exam patterns for {exam.value.upper()}...")

    # Load any ingested papers if present
    data_dir = Path("data/ingested")
    loaded_questions = []
    if data_dir.exists():
        for f in data_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                paper = Paper.model_validate(data)
                if paper.exam == exam:
                    loaded_questions.extend(paper.questions)
            except Exception:
                pass

    bp = PatternAnalyzer.analyze_questions(questions=loaded_questions, exam=exam)
    bp_dir = Path("data/blueprints")
    bp_dir.mkdir(parents=True, exist_ok=True)
    bp_file = bp_dir / f"blueprint_{exam.value}.json"
    bp_file.write_text(json.dumps(bp.model_dump(mode="json"), indent=2), encoding="utf-8")

    print(f"\n[SUCCESS] Pattern Blueprint derived and saved to: {bp_file}")
    print(f"  - Total Questions: {bp.total_questions}")
    print(f"  - Marking: +{bp.positive_mark_per_q} / -{bp.negative_mark_per_q}")
    print(f"  - Topics Identified: {len(bp.topic_weightages)}")
    for tw in bp.topic_weightages:
        print(f"    * {tw.topic_slug.value:25} : {tw.count} Qs ({tw.percentage}%) | avg {tw.avg_target_seconds}s")


def cmd_generate(args):
    """CLI mock generation command handler."""
    exam = ExamType(args.exam)
    bp_file = Path(f"data/blueprints/blueprint_{exam.value}.json")
    if bp_file.exists():
        bp = PatternAnalyzer.analyze_questions(questions=[], exam=exam)
        try:
            data = json.loads(bp_file.read_text(encoding="utf-8"))
            bp = bp.model_validate(data)
        except Exception:
            pass
    else:
        bp = PatternAnalyzer.analyze_questions(questions=[], exam=exam)

    if args.count:
        bp.total_questions = args.count

    print(f"Generating deterministic mock paper for {exam.value.upper()} (Seed: {args.seed})...")
    builder = MockBuilder(seed=args.seed)
    mock = builder.build_mock_paper(blueprint=bp, enable_llm_rewording=args.reword)

    out_dir = Path("data/generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.output) if args.output else out_dir / f"{mock.id}.json"
    out_path.write_text(json.dumps(mock.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")

    verified_count = sum(1 for q in mock.questions if q.machine_verified)
    print(f"\n[SUCCESS] Mock Paper generated: {out_path}")
    print(f"  - Paper ID: {mock.id}")
    print(f"  - Questions: {len(mock.questions)}")
    print(f"  - Machine Verified: {verified_count}/{len(mock.questions)}")
    print(f"  - Source Provenance: {mock.source_type.value}")


def cmd_export(args):
    """CLI content pack export command handler."""
    exam = ExamType(args.exam)
    print(f"Compiling versioned content pack for {exam.value.upper()} v{args.version}...")

    # Load generated questions
    gen_dir = Path("data/generated")
    questions = []
    papers = []
    if gen_dir.exists():
        for f in gen_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                paper = Paper.model_validate(data)
                if paper.exam == exam:
                    papers.append(paper)
                    for q in paper.questions:
                        # Auto-approve in CLI export if flag specified
                        if args.approve_all:
                            q.review_status = ReviewStatus.APPROVED
                        questions.append(q)
            except Exception:
                pass

    pack, stats = ContentPackBuilder.build_pack(
        pack_id=f"pack_{exam.value}",
        version=args.version,
        exam=exam,
        title=f"Maths Maharathi {exam.value.upper()} Pack",
        candidate_questions=questions,
        papers=papers,
        enforce_approval=not args.approve_all,
    )

    exporter = SupabaseExporter()
    out_dir = Path("exports")
    local_file = exporter.export_pack_to_file(pack, out_dir)

    print(f"\n[SUCCESS] Content Pack exported to: {local_file}")
    print(f"  - Version: {pack.version}")
    print(f"  - SHA-256 Checksum: {pack.checksum_sha256}")
    print(f"  - Questions Published: {pack.question_count}")
    print(f"  - Legal/Quality Audit:")
    print(f"    * Blocked PYQ (Copyright): {stats['blocked_pyq_copyright']}")
    print(f"    * Blocked Unverified:      {stats['blocked_unverified']}")
    print(f"    * Blocked Unapproved:      {stats['blocked_unapproved']}")
    print(f"    * Published:               {stats['eligible']}")


def main():
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="Maths Maharathi AI Exam Pipeline CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest
    ingest_p = subparsers.add_parser("ingest", help="Ingest a previous-year paper")
    ingest_p.add_argument("file", help="Path to PDF, TXT or image file")
    ingest_p.add_argument("--exam", required=True, choices=[e.value for e in ExamType])
    ingest_p.add_argument("--year", type=int, required=True)
    ingest_p.add_argument("--shift", default=None)
    ingest_p.add_argument("--source-url", default=None)
    ingest_p.set_defaults(func=cmd_ingest)

    # Analyse
    analyse_p = subparsers.add_parser("analyse", help="Derive pattern blueprint")
    analyse_p.add_argument("--exam", required=True, choices=[e.value for e in ExamType])
    analyse_p.set_defaults(func=cmd_analyse)

    # Generate
    gen_p = subparsers.add_parser("generate", help="Generate verified mock test")
    gen_p.add_argument("--exam", required=True, choices=[e.value for e in ExamType])
    gen_p.add_argument("--count", type=int, default=25)
    gen_p.add_argument("--seed", type=int, default=42)
    gen_p.add_argument("--reword", action="store_true", help="Enable LLM rewording")
    gen_p.add_argument("--output", default=None)
    gen_p.set_defaults(func=cmd_generate)

    # Export
    export_p = subparsers.add_parser("export", help="Export content pack")
    export_p.add_argument("--exam", required=True, choices=[e.value for e in ExamType])
    export_p.add_argument("--version", default="1.0.0")
    export_p.add_argument("--approve-all", action="store_true", help="Mark all generated questions as approved for test run")
    export_p.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
