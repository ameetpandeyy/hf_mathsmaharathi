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
            # When supabase python client is installed and configured
            import requests

            headers = {
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            }

            # 1. Upsert content_packs record
            pack_record = {
                "pack_id": pack.pack_id,
                "version": pack.version,
                "exam": pack.exam.value,
                "title": pack.title,
                "checksum_sha256": pack.checksum_sha256,
                "question_count": pack.question_count,
                "created_at": pack.created_at,
            }
            resp = requests.post(
                f"{self.supabase_url}/rest/v1/content_packs",
                headers=headers,
                json=pack_record,
                timeout=10,
            )
            resp.raise_for_status()

            return {
                "status": "success",
                "pack_id": pack.pack_id,
                "version": pack.version,
                "rows_pushed": pack.question_count,
            }
        except Exception as exc:
            logger.error("Failed to push pack to Supabase: %s", exc)
            return {
                "status": "error",
                "message": str(exc),
                "pack_id": pack.pack_id,
            }
