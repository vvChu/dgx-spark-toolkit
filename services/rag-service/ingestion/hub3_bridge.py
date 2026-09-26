"""Bridge module connecting Hub 3 OKF v2.4 Gazette Bundles to the Ingestion Pipeline.

Implements ADR-0047 SSOT (Catalog discovery and relation reconciliation),
ADR-0059 Legal Verbatim Grounding (cryptographic SHA-256 provenance verification),
Bidirectional ID Resolver for Luật/QCVN/TCVN, clean markdown extraction,
fast-path chunking into ProcessedDocument, Neo4j topology synchronization,
and IngestionQueue integration.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from ingestion.chunking import DocumentChunker
from ingestion.models import (
    Chunk,
    DocumentIdentity,
    DocumentMetadata,
    DocumentRelationships,
    ProcessedDocument,
    RawPage,
)
from ingestion.pipeline_config import HUB3_LEGAL_PATH

logger = logging.getLogger(__name__)

# Buffer size for streaming SHA-256 hashing (64KB as required by ADR-0059)
SHA256_BUFFER_SIZE: int = 64 * 1024


class ShaVerificationStatus(str, Enum):
    """Cryptographic SHA-256 verification status per ADR-0059."""

    VERIFIED = "VERIFIED"
    TAMPERED = "TAMPERED"
    NO_SOURCE = "NO_SOURCE"
    NON_STATUTORY = "NON_STATUTORY"


@dataclass
class Hub3BundleInfo:
    """Canonical representation of an OKF v2.4 legal knowledge bundle."""

    slug: str
    category: str
    registry_id: str
    document_number: str
    title: str
    doc_type: str
    issued_by: str
    issued_date: str
    effective_date: str
    status: str
    validity_status: str
    bundle_path: str
    bundle_dir: str
    markdown_path: str
    pdf_path: Optional[str] = None
    pdf_sha256: Optional[str] = None
    sha_status: str = ShaVerificationStatus.NO_SOURCE.value
    replaces: List[str] = field(default_factory=list)
    canonical_replaces: List[str] = field(default_factory=list)
    amends: List[str] = field(default_factory=list)
    canonical_amends: List[str] = field(default_factory=list)
    amendments: List[Dict[str, Any]] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    guided_by: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    canonical_id: str = ""
    file_name: str = ""
    namespace: str = "VBPL"
    is_statutory: bool = True

    @property
    def is_verified(self) -> bool:
        """Whether the bundle PDF has been verified cryptographically."""
        return self.sha_status == ShaVerificationStatus.VERIFIED.value


class Hub3Bridge:
    """Orchestrates Hub 3 Gazette Bundle discovery, verification, and ingestion."""

    def __init__(self, hub3_path: Optional[str] = None) -> None:
        """Initialize Hub3Bridge with root path of Hub 3 legal knowledge repository.

        Args:
            hub3_path: Root path to ccba-legal-knowledge repository.
                Defaults to HUB3_LEGAL_PATH config constant.
        """
        self.hub3_path = Path(hub3_path or HUB3_LEGAL_PATH).resolve()

    def load_master_catalog(
        self,
        category: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Hub3BundleInfo]:
        """Load Master Catalog legal_registry.yaml and merge with bundle metadata.yaml.

        Follows ADR-0047 Single Source of Truth: legal_registry.yaml holds the
        authoritative catalog and cross-bundle relations (replaces, amends),
        while individual metadata.yaml files provide local bundle properties.

        Args:
            category: Optional category filter (e.g. '01_vbpl', '02_qcvn', '03_tcvn').
            limit: Optional maximum number of bundles to return.

        Returns:
            List of Hub3BundleInfo sorted deterministically by slug (ADR-0058 / Inode Invariance).
        """
        registry_path = self.hub3_path / "legal_registry.yaml"
        registry_data: Dict[str, Any] = {}
        if registry_path.is_file():
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry_data = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("Could not read legal_registry.yaml at %s: %s", registry_path, e)

        # Index registry items by bundle_path, id, and document_number
        registry_items: List[Dict[str, Any]] = (
            registry_data.get("laws", [])
            + registry_data.get("standards", [])
        )
        if isinstance(registry_data.get("documents"), list):
            registry_items.extend(registry_data["documents"])

        registry_index: Dict[str, Dict[str, Any]] = {}
        for item in registry_items:
            bp = item.get("bundle_path")
            if bp:
                norm_bp = bp.strip("/").replace("\\", "/")
                registry_index[norm_bp] = item
                slug_part = norm_bp.split("/")[-1]
                registry_index[slug_part] = item
            item_id = item.get("id")
            if item_id:
                registry_index[item_id] = item
            doc_num = item.get("document_number")
            if doc_num:
                registry_index[doc_num] = item

        # Scan filesystem for bundles under legal_docs/
        legal_docs_root = self.hub3_path / "legal_docs"
        bundle_dirs: List[Path] = []
        if legal_docs_root.is_dir():
            for cat_dir in legal_docs_root.iterdir():
                if cat_dir.is_dir() and not cat_dir.name.startswith("."):
                    for b_dir in cat_dir.iterdir():
                        if b_dir.is_dir() and not b_dir.name.startswith("."):
                            bundle_dirs.append(b_dir)

        # Filesystem Inode Ordering Invariance: sort by slug deterministically
        bundle_dirs.sort(key=lambda p: p.name)

        bundles: List[Hub3BundleInfo] = []
        for b_dir in bundle_dirs:
            cat_name = b_dir.parent.name
            slug = b_dir.name

            if category and cat_name != category:
                continue

            # Read bundle local metadata.yaml
            meta_path = b_dir / "metadata.yaml"
            local_meta: Dict[str, Any] = {}
            if meta_path.is_file():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        local_meta = yaml.safe_load(f) or {}
                except Exception as e:
                    logger.warning("Could not read %s: %s", meta_path, e)

            # Match with Master Catalog registry item
            rel_bundle_path = f"legal_docs/{cat_name}/{slug}"
            reg_item = (
                registry_index.get(rel_bundle_path)
                or registry_index.get(slug)
                or registry_index.get(local_meta.get("id", ""))
                or registry_index.get(local_meta.get("document_number", ""))
                or {}
            )

            # Merge fields: Master Catalog takes priority for relations and SSOT status
            doc_number = (
                local_meta.get("document_number")
                or reg_item.get("document_number")
                or slug
            )
            title = local_meta.get("title") or reg_item.get("title") or slug
            doc_type = (
                local_meta.get("type")
                or reg_item.get("type")
                or local_meta.get("document_type")
                or "unknown"
            )
            issued_by = local_meta.get("issued_by") or reg_item.get("issued_by") or "unknown"
            issued_date = str(local_meta.get("issued_date") or reg_item.get("issued_date") or "")
            effective_date = str(local_meta.get("effective_date") or reg_item.get("effective_date") or "")

            raw_status = str(reg_item.get("status") or local_meta.get("status") or "active").lower()
            validity_status = "OUTDATED" if raw_status in ("expired", "outdated", "superseded") else "ACTIVE"

            # Reconcile relations (replaces, amends, guided_by)
            replaces_set: Set[str] = set()
            # 1. From Registry
            reg_replaces = reg_item.get("relations", {}).get("replaces") if isinstance(reg_item.get("relations"), dict) else None
            if reg_replaces:
                if isinstance(reg_replaces, list):
                    replaces_set.update(str(r) for r in reg_replaces if r)
                else:
                    replaces_set.add(str(reg_replaces))
            # 2. From Local metadata
            local_replaces = local_meta.get("replaces")
            if local_replaces:
                if isinstance(local_replaces, list):
                    replaces_set.update(str(r) for r in local_replaces if r)
                else:
                    replaces_set.add(str(local_replaces))

            replaces = sorted(replaces_set)

            # Amends reconciliation
            amends_set: Set[str] = set()
            reg_amends = reg_item.get("relations", {}).get("amends") if isinstance(reg_item.get("relations"), dict) else None
            if reg_amends:
                if isinstance(reg_amends, list):
                    amends_set.update(str(a) for a in reg_amends if a)
                else:
                    amends_set.add(str(reg_amends))
            local_amends = local_meta.get("amends")
            if local_amends:
                if isinstance(local_amends, list):
                    amends_set.update(str(a) for a in local_amends if a)
                else:
                    amends_set.add(str(local_amends))

            amends = sorted(amends_set)

            # Amendments (e.g. SD1 for QCVN 06 or QCVN 04)
            amendments: List[Dict[str, Any]] = local_meta.get("amendments") or []
            if not isinstance(amendments, list):
                amendments = []

            references: List[str] = []
            local_legal_basis = local_meta.get("legal_basis")
            if isinstance(local_legal_basis, list):
                references.extend(str(r) for r in local_legal_basis if r)

            guided_by = None
            if isinstance(reg_item.get("relations"), dict):
                guided_by = reg_item["relations"].get("guided_by")

            # Locate Markdown file: prioritize {slug}.md, fallback to first non-index md
            md_path = b_dir / f"{slug}.md"
            if not md_path.is_file():
                candidate_mds = sorted([f for f in b_dir.iterdir() if f.is_file() and f.suffix == ".md" and f.name != "index.md"])
                md_path = candidate_mds[0] if candidate_mds else (b_dir / f"{slug}.md")

            # PDF and SHA-256
            pdf_rel = reg_item.get("pdf_path") or local_meta.get("pdf_path")
            pdf_sha256 = (
                reg_item.get("pdf_sha256")
                or local_meta.get("pdf_sha256")
                or (
                    reg_item.get("source_assets", {}).get("pdf", {}).get("sha256")
                    if isinstance(reg_item.get("source_assets"), dict)
                    else None
                )
                or (
                    local_meta.get("source_assets", {}).get("pdf", {}).get("sha256")
                    if isinstance(local_meta.get("source_assets"), dict)
                    else None
                )
            )

            # Determine statutory status
            is_statutory = cat_name != "04_appendices" and doc_type != "Phụ lục đối chiếu"

            # Derive canonical ID and filename
            canonical_id = self._compute_canonical_id(doc_number, slug)
            file_name = Path(pdf_rel).name if pdf_rel else f"{slug}.pdf"

            combined_raw = {**local_meta, **reg_item}

            bundle_info = Hub3BundleInfo(
                slug=slug,
                category=cat_name,
                registry_id=str(reg_item.get("id") or local_meta.get("id") or slug),
                document_number=doc_number,
                title=title,
                doc_type=doc_type,
                issued_by=issued_by,
                issued_date=issued_date,
                effective_date=effective_date,
                status=raw_status,
                validity_status=validity_status,
                bundle_path=f"legal_docs/{cat_name}/{slug}/",
                bundle_dir=str(b_dir),
                markdown_path=str(md_path),
                pdf_path=pdf_rel,
                pdf_sha256=str(pdf_sha256).strip() if pdf_sha256 else None,
                sha_status=ShaVerificationStatus.NON_STATUTORY.value if not is_statutory else ShaVerificationStatus.NO_SOURCE.value,
                replaces=replaces,
                amends=amends,
                amendments=amendments,
                references=references,
                guided_by=str(guided_by) if guided_by else None,
                raw_metadata=combined_raw,
                canonical_id=canonical_id,
                file_name=file_name,
                namespace="VBPL",
                is_statutory=is_statutory,
            )
            bundles.append(bundle_info)

        bundles.sort(key=lambda b: b.slug)

        # Pre-resolve all cross-bundle relationships using Bidirectional ID Resolver
        canonical_map = self.build_canonical_id_map(bundles)
        for b in bundles:
            resolved_replaces = set()
            for r in b.replaces:
                resolved_replaces.add(self.resolve_canonical_id(r, canonical_map))
            b.canonical_replaces = sorted(resolved_replaces)

            resolved_amends = set()
            for a in b.amends:
                resolved_amends.add(self.resolve_canonical_id(a, canonical_map))
            for amd in b.amendments:
                amd_id = amd.get("id") if isinstance(amd, dict) else str(amd)
                if amd_id:
                    resolved_amends.add(self.resolve_canonical_id(amd_id, canonical_map))
            b.canonical_amends = sorted(resolved_amends)

        if limit:
            bundles = bundles[:limit]
        return bundles

    def verify_bundle_sha256(self, bundle: Hub3BundleInfo) -> str:
        """Verify cryptographic SHA-256 hash of bundle source PDF using 64KB streaming.

        Complies with ADR-0059 Legal Verbatim Grounding.

        Args:
            bundle: Hub3BundleInfo instance.

        Returns:
            Status string: VERIFIED, TAMPERED, NO_SOURCE, or NON_STATUTORY.
        """
        if not bundle.is_statutory:
            bundle.sha_status = ShaVerificationStatus.NON_STATUTORY.value
            return bundle.sha_status

        expected_hash = bundle.pdf_sha256
        if not expected_hash or not bundle.pdf_path:
            bundle.sha_status = ShaVerificationStatus.NO_SOURCE.value
            return bundle.sha_status

        # Resolve full path to PDF file
        pdf_file = Path(bundle.pdf_path)
        if not pdf_file.is_absolute():
            pdf_file = self.hub3_path / bundle.pdf_path

        if not pdf_file.is_file():
            # Try within bundle sources/ folder
            fallback_sources = Path(bundle.bundle_dir) / "sources" / Path(bundle.pdf_path).name
            if fallback_sources.is_file():
                pdf_file = fallback_sources
            else:
                bundle.sha_status = ShaVerificationStatus.NO_SOURCE.value
                return bundle.sha_status

        # Streaming 64KB calculation
        h = hashlib.sha256()
        try:
            with open(pdf_file, "rb") as f:
                while chunk := f.read(SHA256_BUFFER_SIZE):
                    h.update(chunk)
            calc_hash = h.hexdigest().lower()
            if calc_hash == expected_hash.strip().lower():
                bundle.sha_status = ShaVerificationStatus.VERIFIED.value
            else:
                bundle.sha_status = ShaVerificationStatus.TAMPERED.value
                logger.error(
                    "SHA-256 MISMATCH for %s: expected %s, calculated %s",
                    bundle.slug,
                    expected_hash,
                    calc_hash,
                )
        except Exception as e:
            logger.error("Failed to read PDF file for SHA-256 verification %s: %s", pdf_file, e)
            bundle.sha_status = ShaVerificationStatus.NO_SOURCE.value

        return bundle.sha_status

    def clean_markdown_frontmatter(self, text: str) -> str:
        """Strip YAML frontmatter block from start of Markdown document.

        Matches block starting with '---' and ending with '---'.

        Args:
            text: Raw markdown content.

        Returns:
            Clean markdown text without frontmatter.
        """
        if not text:
            return ""
        # Strip UTF-8 BOM if present
        text = text.lstrip("\ufeff")
        # Match opening '---' followed by content and closing '---'
        return re.sub(r"^---\s*[\r\n]+.*?[\r\n]+---\s*[\r\n]*", "", text, flags=re.DOTALL).lstrip()

    def build_canonical_id_map(self, bundles: List[Hub3BundleInfo]) -> Dict[str, str]:
        """Build bidirectional mapping from all document aliases to canonical doc_id.

        Sorts input bundles by slug to ensure 100% deterministic output invariant (RULE 5).

        Args:
            bundles: List of Hub3BundleInfo instances.

        Returns:
            Dict mapping aliases (doc_number, slug, registry_id, filename, normalized)
            to canonical doc_id.
        """
        # Filesystem Inode Ordering Invariance: sort bundles deterministically
        sorted_bundles = sorted(bundles, key=lambda b: b.slug)
        mapping: Dict[str, str] = {}

        for b in sorted_bundles:
            cid = b.canonical_id
            if not cid:
                continue

            # Core identities
            mapping[cid] = cid
            if b.document_number:
                mapping[b.document_number] = cid
                mapping[b.document_number.strip()] = cid
                mapping[b.document_number.lower()] = cid
                mapping[b.document_number.upper()] = cid

            if b.slug:
                mapping[b.slug] = cid
                mapping[b.slug.lower()] = cid
                mapping[b.slug.replace("_", "-")] = cid
                mapping[b.slug.replace("-", "_")] = cid

            if b.registry_id:
                mapping[b.registry_id] = cid
                mapping[b.registry_id.lower()] = cid

            if b.file_name:
                mapping[b.file_name] = cid
                mapping[b.file_name.lower()] = cid
                stem = Path(b.file_name).stem
                mapping[stem] = cid
                mapping[stem.lower()] = cid

            # Normalized variants (removing special characters)
            norm_num = re.sub(r"[^\w\d]", "", b.document_number).lower()
            if norm_num:
                mapping[norm_num] = cid

            norm_slug = re.sub(r"[^\w\d]", "", b.slug).lower()
            if norm_slug:
                mapping[norm_slug] = cid

            # Legacy composite ID with filename fallback
            clean_fn = Path(b.file_name).stem.replace(" ", "_")
            legacy_id = f"{b.namespace}/{b.document_number}_{clean_fn}"
            legacy_sanitized = re.sub(r"[^\w\d\-_/.]", "_", legacy_id)
            mapping[legacy_sanitized] = cid

        return mapping

    def resolve_canonical_id(
        self,
        identifier: str,
        canonical_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """Resolve any document identifier variant to its canonical doc_id.

        Args:
            identifier: Raw document identifier, slug, number, or path.
            canonical_map: Optional lookup map from build_canonical_id_map.

        Returns:
            Canonical doc_id string (e.g. 'VBPL/QCVN_06_2022/BXD', 'VBPL/55/2024/QH15').
        """
        if not identifier:
            return ""

        clean = str(identifier).strip()
        if canonical_map:
            # Direct match
            if clean in canonical_map:
                return canonical_map[clean]
            # Lowercase match
            if clean.lower() in canonical_map:
                return canonical_map[clean.lower()]
            # Hyphen/underscore swap
            swapped = clean.replace("-", "_")
            if swapped in canonical_map:
                return canonical_map[swapped]
            swapped_dash = clean.replace("_", "-")
            if swapped_dash in canonical_map:
                return canonical_map[swapped_dash]
            # Stripped special chars
            norm = re.sub(r"[^\w\d]", "", clean).lower()
            if norm in canonical_map:
                return canonical_map[norm]

        # Algorithmic normalization if not found in map
        return self._normalize_unmapped_id(clean)

    def convert_bundle_to_processed_doc(
        self,
        bundle: Hub3BundleInfo,
        chunker: Optional[DocumentChunker] = None,
        canonical_map: Optional[Dict[str, str]] = None,
    ) -> ProcessedDocument:
        """Convert a Hub 3 Gazette Bundle directly into a ProcessedDocument.

        Fast-path bypasses OCR and LLM parsing, strips frontmatter, chunks
        clean markdown, and explicitly stamps each Chunk with chunk_id
        ('{doc_id}::p1::c{idx}') and validity_status.

        Args:
            bundle: Hub3BundleInfo instance.
            chunker: Optional DocumentChunker instance.
            canonical_map: Optional lookup map for relationship target resolution.

        Returns:
            Complete ProcessedDocument ready for indexing or pipeline export.
        """
        md_file = Path(bundle.markdown_path)
        if not md_file.is_file():
            raise FileNotFoundError(f"Markdown file not found for bundle {bundle.slug}: {md_file}")

        with open(md_file, "r", encoding="utf-8") as f:
            raw_text = f.read()

        clean_text = self.clean_markdown_frontmatter(raw_text)

        doc_id = bundle.canonical_id or self._compute_canonical_id(bundle.document_number, bundle.slug)

        identity = DocumentIdentity(
            doc_number=bundle.document_number,
            namespace=bundle.namespace,
            content_hash=hashlib.md5(clean_text.encode("utf-8")).hexdigest(),
            file_name=bundle.file_name,
            rel_path=bundle.bundle_path,
            override_doc_id=doc_id,
        )

        metadata = DocumentMetadata(
            date=bundle.effective_date or bundle.issued_date or "unknown",
            doc_type=bundle.doc_type or "unknown",
            authority=bundle.issued_by or "unknown",
            doc_number=bundle.document_number,
            validity_status=bundle.validity_status,
            doc_status=bundle.validity_status,
            file_name=bundle.file_name,
            source_category=bundle.category,
        )

        # Resolve relationship IDs
        resolved_replaces = list(bundle.canonical_replaces) if bundle.canonical_replaces else [
            self.resolve_canonical_id(r, canonical_map)
            for r in bundle.replaces
            if r
        ]
        resolved_amends = list(bundle.canonical_amends) if bundle.canonical_amends else [
            self.resolve_canonical_id(a, canonical_map)
            for a in bundle.amends
            if a
        ]
        if not bundle.canonical_amends:
            for amd in bundle.amendments:
                amd_id = amd.get("id") if isinstance(amd, dict) else str(amd)
                if amd_id:
                    resolved_amends.append(self.resolve_canonical_id(amd_id, canonical_map))

        relationships = DocumentRelationships(
            replaces=sorted(set(resolved_replaces)),
            amends=sorted(set(resolved_amends)),
            references=list(bundle.references),
            guides=[],
        )

        # Fast-Path Chunking: disable table vision correction & summarization for 100% local execution
        if chunker is None:
            chunker = DocumentChunker()
            chunker.TABLE_CORRECT_ENABLED = False
            chunker.TABLE_SUMMARY_ENABLED = False
        else:
            if hasattr(chunker, "TABLE_CORRECT_ENABLED"):
                chunker.TABLE_CORRECT_ENABLED = False
            if hasattr(chunker, "TABLE_SUMMARY_ENABLED"):
                chunker.TABLE_SUMMARY_ENABLED = False

        raw_chunks = chunker.chunk_document(
            text=clean_text,
            source=bundle.file_name,
            page=1,
            doc_id=doc_id,
        )

        chunks: List[Chunk] = []
        for idx, rc in enumerate(raw_chunks, start=1):
            chunk_id = f"{doc_id}::p1::c{idx}"
            chunk_obj = Chunk(
                text=rc.get("text", ""),
                source=rc.get("source", bundle.file_name),
                page=rc.get("page", 1),
                chunk_type=rc.get("chunk_type", "parent"),
                is_table=rc.get("is_table", False),
                parent_id=rc.get("parent_id", ""),
                hierarchy_path=rc.get("hierarchy_path", ""),
                bbox=rc.get("bbox", [0, 0, 1000, 1000]),
                synthetic_queries=rc.get("synthetic_queries", ""),
                doc_id=doc_id,
                doc_number=bundle.document_number,
                chunk_id=chunk_id,
                validity_status=bundle.validity_status,
            )
            chunks.append(chunk_obj)

        raw_pages = [RawPage(text=clean_text, page=1, source="hub3_markdown")]

        return ProcessedDocument(
            identity=identity,
            metadata=metadata,
            raw_pages=raw_pages,
            chunks=chunks,
            relationships=relationships,
            file_path=str(md_file),
            stage="ready",
        )

    async def sync_topology_to_neo4j(
        self,
        bundles: List[Hub3BundleInfo],
        neo4j_repo: Any,
        canonical_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, int]:
        """Synchronize Hub 3 legal topology and status into Neo4j graph.

        Delegates to Neo4jRepository.sync_hub3_topology or handles custom repo instances.

        Args:
            bundles: List of Hub3BundleInfo instances.
            neo4j_repo: Neo4jRepository instance.
            canonical_map: Optional lookup map for alias resolution.

        Returns:
            Dict with counts of nodes_synced, replaces_created, amends_created.
        """
        if hasattr(neo4j_repo, "sync_hub3_topology"):
            id_map = canonical_map or self.build_canonical_id_map(bundles)
            try:
                result = neo4j_repo.sync_hub3_topology(bundles, id_map=id_map)
            except TypeError:
                result = neo4j_repo.sync_hub3_topology(bundles)
            if inspect.isawaitable(result):
                return await result
            return result
        return {"nodes_synced": 0, "replaces_created": 0, "amends_created": 0}

    def _validate_bundle_security(self, bundle: Hub3BundleInfo) -> None:
        """Validate cryptographic provenance of bundle before ingestion queueing.

        Enforces ADR-0059 Hard Security Gate:
        - If bundle has not been verified yet, auto-invokes verify_bundle_sha256(bundle).
        - If bundle is TAMPERED, immediately raises ValueError.
        - Statutory documents must be cryptographically VERIFIED (or appendices/non-statutory).

        Args:
            bundle: Hub3BundleInfo instance.

        Raises:
            ValueError: If bundle is TAMPERED or statutory document without verified source PDF.
        """
        if not bundle.is_verified and bundle.sha_status != ShaVerificationStatus.TAMPERED.value:
            self.verify_bundle_sha256(bundle)

        if bundle.sha_status == ShaVerificationStatus.TAMPERED.value:
            raise ValueError(
                f"Security Exception: Cannot enqueue TAMPERED bundle {bundle.slug} ({bundle.document_number})"
            )

        is_allowed = (
            bundle.is_verified
            or bundle.category == "04_appendices"
            or not bundle.is_statutory
        )
        if not is_allowed:
            raise ValueError(
                f"Security Exception: Cannot enqueue statutory bundle {bundle.slug} ({bundle.document_number}) "
                f"with unverified source (status: {bundle.sha_status})"
            )

    def enqueue_bundle(self, bundle: Hub3BundleInfo, queue: Any) -> str:
        """Enqueue bundle into IngestionQueue for asynchronous ingestion.

        Fast-Path: Enqueues the pre-standardized, frontmatter-stripped Markdown
        path, bypassing GPU-heavy OCR and LLM extraction stages.
        Strictly enforces ADR-0059 Hard Security Gate before queueing.

        Args:
            bundle: Hub3BundleInfo instance.
            queue: IngestionQueue instance.

        Returns:
            Queue message ID string.
        """
        self._validate_bundle_security(bundle)

        target_file = bundle.markdown_path
        content_hash = bundle.pdf_sha256 or hashlib.md5(bundle.slug.encode("utf-8")).hexdigest()
        return queue.enqueue(
            target_file,
            content_hash,
            bundle.bundle_path,
        )

    def enqueue_batch(self, bundles: List[Hub3BundleInfo], queue: Any) -> int:
        """Enqueue multiple bundles into IngestionQueue in batch.

        Fast-Path: Enqueues Markdown files directly after validating cryptographic SHA-256 provenance.

        Args:
            bundles: List of Hub3BundleInfo instances.
            queue: IngestionQueue instance.

        Returns:
            Count of successfully enqueued items.
        """
        for b in bundles:
            self._validate_bundle_security(b)

        files = []
        for b in bundles:
            target_file = b.markdown_path
            content_hash = b.pdf_sha256 or hashlib.md5(b.slug.encode("utf-8")).hexdigest()
            files.append({
                "file_path": target_file,
                "content_hash": content_hash,
                "rel_path": b.bundle_path,
            })

        if hasattr(queue, "enqueue_batch"):
            return queue.enqueue_batch(files)

        count = 0
        for f in files:
            queue.enqueue(f["file_path"], f["content_hash"], f["rel_path"])
            count += 1
        return count

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _compute_canonical_id(self, doc_number: str, slug: str) -> str:
        """Compute canonical doc_id for Luật, QCVN, and TCVN uniformly."""
        if not doc_number:
            clean_slug = slug.replace(" ", "_")
            return f"VBPL/{clean_slug}"

        # Standard Luật/Nghị định/Thông tư: digits/year/type (e.g. 55/2024/QH15)
        if re.match(r"^\d+/", doc_number):
            raw = f"VBPL/{doc_number}"
            return re.sub(r"[^\w\d\-_/.]", "_", raw)

        # Standard QCVN, TCVN, TCXD, TCXDVN, or APPENDIX/Phụ lục
        if re.match(r"^(?:QCVN|TCVN|TCXD|TCXDVN|APPENDIX|PL)", doc_number, re.IGNORECASE):
            raw = f"VBPL/{doc_number}"
            return re.sub(r"[^\w\d\-_/.]", "_", raw)

        # Fallback to sanitized namespace/slug
        clean_slug = slug.replace(" ", "_")
        return f"VBPL/{clean_slug}"

    def _normalize_unmapped_id(self, identifier: str) -> str:
        """Normalize an external or older document ID not present in Hub 3."""
        clean = identifier.strip()

        # If already starts with VBPL/
        if clean.startswith("VBPL/"):
            return re.sub(r"[^\w\d\-_/.]", "_", clean)

        # Match QCVN: e.g. QCVN 06:2020/BXD or QCVN-01-2019-BXD
        m_qcvn = re.search(r"QCVN[-_\s]*(\d+)[:\-_/](\d{4})[-_\s/]*([A-Z]+)", clean, re.IGNORECASE)
        if m_qcvn:
            num = m_qcvn.group(1).zfill(2)
            year = m_qcvn.group(2)
            auth = m_qcvn.group(3).upper()
            return f"VBPL/QCVN_{num}_{year}/{auth}"

        # Match TCVN: e.g. TCVN 7336:2021, TCVN-4601-1988, TCVN ISO 19650-1:2021
        m_tcvn = re.search(r"TCVN[-_\s]*(?:ISO[-_\s]*)?(\d+)(?:[-_\s]+(\d+))?[:\-_/](\d{4})", clean, re.IGNORECASE)
        if m_tcvn:
            p1 = m_tcvn.group(1)
            p2 = m_tcvn.group(2)
            year = m_tcvn.group(3)
            if "ISO" in clean.upper():
                suffix = f"-{p2}" if p2 else ""
                return f"VBPL/TCVN_ISO_{p1}{suffix}_{year}"
            return f"VBPL/TCVN_{p1}_{year}"

        # Match TCXD or TCXDVN: e.g. TCXD 205:1998, TCXDVN 365:2007
        m_tcxd = re.search(r"(TCXDVN|TCXD)[-_\s]*(\d+)[:\-_/](\d{2,4})", clean, re.IGNORECASE)
        if m_tcxd:
            prefix = m_tcxd.group(1).upper()
            return f"VBPL/{prefix}_{m_tcxd.group(2)}_{m_tcxd.group(3)}"

        # Match standard decree/circular/law: e.g. 15/2021/NĐ-CP or 10_2021_nd_cp
        m_law = re.search(r"(\d+)[/_\-](\d{4})[/_\-]([A-Za-z0-9Đđ_\-]+)", clean)
        if m_law:
            num = m_law.group(1)
            year = m_law.group(2)
            suffix = m_law.group(3).upper().replace("_", "-")
            if "ND" in suffix and "NĐ" not in suffix:
                suffix = suffix.replace("ND", "NĐ")
            return f"VBPL/{num}/{year}/{suffix}"

        # Default fallback
        sanitized = re.sub(r"[^\w\d\-_/.]", "_", clean)
        return f"VBPL/{sanitized}"
