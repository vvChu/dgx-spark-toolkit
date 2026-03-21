"""Runner mixin — entry points, queue consumer, and filesystem watchers."""
import logging
import os
import threading
import time

from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from ingestion.pipeline_config import SOURCE_DIR, MAX_WORKERS

logger = logging.getLogger(__name__)


class RunnerMixin:
    """Entry points and worker loop management."""

    def run(self):
        """Main entry point: scan → enqueue → consume.

        Mode 1 (Redis available): Scan files → push to Redis Stream → consume
        Mode 2 (Fallback):        Scan files → process directly with ThreadPoolExecutor
        """
        try:
            from ingestion.queue import RedisQueue
            self._queue = RedisQueue()
            logger.info("Redis queue connected ✓ — using queue-based ingestion")
        except Exception as e:
            self._queue = None
            logger.warning(f"Redis queue unavailable, using legacy mode: {e}")

        if self._queue:
            self._scan_and_enqueue()
            self._consume_queue()
        else:
            self._run_legacy()

    def _scan_and_enqueue(self):
        """Scan filesystem and push all unprocessed files to Redis Stream."""
        logger.info("Scanning filesystem for PDF files...")
        pdf_files = []
        for root, _, files in os.walk(SOURCE_DIR):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, file))

        logger.info(f"Found {len(pdf_files)} PDF files. Filtering already-queued...")

        to_enqueue = []
        for f in pdf_files:
            rel_path = os.path.relpath(f, SOURCE_DIR)
            with self._processed_cache_lock:
                if rel_path in self.processed_cache:
                    continue
            if self._queue.is_file_queued(rel_path):
                continue
            to_enqueue.append({
                "file_path": f,
                "rel_path": rel_path,
                "content_hash": "",
            })

        if to_enqueue:
            _PRIORITY_PATTERNS = ['BXD-GTVT', 'QCVN']

            def _priority_key(item):
                rp = item["rel_path"]
                for i, pat in enumerate(_PRIORITY_PATTERNS):
                    if pat in rp:
                        return (0, i, rp)
                return (1, 0, rp)

            to_enqueue.sort(key=_priority_key)
            priority_count = sum(1 for x in to_enqueue if any(p in x['rel_path'] for p in _PRIORITY_PATTERNS))
            logger.info(f"Priority: {priority_count} priority files (BXD-GTVT/QCVN) queued first")

            self._queue.enqueue_batch(to_enqueue)
            for f in to_enqueue:
                self._queue.mark_queued(f["rel_path"])
        else:
            logger.info("No new files to enqueue")

    def _consume_queue(self):
        """Consumer loop: claim messages from Redis → process → ack/nack."""
        logger.info(f"Starting consumer loop (worker: {self._queue.consumer_id})...")

        event_handler = _QueueWatchHandler(self)
        observer = Observer()
        observer.schedule(event_handler, SOURCE_DIR, recursive=True)
        observer.start()

        try:
            while True:
                messages = self._queue.claim_next(count=1, block_ms=5000)
                if not messages:
                    self._queue.update_metrics()
                    continue

                for msg in messages:
                    file_path = msg.get("file_path", "")
                    msg_id = msg.get("msg_id", "")

                    if not file_path or not os.path.exists(file_path):
                        self._queue.ack(msg_id)
                        continue

                    try:
                        self.safe_process(file_path)
                        self._queue.ack(msg_id)
                    except Exception as e:
                        self._queue.nack(msg_id, str(e))

                self._queue.update_metrics()
        except KeyboardInterrupt:
            logger.info("Consumer loop interrupted")
            observer.stop()
        observer.join()

    def _run_legacy(self):
        """Legacy mode: direct filesystem polling with ThreadPoolExecutor."""
        logger.info(f"Starting parallel ingestion scan (legacy mode)...")
        pdf_files = []
        for root, _, files in os.walk(SOURCE_DIR):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, file))

        logger.info(f"Found {len(pdf_files)} PDF files. Processing with {MAX_WORKERS} workers...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            executor.map(self.safe_process, pdf_files)

        logger.info("Initial scan complete. Starting live watch...")
        event_handler = _LegacyWatchHandler(self)
        observer = Observer()
        observer.schedule(event_handler, SOURCE_DIR, recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


class _QueueWatchHandler(FileSystemEventHandler):
    """File watcher that enqueues new files to Redis instead of processing directly."""

    def __init__(self, ingestor):
        self.ingestor = ingestor

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.pdf'):
            rel_path = os.path.relpath(event.src_path, SOURCE_DIR)
            logger.info(f"New file detected, enqueuing: {rel_path}")
            time.sleep(2)
            try:
                self.ingestor._queue.enqueue(event.src_path, "", rel_path)
                self.ingestor._queue.mark_queued(rel_path)
            except Exception as e:
                logger.error(f"Failed to enqueue new file: {e}")


class _LegacyWatchHandler(FileSystemEventHandler):
    """Legacy file watcher (used when Redis is unavailable)."""

    def __init__(self, ingestor):
        self.ingestor = ingestor
        self._active_threads: set = set()

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.pdf'):
            logger.info(f"New file detected: {event.src_path}")

            def _process(path):
                time.sleep(2)
                try:
                    self.ingestor.process_file(path)
                except Exception as e:
                    logger.error(f"Error processing new file {path}: {e}")
                finally:
                    self._active_threads.discard(threading.current_thread())

            t = threading.Thread(target=_process, args=(event.src_path,), daemon=True)
            self._active_threads.add(t)
            t.start()
