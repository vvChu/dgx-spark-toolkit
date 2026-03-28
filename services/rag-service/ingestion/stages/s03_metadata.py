"""Stage 3: Metadata — Regex + LLM extraction with hardening."""
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

from ingestion.models import ProcessedDocument
from ingestion.legal_taxonomy import classify_all, classify_source_category

logger = logging.getLogger(__name__)


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument:
    """Extract and refine metadata from filename + document text in parallel."""
    file_path = doc.file_path
    raw_pages = doc.raw_pages

    # Prepare text windows for parallel LLM calls
    full_text_head = "\n".join([p.text for p in raw_pages[:2]])
    full_text_summary = "\n".join([p.text for p in raw_pages[:5]])
    head_tail_rels = "\n".join([p.text for p in raw_pages[:5]] + [p.text for p in raw_pages[-3:]])

    # Step 1: Regex filename metadata
    meta = ctx.parse_metadata(os.path.basename(file_path))
    doc.metadata.update_from_dict(meta)
    doc.metadata.file_name = os.path.basename(file_path)

    # Step 2: Parallel LLM refinement — each call is independent, partial success OK
    _LLM_TIMEOUT = 60  # Free tier models respond in 2-10s; 60s is generous

    with ThreadPoolExecutor(max_workers=3) as executor:
        from ingestion.cloud_vision import llm_generate_summary, llm_extract_metadata
        meta_future = executor.submit(llm_extract_metadata, full_text_head)
        summary_future = executor.submit(llm_generate_summary, full_text_summary)
        rels_future = executor.submit(ctx.parse_relationships_llm, head_tail_rels)

        # Each call handled independently — never let one failure kill the pipeline
        try:
            refined_meta = meta_future.result(timeout=_LLM_TIMEOUT)
        except Exception as e:
            logger.warning(f"  Metadata LLM failed ({e}), using regex only")
            refined_meta = None
        try:
            doc.summary = summary_future.result(timeout=_LLM_TIMEOUT)
        except Exception as e:
            logger.warning(f"  Summary LLM failed ({e}), skipping")
            doc.summary = ""
        try:
            rels = rels_future.result(timeout=_LLM_TIMEOUT)
        except Exception as e:
            logger.warning(f"  Relationships LLM failed ({e}), using regex fallback")
            rels = ctx.parse_relationships(head_tail_rels)

    # Step 3: Harden metadata refinement
    if refined_meta:
        _harden_metadata(doc, refined_meta)

    # Step 4: Regex fallback for doc_number
    if not doc.metadata.doc_number:
        regex_num = ctx.extract_doc_number_regex(full_text_head)
        if regex_num:
            doc.metadata.doc_number = regex_num

    # Step 5: Legal taxonomy classification
    taxonomy = classify_all(
        doc_number=doc.metadata.doc_number,
        filename=os.path.basename(file_path),
        authority=doc.metadata.authority,
        text_head=full_text_head,
    )
    doc.metadata.doc_type = taxonomy["doc_type"]
    doc.metadata.legal_level = taxonomy["legal_level"]
    doc.metadata.discipline = taxonomy["discipline"]
    logger.info(f"  Taxonomy: type={taxonomy['doc_type']}, level={taxonomy['legal_level']}, discipline={taxonomy['discipline']}")

    # Step 6a: Source category from folder structure (P1-5)
    source_cat = classify_source_category(doc.identity.rel_path)
    doc.metadata.source_category = source_cat
    logger.info(f"  source_category: {source_cat}")

    # Step 7: Parse relationships
    if isinstance(rels, dict):
        from ingestion.models import DocumentRelationships
        doc.relationships = DocumentRelationships(
            replaces=rels.get("replaces", []),
            amends=rels.get("amends", []),
            references=rels.get("references", []),
            guides=rels.get("guides", []),
        )

    return doc


def _harden_metadata(doc: ProcessedDocument, refined: dict):
    """Prevent metadata degradation from weak LLM outputs."""
    new_num = refined.get("doc_number", "")
    old_num = doc.metadata.doc_number or ""

    is_new_suspicious = bool(re.match(r'^\d+$', str(new_num))) and len(str(new_num)) <= 2
    is_old_robust = '/' in str(old_num) or len(str(old_num)) > 4

    if is_new_suspicious and is_old_robust:
        logger.warning(f"  Rejected suspicious doc_number refinement: '{new_num}' vs '{old_num}'")
        refined.pop("doc_number", None)

    # Validate date
    llm_date = refined.get("date") or refined.get("doc_date", "")
    if llm_date and llm_date != "unknown":
        if not re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$|^\d{4}-\d{2}-\d{2}$', str(llm_date)):
            logger.warning(f"  Rejected suspicious date: '{llm_date}'")
            refined.pop("date", None)
            refined.pop("doc_date", None)
        elif llm_date in ("2025-01-01", "01/01/2025", "01-01-2025"):
            logger.warning(f"  Rejected placeholder date: '{llm_date}'")
            refined.pop("date", None)
            refined.pop("doc_date", None)

    doc.metadata.update_from_dict({k: v for k, v in refined.items() if v and v != "unknown"})
