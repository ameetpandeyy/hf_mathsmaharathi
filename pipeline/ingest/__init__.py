"""Ingestion module."""

from pipeline.ingest.loader import PaperIngestor, DocumentIngestionError

__all__ = ["PaperIngestor", "DocumentIngestionError"]
