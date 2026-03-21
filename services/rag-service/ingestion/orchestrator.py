"""Stage-based orchestrator for the RAG ingestion pipeline.

Replaces the monolithic process_file() method with a sequence of stages,
each operating on a shared ProcessedDocument model.

Usage:
    orchestrator = PipelineOrchestrator(ingestor)
    orchestrator.run_pipeline(file_path)
"""
import logging
import time
from typing import Callable

from prometheus_client import Histogram, Counter

from ingestion.models import ProcessedDocument, DocumentIdentity, DocumentMetadata

logger = logging.getLogger(__name__)

# Pipeline stage metrics
STAGE_DURATION = Histogram(
    'rag_stage_duration_seconds',
    'Time spent in each pipeline stage',
    ['stage'],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300]
)
STAGE_TOTAL = Counter(
    'rag_stage_total',
    'Pipeline stage executions',
    ['stage', 'status']  # status: success, error, skip
)
PIPELINE_TOTAL = Counter(
    'rag_pipeline_total',
    'Total pipeline runs',
    ['status']  # completed, skipped, failed
)


class StageError(Exception):
    """Raised when a pipeline stage fails."""
    def __init__(self, stage_name: str, cause: Exception):
        self.stage_name = stage_name
        self.cause = cause
        super().__init__(f"Stage '{stage_name}' failed: {cause}")


class PipelineOrchestrator:
    """Runs pipeline stages sequentially on a ProcessedDocument.
    
    Stage signature: (doc: ProcessedDocument, ctx: PipelineContext) -> ProcessedDocument
    """

    def __init__(self, ctx):
        """ctx is the PipelineContext (the ProductionIngestor instance for now)."""
        self.ctx = ctx
        self.stages: list[tuple[str, Callable]] = []
        self._register_stages()

    def _register_stages(self):
        """Register all stages in order."""
        from ingestion.stages.s01_intake import run as s01
        from ingestion.stages.s02_ocr import run as s02
        from ingestion.stages.s03_metadata import run as s03
        from ingestion.stages.s04_identity import run as s04
        from ingestion.stages.s05_chunking import run as s05
        from ingestion.stages.s06_enrichment import run as s06
        from ingestion.stages.s07_embedding import run as s07
        from ingestion.stages.s08_indexing import run as s08
        from ingestion.stages.s09_export import run as s09

        self.stages = [
            ("s01_intake", s01),
            ("s02_ocr", s02),
            ("s03_metadata", s03),
            ("s04_identity", s04),
            ("s05_chunking", s05),
            ("s06_enrichment", s06),
            ("s07_embedding", s07),
            ("s08_indexing", s08),
            ("s09_export", s09),
        ]

    def run_pipeline(self, file_path: str) -> ProcessedDocument | None:
        """Execute all stages on a file. Returns ProcessedDocument or None on skip."""
        import os

        SOURCE_DIR = "/app/data/legal_docs_source"
        rel_path = os.path.relpath(file_path, SOURCE_DIR)

        # Create initial document model
        doc = ProcessedDocument(
            identity=DocumentIdentity(
                doc_number="",
                namespace="",
                content_hash="",
                file_name=os.path.basename(file_path),
                rel_path=rel_path,
            ),
            file_path=file_path,
        )

        for stage_name, stage_fn in self.stages:
            t0 = time.time()
            try:
                result = stage_fn(doc, self.ctx)
                elapsed = time.time() - t0
                STAGE_DURATION.labels(stage=stage_name).observe(elapsed)

                if result is None:
                    STAGE_TOTAL.labels(stage=stage_name, status="skip").inc()
                    PIPELINE_TOTAL.labels(status="skipped").inc()
                    logger.info(f"  [{stage_name}] Skipped ({elapsed:.2f}s)")
                    return None

                STAGE_TOTAL.labels(stage=stage_name, status="success").inc()
                doc = result
                doc.stage = stage_name
                logger.debug(f"  [{stage_name}] completed in {elapsed:.2f}s")
            except Exception as e:
                elapsed = time.time() - t0
                STAGE_DURATION.labels(stage=stage_name).observe(elapsed)
                STAGE_TOTAL.labels(stage=stage_name, status="error").inc()
                PIPELINE_TOTAL.labels(status="failed").inc()
                logger.error(f"  [{stage_name}] FAILED in {elapsed:.2f}s: {e}")
                raise StageError(stage_name, e)

        PIPELINE_TOTAL.labels(status="completed").inc()
        return doc
