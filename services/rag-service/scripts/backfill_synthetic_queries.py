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
from pathlib import Path

# Ensure rag-service root (/app or repo root) is in sys.path
_RAG_ROOT = str(Path(__file__).resolve().parent.parent)
if _RAG_ROOT not in sys.path:
    sys.path.insert(0, _RAG_ROOT)
if os.path.exists("/app") and "/app" not in sys.path:
    sys.path.insert(0, "/app")

import json
import time
import logging
import glob
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

EXPORT_JSON_DIR = os.environ.get(
    "EXPORT_JSON_DIR",
    "/app/exports/json" if os.path.exists("/app/exports/json") else "/home/vvc/Public/exports/json"
)
BACKFILL_LIMIT = int(os.environ.get("BACKFILL_LIMIT", "195"))
DRY_RUN = os.environ.get("BACKFILL_DRY_RUN", "0") == "1"
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "6"))  # LLM concurrency

_VN_DIACRITICS = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]",
    re.IGNORECASE,
)


def is_valid_synthetic_queries(text: str) -> bool:
    """Validate that synthetic queries are genuine Vietnamese questions."""
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    if len(text) < 20:
        return False
    if "is no longer available" in text or "Please switch to Gemini" in text:
        return False
    if "Thinking Process" in text or "Analyze the Request" in text or "Tư duy suy luận" in text:
        return False
    if not _VN_DIACRITICS.search(text):
        return False
    return True


# ── LLM setup ────────────────────────────────────────────────────────────────

try:
    import httpx
    from core.config import get_settings
    from ingestion.normalizers.boilerplate import strip_ai_monologue
    from ingestion.legal_taxonomy import classify_source_category
    _API_URL = os.environ.get("SYNTHETIC_API_URL", "").rstrip("/")
    if not _API_URL:
        _API_URL = os.environ.get("VLLM_API_BASE", "").rstrip("/")
        if not _API_URL or "ai-gateway:4000" in _API_URL:
            _API_URL = "http://100.83.192.30:8045/v1"
    if not _API_URL.endswith("/chat/completions"):
        _API_URL += "/chat/completions"
    _MODEL = os.environ.get("SYNTHETIC_QUERY_MODEL", "gemini-3.7-flash-low")
    _API_KEY = os.environ.get("GATEWAY_PROXY_KEY", "sk-ef1b299485084c76a1396fa6275cb30d")
    _CLIENT = httpx.Client(timeout=60)
    logger.info(f"LLM endpoint: {_API_URL}  model: {_MODEL}")
except Exception as e:
    logger.error(f"Cannot load settings: {e}")
    sys.exit(1)


def _generate(chunk_text: str) -> str:
    """Call LLM to generate 3-5 synthetic queries for a chunk in Vietnamese."""
    payload = {
        "model": _MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Bạn là trợ lý chuyên tạo câu hỏi giả định người dùng bằng tiếng Việt. "
                    "CHỈ xuất ra 3-5 câu hỏi tiếng Việt, mỗi câu trên một dòng riêng biệt, mà văn bản đã cho có thể trả lời. "
                    "TUYỆT ĐỐI KHÔNG xuất quá trình tư duy, phân tích, hay ngôn ngữ khác."
                ),
            },
            {
                "role": "user",
                "content": f"Tạo 3-5 câu hỏi tiếng Việt cho đoạn văn bản sau:\n\n{chunk_text[:2000]}\n\nCâu hỏi:",
            },
        ],
        "max_tokens": 512,
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {_API_KEY}"}

    for attempt in range(3):
        try:
            resp = _CLIENT.post(_API_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                time.sleep(3 * (2**attempt))
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"].get("content", "").strip()
            content = strip_ai_monologue(content)
            if is_valid_synthetic_queries(content):
                return content[:4000]
            else:
                logger.warning(f"Generated queries failed validation: {content[:80]}")
                return ""
        except Exception as exc:
            if attempt == 2:
                logger.warning(f"Failed after 3 attempts: {exc}")
                return ""
            time.sleep(3 * (2**attempt))
    return ""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    json_files = sorted(glob.glob(os.path.join(EXPORT_JSON_DIR, "*.json")))
    json_files = [f for f in json_files if not f.endswith(".bak")]
    logger.info(f"Found {len(json_files)} JSON exports in {EXPORT_JSON_DIR}")

    # Stage 1: Sanitize corrupted existing chunks (strip reasoning leaks, deprecation, fix source_category)
    sanitized_count = 0
    for path in json_files:
        try:
            raw_text = Path(path).read_text(errors="replace")
            data = json.loads(raw_text)
        except Exception as e:
            logger.warning(f"Skip sanitize (parse error): {path}: {e}")
            continue
        modified = False

        orig_path = data.get("original_path") or Path(path).name
        cat = classify_source_category(orig_path)
        if data.get("metadata", {}).get("source_category") != cat:
            if "metadata" not in data:
                data["metadata"] = {}
            data["metadata"]["source_category"] = cat
            modified = True

        for chunk in data.get("chunks", []):
            if chunk.get("source_category") != cat:
                chunk["source_category"] = cat
                modified = True

            # Sanitize chunk text from OCR monologue & prompt leakages
            old_text = chunk.get("text", "")
            cleaned_text = strip_ai_monologue(old_text)
            if cleaned_text != old_text:
                chunk["text"] = cleaned_text
                modified = True

            # Validate synthetic queries
            sq = chunk.get("synthetic_queries", "")
            if sq:
                cleaned_sq = strip_ai_monologue(sq)
                if not is_valid_synthetic_queries(cleaned_sq):
                    chunk["synthetic_queries"] = ""
                    modified = True
                    sanitized_count += 1
                elif cleaned_sq != sq:
                    chunk["synthetic_queries"] = cleaned_sq
                    modified = True

        if modified and not DRY_RUN:
            Path(path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    if sanitized_count > 0:
        logger.info(f"Sanitized {sanitized_count} corrupt or deprecation-infected chunks.")

    # Stage 2: Collect all parent chunks missing synthetic_queries
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
                and not is_valid_synthetic_queries(chunk.get("synthetic_queries", ""))
            ):
                todo.append((path, data, chunk))

    total = len(todo)
    logger.info(f"Found {total} parent chunks without valid synthetic_queries")

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
                and not is_valid_synthetic_queries(chunk.get("synthetic_queries", ""))
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

            if (done + errors) % 10 == 0:
                logger.info(f"  Progress: {done + errors}/{len(flat_tasks)} (done={done}, err={errors})")
                # Checkpoint save modified files
                for p in dirty_files:
                    try:
                        Path(p).write_text(
                            json.dumps(file_data[p], ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    except Exception as save_err:
                        logger.warning(f"Checkpoint save error for {p}: {save_err}")

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
