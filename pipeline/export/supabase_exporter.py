"""Supabase database and storage exporter for Maths Maharathi."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from schemas.models import ContentPack

logger = logging.getLogger(__name__)


class SupabaseExporter:
    """Exports versioned content packs and individual tables to Supabase and local storage."""

    def __init__(self, supabase_url: Optional[str] = None, service_key: Optional[str] = None):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.service_key = service_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    def export_pack_to_file(self, pack: ContentPack, output_dir: Path) -> Path:
        """Saves content pack JSON and checksum to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"{pack.pack_id}_v{pack.version}.json"
        
        pack_data = pack.model_dump(mode="json")
        file_path.write_text(json.dumps(pack_data, indent=2, ensure_ascii=False), encoding="utf-8")
        
        # Write checksum file
        chk_path = output_dir / f"{pack.pack_id}_v{pack.version}.sha256"
        chk_path.write_text(f"{pack.checksum_sha256}  {file_path.name}\n", encoding="utf-8")
        
        return file_path

    def push_to_supabase(self, pack: ContentPack) -> Dict[str, Any]:
        """Pushes pack rows into mock_papers, mock_questions, and content_packs tables."""
        if not self.supabase_url or not self.service_key:
            return {
                "status": "dry_run",
                "message": "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured; dry-run mode active",
                "pack_id": pack.pack_id,
                "version": pack.version,
                "questions_count": pack.question_count,
                "checksum": pack.checksum_sha256,
            }

        try:
            import requests

            headers = {
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation,resolution=merge-duplicates",
            }

            # 1. Fetch exam UUID from exams table
            exam_resp = requests.get(
                f"{self.supabase_url}/rest/v1/exams?slug=eq.{pack.exam.value}&select=id",
                headers=headers,
                timeout=10,
            )
            exam_id = None
            if exam_resp.ok and exam_resp.json():
                exam_id = exam_resp.json()[0]["id"]

            # 2. Fetch topic UUIDs map from topics table
            topic_resp = requests.get(
                f"{self.supabase_url}/rest/v1/topics?select=id,slug",
                headers=headers,
                timeout=10,
            )
            topic_map = {}
            if topic_resp.ok and topic_resp.json():
                for t in topic_resp.json():
                    topic_map[t["slug"]] = t["id"]
            default_topic_id = list(topic_map.values())[0] if topic_map else None

            # 3. Upsert content_packs record matching table schema
            pack_record = {
                "pack_id": f"{pack.pack_id}_v{pack.version}",
                "type": "exam_mocks",
                "version": pack.version,
                "exam_slug": pack.exam.value,
                "storage_path": f"exports/{pack.pack_id}_v{pack.version}.json",
                "checksum": pack.checksum_sha256,
                "min_app_version": "1.0.0",
                "question_count": pack.question_count,
                "metadata": {
                    "title": pack.title,
                    "created_at": pack.created_at,
                },
                "status": "published",
            }
            requests.post(
                f"{self.supabase_url}/rest/v1/content_packs",
                headers=headers,
                json=pack_record,
                timeout=10,
            )

            # 4. Insert mock_papers if exam_id is resolved
            paper_id_map = {}
            if exam_id and pack.papers:
                for paper in pack.papers:
                    paper_payload = {
                        "exam_id": exam_id,
                        "title": paper.title,
                        "year": paper.year or 2025,
                        "shift": paper.shift or "Daily Mock",
                        "source_type": "original",
                        "total_questions": paper.total_questions,
                        "duration_minutes": paper.duration_minutes,
                        "total_marks": paper.total_marks,
                        "negative_marking_ratio": paper.negative_marking_ratio,
                        "is_free": True,
                        "is_published": True,
                    }
                    p_resp = requests.post(
                        f"{self.supabase_url}/rest/v1/mock_papers",
                        headers=headers,
                        json=paper_payload,
                        timeout=10,
                    )
                    if p_resp.ok and p_resp.json():
                        paper_id_map[paper.id] = p_resp.json()[0]["id"]

            # 5. Insert questions into mock_questions
            questions_inserted = 0
            if pack.questions and topic_map:
                questions_batch = []
                for q in pack.questions:
                    t_id = topic_map.get(q.topic_slug.value, default_topic_id)
                    if not t_id:
                        continue
                    
                    options_dict = {
                        opt.key: opt.text_en for opt in q.options
                    }
                    q_payload = {
                        "topic_id": t_id,
                        "text_en": q.text_en,
                        "text_hi": q.text_hi or q.text_en,
                        "options": options_dict,
                        "correct_option": q.correct_option,
                        "solution_steps": [{"step": 1, "explanation": q.explanation_en or ""}],
                        "shortcut_trick": q.shortcut_trick or "",
                        "difficulty": q.difficulty.value,
                        "target_seconds": q.target_seconds,
                        "marks_correct": q.marks_correct,
                        "marks_negative": q.marks_negative,
                        "source_type": "original",
                        "rights_cleared": True,
                        "verified": q.machine_verified,
                        "solver_output": q.solver_output or {},
                        "dedupe_hash": q.dedupe_hash,
                        "is_published": True,
                    }
                    questions_batch.append(q_payload)

                if questions_batch:
                    q_resp = requests.post(
                        f"{self.supabase_url}/rest/v1/mock_questions",
                        headers=headers,
                        json=questions_batch,
                        timeout=15,
                    )
                    if q_resp.ok:
                        questions_inserted = len(questions_batch)

            return {
                "status": "success",
                "pack_id": pack.pack_id,
                "version": pack.version,
                "questions_pushed": questions_inserted,
                "papers_pushed": len(paper_id_map),
            }
        except Exception as exc:
            logger.error("Failed to push pack to Supabase: %s", exc)
            return {
                "status": "error",
                "message": str(exc),
                "pack_id": pack.pack_id,
            }
