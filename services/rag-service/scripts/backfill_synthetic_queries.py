#!/usr/bin/env python3
"""Backfill synthetic queries for existing JSON exports that lack them.

Reads all exports/json/*.json, finds parent chunks without synthetic_queries,
calls the LLM to generate them, saves results back, and optionally rebuilds
Milvus entries.

Run inside the rag-service container:
    docker compose exec rag-service python3 scripts/backfill_synthetic_queries.py

Options (env vars):
    BACKFILL_LIMIT   max chunks to process (default: 0 = no limit)
    BACKFILL_DRY_RUN  set to 1 to preview without saving (default: 0)
    EXPORT_JSON_DIR  path to exports (default: /app/exports/json)
"""
import os
import sys
import json
import time
import logging
import glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

EXPORT_JSON_DIR = os.environ.get("EXPORT_JSON_DIR", "/app/exports/json")
BACKFILL_LIMIT = int(os.environ.get("BACKFILL_LIMIT", "0"))
DRY_RUN = os.environ.get("BACKFILL_DRY_RUN", "0") == "1"
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "6"))  # LLM concurrency

# ── LLM setup ────────────────────────────────────────────────────────────────

try:
    import httpx
    from core.config import get_settings
    s = get_settings()
    _API_URL = s.VLLM_API_BASE.rstrip("/") + "/chat/completions"
    _MODEL = os.environ.get("JSON_MODEL", s.VLLM_MODEL)
    _API_KEY = s.LITELLM_MASTER_KEY or "unused"
    _CLIENT = httpx.Client(timeout=60)
    logger.info(f"LLM endpoint: {_API_URL}  model: {_MODEL}")
except Exception as e:
    logger.error(f"Cannot load settings: {e}")
    sys.exit(1)


def _generate(chunk_text: str) -> str:
    """Call LLM to generate 3-5 synthetic queries for a chunk."""
    payload = {
        "model": _MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an assistant that generates hypothetical user questions. "
                    "Output ONLY 3-5 questions separated by newlines that the given text can answer."
                ),
            },
            {
                "role": "user",
                "content": f"Generate 3-5 questions for this text:\n\n{chunk_text[:2000]}\n\nQuestions:",
            },
        ],
        "max_tokens": 512,
        "temperature": 0.5,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }
    headers = {"Authorization": f"Bearer {_API_KEY}"}

    for attempt in range(3):
        try:
            resp = _CLIENT.post(_API_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                time.sleep(5 * (2**attempt))
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"].get("content", "").strip()
            return content[:4000]
        except Exception as exc:
            if attempt == 2:
                logger.warning(f"Failed after 3 attempts: {exc}")
                return ""
            time.sleep(5 * (2**attempt))
    return ""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    json_files = sorted(glob.glob(os.path.join(EXPORT_JSON_DIR, "*.json")))
    logger.info(f"Found {len(json_files)} JSON exports in {EXPORT_JSON_DIR}")

    # Collect all parent chunks missing synthetic_queries
    todo: list[tuple[str, dict, dict]] = []  # (file_path, doc_data, chunk)
    for path in json_files:
        try:
            data = json.loads(Path(path).read_text(errors="replace"))
        except Exception as e:
            logger.warning(f"Skip (parse error): {path}: {e}")
            continue
        for chunk in data.get("chunks", []):
            if (
                chunk.get("chunk_type") == "parent"
                and len(chunk.get("text", "")) > 100
                and not chunk.get("synthetic_queries", "").strip()
            ):
                todo.append((path, data, chunk))

    total = len(todo)
    logger.info(f"Found {total} parent chunks without synthetic_queries")

    if BACKFILL_LIMIT > 0:
        todo = todo[:BACKFILL_LIMIT]
        logger.info(f"Limited to {len(todo)} chunks (BACKFILL_LIMIT={BACKFILL_LIMIT})")

    if DRY_RUN:
        logger.info("DRY RUN — no changes will be saved")
        return

    if not todo:
        logger.info("Nothing to backfill. All parent chunks already have synthetic_queries.")
        return

    # Group by file so we can save each file once after all its chunks are done
    from collections import defaultdict
    file_to_chunks: dict[str, list[dict]] = defaultdict(list)
    chunk_to_file: dict[int, str] = {}
    for path, _data, chunk in todo:
        file_to_chunks[path].append(chunk)
        chunk_to_file[id(chunk)] = path

    # Load all file data into memory (for mutation)
    file_data: dict[str, dict] = {}
    for path in file_to_chunks:
        file_data[path] = json.loads(Path(path).read_text(errors="replace"))

    # Build a flat task list with references to mutable chunk dicts
    flat_tasks: list[tuple[str, dict]] = []
    for path, data in file_data.items():
        for chunk in data.get("chunks", []):
            if (
                chunk.get("chunk_type") == "parent"
                and len(chunk.get("text", "")) > 100
                and not chunk.get("synthetic_queries", "").strip()
                and path in file_to_chunks
            ):
                flat_tasks.append((path, chunk))

    if BACKFILL_LIMIT > 0:
        flat_tasks = flat_tasks[:BACKFILL_LIMIT]

    logger.info(f"Backfilling {len(flat_tasks)} chunks with {MAX_WORKERS} workers...")
    done = 0
    errors = 0
    dirty_files: set[str] = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to = {
            executor.submit(_generate, chunk["text"]): (path, chunk)
            for path, chunk in flat_tasks
        }
        for future in as_completed(future_to):
            path, chunk = future_to[future]
            try:
                result = future.result()
                if result:
                    chunk["synthetic_queries"] = result
                    dirty_files.add(path)
                    done += 1
                else:
                    errors += 1
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                errors += 1

            if (done + errors) % 50 == 0:
                logger.info(f"  Progress: {done + errors}/{len(flat_tasks)} (done={done}, err={errors})")

    # Save modified files
    logger.info(f"Saving {len(dirty_files)} modified JSON files...")
    saved = 0
    for path in dirty_files:
        try:
            Path(path).write_text(
                json.dumps(file_data[path], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            saved += 1
        except Exception as e:
            logger.error(f"Failed to save {path}: {e}")

    logger.info(
        f"\n✅ Backfill complete: {done} queries generated, {errors} errors, {saved} files saved."
    )
    logger.info(
        "Run comprehensive_audit.py again to verify synthetic_queries coverage."
    )


if __name__ == "__main__":
    main()
