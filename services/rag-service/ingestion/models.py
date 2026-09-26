"""Typed data models for the RAG ingestion pipeline.

These models are the Single Source of Truth for document identity,
metadata, and chunk structure across all pipeline stages.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Layer 1: Document Identity
# ---------------------------------------------------------------------------

@dataclass
class DocumentIdentity:
    """Globally unique document identity — scoped by namespace."""

    doc_number: str         # Raw legal number, e.g. "01/2023/TT-BTP"
    namespace: str          # Domain scope, e.g. "Linh_vuc_BTP"
    content_hash: str       # MD5 of file bytes
    file_name: str          # Original filename
    rel_path: str           # Relative path from SOURCE_DIR
    override_doc_id: str = ""  # Explicit canonical doc_id override

    @property
    def doc_id(self) -> str:
        """Globally unique: namespace/doc_number (or namespace/filename fallback)."""
        if self.override_doc_id:
            return self.override_doc_id
        if self.doc_number and (
            re.match(r'^\d+/', self.doc_number)
            or re.match(r'^(?:QCVN|TCVN|TCXD|TCXDVN|APPENDIX|PL)', self.doc_number, re.IGNORECASE)
        ):
            raw = f"{self.namespace}/{self.doc_number}"
        else:
            clean_fn = os.path.splitext(self.file_name)[0].replace(' ', '_')
            if self.doc_number:
                raw = f"{self.namespace}/{self.doc_number}_{clean_fn}"
            else:
                raw = f"{self.namespace}/{clean_fn}"
        # Sanitize for Neo4j/PostgreSQL safety
        return re.sub(r'[^\w\d\-_/.]', '_', raw)


# ---------------------------------------------------------------------------
# Layer 2: Document Metadata
# ---------------------------------------------------------------------------

@dataclass
class DocumentMetadata:
    """Extracted metadata for a document."""

    date: str = "unknown"
    doc_type: str = "unknown"
    authority: str = "unknown"
    doc_number: str = ""
    validity_status: str = "ACTIVE"
    legal_level: str = "UNKNOWN"
    discipline: str = "UNKNOWN"
    project_code: str = "GENERIC"
    doc_status: str = "ACTIVE"
    revision: int = 0
    file_name: str = ""
    source_category: str = "KHAC"

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "type": self.doc_type,
            "authority": self.authority,
            "doc_number": self.doc_number,
            "validity_status": self.validity_status,
            "legal_level": self.legal_level,
            "discipline": self.discipline,
            "project_code": self.project_code,
            "doc_status": self.doc_status,
            "revision": self.revision,
            "file_name": self.file_name,
            "source_category": self.source_category,
        }

    def update_from_dict(self, d: dict):
        """Merge non-empty values from a dict (e.g. LLM refinement)."""
        for key, val in d.items():
            if val and str(val).lower() not in ("unknown", "n/a", "none"):
                mapped = {
                    "type": "doc_type", "doc_date": "date",
                }.get(key, key)
                if hasattr(self, mapped):
                    setattr(self, mapped, val)


# ---------------------------------------------------------------------------
# Layer 3: Chunks
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A single chunk of text with identity and metadata."""

    text: str
    source: str           # Filename
    page: int
    chunk_type: str = "parent"   # "parent" | "child" | "table"
    is_table: bool = False
    parent_id: str = ""
    hierarchy_path: str = ""
    bbox: list = field(default_factory=lambda: [0, 0, 1000, 1000])
    synthetic_queries: str = ""

    # Identity fields — set centrally by orchestrator
    doc_id: str = ""
    doc_number: str = ""
    chunk_id: str = ""
    validity_status: str = "ACTIVE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "page": self.page,
            "chunk_type": self.chunk_type,
            "is_table": self.is_table,
            "parent_id": self.parent_id,
            "hierarchy_path": self.hierarchy_path,
            "bbox": self.bbox,
            "synthetic_queries": self.synthetic_queries,
            "doc_id": self.doc_id,
            "doc_number": self.doc_number,
            "chunk_id": self.chunk_id,
            "validity_status": self.validity_status,
        }


# ---------------------------------------------------------------------------
# Layer 4: Relationships
# ---------------------------------------------------------------------------

@dataclass
class DocumentRelationships:
    """Legal relationships extracted from document text."""

    replaces: list[str] = field(default_factory=list)
    amends: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    guides: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "replaces": self.replaces,
            "amends": self.amends,
            "references": self.references,
            "guides": self.guides,
        }


# ---------------------------------------------------------------------------
# Layer 5: Raw extraction result (from OCR/digital)
# ---------------------------------------------------------------------------

@dataclass
class RawPage:
    """Result of extracting a single page from PDF."""

    text: str
    page: int
    is_table: bool = False
    layout: list = field(default_factory=list)
    bbox: list = field(default_factory=list)
    source: str = "digital"
    error: str = ""


# ---------------------------------------------------------------------------
# Aggregate: ProcessedDocument — flows through all stages
# ---------------------------------------------------------------------------

@dataclass
class ProcessedDocument:
    """The complete document state flowing through the pipeline stages.
    
    Each stage reads and enriches this object:
      s01_intake  → identity, raw file info
      s02_ocr     → raw_pages
      s03_metadata → metadata (LLM + regex)
      s04_identity → identity.doc_id finalized
      s05_chunking → chunks
      s06_enrichment → summary, relationships, synthetic_queries
      s07_embedding → embeddings (stored in chunks)
      s08_indexing → indexed to Milvus + Neo4j
      s09_export → exported to JSON/Markdown
    """

    identity: DocumentIdentity
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
    raw_pages: list[RawPage] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    relationships: DocumentRelationships = field(default_factory=DocumentRelationships)
    summary: str = ""

    # Processing state
    file_path: str = ""
    failed_pages: list[int] = field(default_factory=list)
    stage: str = "intake"
