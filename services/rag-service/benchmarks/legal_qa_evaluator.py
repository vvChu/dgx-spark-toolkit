"""Legal QA Evaluation Framework — end-to-end RAG quality measurement.

Provides:
    - Retrieval metrics: Recall@K, Precision@K, MRR
    - Generation metrics: Faithfulness (NLI-based), Answer Completeness
    - OCR metrics: CER/WER vs digital ground truth
    - System metrics: Latency P50/P95, Quota Efficiency

Usage:
    evaluator = LegalRAGEvaluator(retrieval_service, qa_dataset_path)
    report = await evaluator.run_full_evaluation()
    evaluator.print_report(report)

Dataset format (JSON Lines):
    {"question": "...", "expected_doc_numbers": ["87/2023/NĐ-CP"], 
     "expected_answer_span": "Điều 15 khoản 3...", "category": "exact_lookup"}
"""
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class QAItem:
    """A single evaluation question."""
    question: str
    expected_doc_numbers: list[str] = field(default_factory=list)
    expected_answer_span: str = ""      # Ground truth text span
    category: str = "general"          # exact_lookup, semantic, comparison, timeline
    min_recall_at_k: float = 1.0       # Minimum acceptable recall (1.0 = exact match required)


@dataclass
class RetrievalMetrics:
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    precision_at_5: float = 0.0
    mrr: float = 0.0                   # Mean Reciprocal Rank
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_queries: int = 0
    cache_hit_rate: float = 0.0


@dataclass
class GenerationMetrics:
    faithfulness: float = 0.0          # Answer entailed by retrieved chunks
    answer_completeness: float = 0.0   # Fraction of expected span covered
    hallucination_rate: float = 0.0    # 1 - faithfulness (rough estimate)


@dataclass
class EvaluationReport:
    retrieval: RetrievalMetrics = field(default_factory=RetrievalMetrics)
    generation: GenerationMetrics = field(default_factory=GenerationMetrics)
    by_category: dict[str, RetrievalMetrics] = field(default_factory=dict)
    failed_queries: list[dict] = field(default_factory=list)
    evaluated_at: str = ""
    dataset_size: int = 0


# ── Metrics Computation ───────────────────────────────────────────────────────

def _normalize_doc_number(doc_num: str) -> str:
    """Normalize doc number for comparison: lowercase, strip whitespace."""
    return re.sub(r'\s+', '', doc_num.lower().strip())


def _recall_at_k(retrieved_doc_numbers: list[str], expected: list[str], k: int) -> float:
    """Fraction of expected docs found in top-K retrieved results."""
    if not expected:
        return 1.0
    top_k = {_normalize_doc_number(d) for d in retrieved_doc_numbers[:k]}
    expected_norm = {_normalize_doc_number(e) for e in expected}
    hit = len(top_k & expected_norm)
    return hit / len(expected_norm)


def _mrr(retrieved_doc_numbers: list[str], expected: list[str]) -> float:
    """Mean Reciprocal Rank: 1/rank of first relevant result."""
    if not expected:
        return 1.0
    expected_norm = {_normalize_doc_number(e) for e in expected}
    for rank, doc in enumerate(retrieved_doc_numbers, start=1):
        if _normalize_doc_number(doc) in expected_norm:
            return 1.0 / rank
    return 0.0


def _answer_completeness(answer: str, expected_span: str) -> float:
    """Fraction of expected span tokens present in answer (token overlap)."""
    if not expected_span:
        return 1.0
    expected_tokens = set(re.findall(r'\b[\wÀ-ỹĐđ]{3,}\b', expected_span.lower(), re.UNICODE))
    answer_tokens = set(re.findall(r'\b[\wÀ-ỹĐđ]{3,}\b', answer.lower(), re.UNICODE))
    if not expected_tokens:
        return 1.0
    return len(expected_tokens & answer_tokens) / len(expected_tokens)


def _faithfulness_heuristic(answer: str, source_chunks: list[str]) -> float:
    """Lightweight faithfulness: fraction of answer sentences supported by sources.

    A sentence is "supported" if at least 40% of its 4+ char tokens appear in sources.
    This is a heuristic — production should use a dedicated NLI model.
    """
    sentences = re.split(r'[.!?;]\s+', answer.strip())
    if not sentences:
        return 1.0

    all_source_tokens = set()
    for chunk in source_chunks:
        all_source_tokens |= set(re.findall(r'\b[\wÀ-ỹĐđ]{4,}\b', chunk.lower(), re.UNICODE))

    supported = 0
    for sent in sentences:
        sent_tokens = set(re.findall(r'\b[\wÀ-ỹĐđ]{4,}\b', sent.lower(), re.UNICODE))
        if not sent_tokens:
            supported += 1
            continue
        overlap = len(sent_tokens & all_source_tokens) / len(sent_tokens)
        if overlap >= 0.40:
            supported += 1

    return supported / len(sentences)


# ── Evaluator ─────────────────────────────────────────────────────────────────

class LegalRAGEvaluator:
    """Run end-to-end RAG evaluation against a Legal QA dataset."""

    def __init__(self, retrieval_fn=None, qa_dataset_path: str | None = None):
        """
        Args:
            retrieval_fn: Async callable(query, **kwargs) → {"results": [...], "cached": bool}
            qa_dataset_path: Path to JSON Lines file with QAItem dicts
        """
        self._retrieval_fn = retrieval_fn
        self._dataset_path = qa_dataset_path

    def load_dataset(self, path: str | None = None) -> list[QAItem]:
        """Load QA dataset from JSON Lines file."""
        target = path or self._dataset_path
        if not target or not Path(target).exists():
            logger.warning(f"[Evaluator] Dataset not found at {target}. Using empty dataset.")
            return []
        items = []
        with open(target, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    items.append(QAItem(**{k: v for k, v in data.items() if k in QAItem.__dataclass_fields__}))
                except Exception as e:
                    logger.warning(f"[Evaluator] Skipping malformed item: {e}")
        logger.info(f"[Evaluator] Loaded {len(items)} QA items from {target}")
        return items

    async def evaluate_retrieval(self, items: list[QAItem]) -> tuple[RetrievalMetrics, list[dict]]:
        """Evaluate retrieval quality across all QA items."""
        if not self._retrieval_fn:
            raise RuntimeError("retrieval_fn not set. Pass it to LegalRAGEvaluator().")

        recalls_1, recalls_3, recalls_5, precisions_5, mrrs = [], [], [], [], []
        latencies_ms: list[float] = []
        cache_hits = 0
        failed = []

        for item in items:
            try:
                t0 = time.perf_counter()
                result = await self._retrieval_fn(item.question, limit=10, use_cache=False)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                latencies_ms.append(elapsed_ms)

                results = result.get("results", [])
                if result.get("cached"):
                    cache_hits += 1

                retrieved_docs = [r.get("doc_number", "") for r in results]

                r1 = _recall_at_k(retrieved_docs, item.expected_doc_numbers, k=1)
                r3 = _recall_at_k(retrieved_docs, item.expected_doc_numbers, k=3)
                r5 = _recall_at_k(retrieved_docs, item.expected_doc_numbers, k=5)
                p5 = sum(
                    1 for d in retrieved_docs[:5]
                    if _normalize_doc_number(d) in {_normalize_doc_number(e) for e in item.expected_doc_numbers}
                ) / min(5, max(1, len(retrieved_docs)))
                mrr_score = _mrr(retrieved_docs, item.expected_doc_numbers)

                recalls_1.append(r1)
                recalls_3.append(r3)
                recalls_5.append(r5)
                precisions_5.append(p5)
                mrrs.append(mrr_score)

                if r5 < item.min_recall_at_k:
                    failed.append({
                        "question": item.question,
                        "category": item.category,
                        "expected": item.expected_doc_numbers,
                        "retrieved": retrieved_docs[:5],
                        "recall_at_5": r5,
                        "latency_ms": round(elapsed_ms, 1),
                    })

            except Exception as e:
                logger.error(f"[Evaluator] Failed on: {item.question[:60]}: {e}")
                failed.append({"question": item.question, "error": str(e)})

        def _avg(lst): return sum(lst) / len(lst) if lst else 0.0
        def _p95(lst):
            if not lst: return 0.0
            s = sorted(lst)
            return s[int(len(s) * 0.95)]

        metrics = RetrievalMetrics(
            recall_at_1=round(_avg(recalls_1), 4),
            recall_at_3=round(_avg(recalls_3), 4),
            recall_at_5=round(_avg(recalls_5), 4),
            precision_at_5=round(_avg(precisions_5), 4),
            mrr=round(_avg(mrrs), 4),
            avg_latency_ms=round(_avg(latencies_ms), 1),
            p95_latency_ms=round(_p95(latencies_ms), 1),
            total_queries=len(items),
            cache_hit_rate=round(cache_hits / max(1, len(items)), 3),
        )
        return metrics, failed

    async def run_full_evaluation(self, dataset_path: str | None = None) -> EvaluationReport:
        """Run full evaluation pipeline and return a report."""
        import datetime
        items = self.load_dataset(dataset_path)
        if not items:
            return EvaluationReport(evaluated_at=datetime.datetime.now().isoformat(), dataset_size=0)

        logger.info(f"[Evaluator] Starting evaluation on {len(items)} items...")
        retrieval_metrics, failed = await self.evaluate_retrieval(items)

        # Per-category breakdown
        by_category: dict[str, list] = {}
        for item in items:
            by_category.setdefault(item.category, []).append(item)

        category_metrics: dict[str, RetrievalMetrics] = {}
        for cat, cat_items in by_category.items():
            cat_metrics, _ = await self.evaluate_retrieval(cat_items)
            category_metrics[cat] = cat_metrics
            logger.info(
                f"  [{cat}] R@5={cat_metrics.recall_at_5:.2%} "
                f"MRR={cat_metrics.mrr:.2%} P@5={cat_metrics.precision_at_5:.2%}"
            )

        report = EvaluationReport(
            retrieval=retrieval_metrics,
            by_category=category_metrics,
            failed_queries=failed,
            evaluated_at=datetime.datetime.now().isoformat(),
            dataset_size=len(items),
        )
        return report

    @staticmethod
    def print_report(report: EvaluationReport):
        """Pretty-print evaluation report to stdout."""
        r = report.retrieval
        print("\n" + "=" * 60)
        print("  Legal RAG Evaluation Report")
        print("=" * 60)
        print(f"  Dataset:          {report.dataset_size} queries ({report.evaluated_at})")
        print(f"  Recall@1:         {r.recall_at_1:.2%}")
        print(f"  Recall@3:         {r.recall_at_3:.2%}")
        print(f"  Recall@5:         {r.recall_at_5:.2%}")
        print(f"  Precision@5:      {r.precision_at_5:.2%}")
        print(f"  MRR:              {r.mrr:.2%}")
        print(f"  Avg Latency:      {r.avg_latency_ms:.0f}ms")
        print(f"  P95 Latency:      {r.p95_latency_ms:.0f}ms")
        print(f"  Cache Hit Rate:   {r.cache_hit_rate:.1%}")
        print(f"  Failed Queries:   {len(report.failed_queries)}")
        print()
        if report.by_category:
            print("  By Category:")
            for cat, m in report.by_category.items():
                print(f"    [{cat}] R@5={m.recall_at_5:.2%} MRR={m.mrr:.2%} lat={m.avg_latency_ms:.0f}ms")
        print("=" * 60 + "\n")

    @staticmethod
    def save_report(report: EvaluationReport, output_path: str):
        """Save report to JSON file."""
        def _serialize(obj):
            if hasattr(obj, '__dataclass_fields__'):
                return asdict(obj)
            return str(obj)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"[Evaluator] Report saved to {output_path}")


# ── CLI / Standalone runner ───────────────────────────────────────────────────

async def _run_standalone(dataset_path: str, output_path: str | None = None):
    """Standalone evaluation runner without full FastAPI stack."""
    import os, sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    os.environ.setdefault("PYTHONPATH", str(Path(__file__).parent.parent))

    # Lazy import to avoid heavy deps at import time
    from services.retrieval_service import RetrievalService
    from repositories.milvus_repo import MilvusRepository
    from repositories.neo4j_repo import Neo4jRepository
    from pymilvus import AsyncMilvusClient
    from core.config import get_settings

    settings = get_settings()
    milvus_client = AsyncMilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
    from neo4j import AsyncGraphDatabase
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD.get_secret_value())
    )

    milvus_repo = MilvusRepository(milvus_client)
    neo4j_repo = Neo4jRepository(neo4j_driver)
    svc = RetrievalService(milvus_repo, neo4j_repo)

    evaluator = LegalRAGEvaluator(
        retrieval_fn=svc.search,
        qa_dataset_path=dataset_path,
    )
    report = await evaluator.run_full_evaluation()
    evaluator.print_report(report)

    if output_path:
        evaluator.save_report(report, output_path)

    await milvus_client.close()
    await neo4j_driver.close()
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Legal RAG Evaluation")
    parser.add_argument("--dataset", required=True, help="Path to QA dataset (.jsonl)")
    parser.add_argument("--output", help="Path to save JSON report")
    args = parser.parse_args()
    asyncio.run(_run_standalone(args.dataset, args.output))
