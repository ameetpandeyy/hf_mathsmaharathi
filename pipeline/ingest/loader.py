"""PDF and image document ingestion with OCR fallback and page cleanup."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Optional library detection
try:
    try:
        import pymupdf as fitz  # Modern PyMuPDF API
    except ImportError:
        import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


class DocumentIngestionError(Exception):
    """Raised when paper ingestion fails."""
    pass


class PaperIngestor:
    """Handles raw paper ingestion from PDF or image files with OCR fallback."""

    HEADER_FOOTER_PATTERNS = [
        r"Page\s+\d+\s+of\s+\d+",
        r"Staff\s+Selection\s+Commission",
        r"Combined\s+Graduate\s+Level\s+Exam.*",
        r"Institute\s+of\s+Banking\s+Personnel\s+Selection",
        r"Railway\s+Recruitment\s+Board.*",
        r"Roll\s+No[:\s]+[A-Za-z0-9\-]+",
        r"Candidate\s+Name[:\s]+.*",
        r"Test\s+Date[:\s]+.*",
        r"Test\s+Time[:\s]+.*",
        r"Subject[:\s]+Quantitative\s+Aptitude.*",
        r"DO\s+NOT\s+OPEN\s+THIS\s+BOOKLET.*",
    ]

    @classmethod
    def clean_page_text(cls, text: str) -> str:
        """Removes exam headers, footers, roll numbers, and watermarks."""
        lines = text.splitlines()
        cleaned_lines: List[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Check against recurring headers/footers
            is_header = any(re.search(pat, stripped, re.IGNORECASE) for pat in cls.HEADER_FOOTER_PATTERNS)
            if not is_header:
                cleaned_lines.append(stripped)
        return "\n".join(cleaned_lines)

    @classmethod
    def extract_text_from_pdf(cls, file_path: Path) -> List[Dict[str, Any]]:
        """Extracts text per page from PDF using PyMuPDF or pdfplumber."""
        pages_content: List[Dict[str, Any]] = []

        if HAS_PYMUPDF:
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                raw_text = page.get_text()
                if not raw_text.strip() and HAS_OCR:
                    # Run OCR on page pixmap if blank
                    pix = page.get_pixmap()
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    raw_text = pytesseract.image_to_string(img, lang="eng+hin")

                cleaned = cls.clean_page_text(raw_text)
                pages_content.append({
                    "page_number": page_num + 1,
                    "raw_text": raw_text,
                    "cleaned_text": cleaned,
                })
            doc.close()
            return pages_content

        elif HAS_PDFPLUMBER:
            with pdfplumber.open(file_path) as pdf:
                for idx, page in enumerate(pdf.pages):
                    raw_text = page.extract_text() or ""
                    cleaned = cls.clean_page_text(raw_text)
                    pages_content.append({
                        "page_number": idx + 1,
                        "raw_text": raw_text,
                        "cleaned_text": cleaned,
                    })
            return pages_content

        else:
            # Fallback for plain text or environment without C-bindings
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                return [{
                    "page_number": 1,
                    "raw_text": content,
                    "cleaned_text": cls.clean_page_text(content),
                }]
            except Exception as e:
                raise DocumentIngestionError(f"Cannot parse file without PDF libraries or text fallback: {e}")

    @classmethod
    def load_document(cls, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Loads and processes document into structured page extracts."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found at {path}")

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            pages = cls.extract_text_from_pdf(path)
        elif suffix in (".png", ".jpg", ".jpeg"):
            if HAS_OCR:
                img = Image.open(path)
                raw_text = pytesseract.image_to_string(img, lang="eng+hin")
                pages = [{
                    "page_number": 1,
                    "raw_text": raw_text,
                    "cleaned_text": cls.clean_page_text(raw_text),
                }]
            else:
                pages = [{
                    "page_number": 1,
                    "raw_text": "",
                    "cleaned_text": "",
                    "error": "OCR engine (pytesseract/Tesseract) not installed",
                }]
        elif suffix in (".txt", ".json", ".md"):
            raw_text = path.read_text(encoding="utf-8", errors="ignore")
            pages = [{
                "page_number": 1,
                "raw_text": raw_text,
                "cleaned_text": cls.clean_page_text(raw_text),
            }]
        else:
            raise DocumentIngestionError(f"Unsupported document format: {suffix}")

        full_cleaned = "\n\n".join(p["cleaned_text"] for p in pages if p.get("cleaned_text"))
        return {
            "file_name": path.name,
            "total_pages": len(pages),
            "pages": pages,
            "full_text": full_cleaned,
        }
