"""Container startup warmup module for heavy ML models (BGE-M3 & BGE-Reranker).

Provides resilient model pre-warming during container startup to avoid
first-query latency spikes while preserving CI/test hermeticity.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Mutex to prevent multiple concurrent warmup executions
_warmup_thread_lock = threading.Lock()


def is_test_environment() -> bool:
    """Detect whether code is executing in a CI runner or pytest environment.

    Returns:
        bool: True if test environment flags are set, False otherwise.
    """
    skip_flag = os.getenv("SKIP_MODEL_WARMUP", "").strip().lower()
    return bool(
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("CI")
        or skip_flag in ("1", "true", "yes")
    )


async def perform_warmup(
    app: FastAPI,
    timeout: Optional[float] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Warm up heavy ML models (BGE-M3 embedding & BGE-Reranker) sequentially.

    In test or CI environments, warmup is automatically skipped unless force=True.
    Uses an isolated background thread to prevent blocking the asyncio event loop.
    Implements a self-healing pattern where late completion updates app.state.warmup_status.

    Args:
        app: FastAPI application instance whose state holds warmup_status.
        timeout: Maximum time in seconds to wait synchronously before continuing startup.
        force: If True, bypass test environment checks and force warmup execution.

    Returns:
        Dict[str, Any]: Status dictionary detailing warmup state.
    """
    from core.config import get_settings
    settings = get_settings()

    # 1. Skip in test/CI environments unless explicitly forced
    if is_test_environment() and not force:
        status: Dict[str, Any] = {"status": "skipped", "reason": "test_env"}
        if hasattr(app, "state"):
            app.state.warmup_status = status
        return status

    # 2. Check if warmup is disabled via configuration
    if not getattr(settings, "WARMUP_ON_STARTUP", True) and not force:
        status = {"status": "disabled", "reason": "config_disabled"}
        if hasattr(app, "state"):
            app.state.warmup_status = status
        return status

    # 3. Parse timeout before acquiring lock to prevent lock leaks on invalid input
    try:
        if timeout is not None:
            timeout_seconds = float(timeout)
        else:
            timeout_seconds = float(getattr(settings, "WARMUP_TIMEOUT_SECONDS", 110.0) or 110.0)
    except (ValueError, TypeError) as err:
        logger.error(f"Invalid warmup timeout value: {err}")
        return {"status": "failed", "error": f"Invalid timeout: {err}"}

    # 4. Check for concurrent warmup execution (never return stale status)
    if not _warmup_thread_lock.acquire(blocking=False):
        logger.warning("Model warmup already in progress, skipping concurrent trigger.")
        return {"status": "in_progress", "reason": "already_in_progress"}

    if hasattr(app, "state"):
        app.state.warmup_status = {"status": "in_progress"}

    def _worker() -> None:
        t0 = time.time()
        try:
            logger.info("Starting model warmup (BGE-M3 & Reranker)...")

            # Step 1: BGE-M3 Singleton (Dense + Sparse vector initialization)
            from retrieval.search_pipeline import get_embedding_model
            embedding_model = get_embedding_model()
            embedding_model.embed_query("warmup query")
            logger.info("Embedding model (BGE-M3) warmup completed.")

            # Step 2: BGE-Reranker (CrossEncoder GPU/CPU inference initialization)
            from retrieval.reranker import get_reranker
            reranker = get_reranker()
            reranker.rerank_sync("warmup query", ["warmup doc"])
            logger.info("Reranker model warmup completed.")

            elapsed = time.time() - t0
            logger.info(f"Model warmup completed successfully in {elapsed:.2f}s")
            if hasattr(app, "state"):
                app.state.warmup_status = {
                    "status": "ready",
                    "duration_seconds": round(elapsed, 2),
                }
        except Exception as e:
            logger.critical(f"Model warmup failed: {e}", exc_info=True)
            if hasattr(app, "state"):
                app.state.warmup_status = {
                    "status": "failed",
                    "error": str(e),
                }
        finally:
            try:
                _warmup_thread_lock.release()
            except RuntimeError:
                pass

    try:
        worker_task = asyncio.create_task(asyncio.to_thread(_worker))
    except Exception as dispatch_err:
        logger.critical(f"Failed to dispatch warmup worker: {dispatch_err}", exc_info=True)
        try:
            _warmup_thread_lock.release()
        except RuntimeError:
            pass
        if hasattr(app, "state"):
            app.state.warmup_status = {"status": "failed", "error": str(dispatch_err)}
        return {"status": "failed", "error": str(dispatch_err)}

    try:
        await asyncio.wait_for(asyncio.shield(worker_task), timeout=timeout_seconds)
        st = getattr(app.state, "warmup_status", None) if hasattr(app, "state") else None
        return st if isinstance(st, dict) else {"status": "ready"}
    except asyncio.TimeoutError:
        logger.warning(
            f"Model warmup timed out after {timeout_seconds}s. "
            "Continuing startup with warmup running in background (Self-Healing enabled)."
        )
        st = getattr(app.state, "warmup_status", None) if hasattr(app, "state") else None
        return st if isinstance(st, dict) else {"status": "in_progress"}
