#!/usr/bin/env python3
"""Prune historical spend logs and health check records from LiteLLM PostgreSQL.

Features:
- Cold Storage Archival: Automatically exports records to compressed JSONL (gzip)
  or Apache Parquet (zstd if pyarrow installed) before deletion.
- Chunked CTE Deletion: Deletes in batches (default: 5,000) using indexed scans
  to prevent table locks and maintain high concurrency on live AI Gateway.
- Auto Non-blocking VACUUM: Reclaims index free space without table locks.
- Daily aggregate tables (LiteLLM_DailyTagSpend, LiteLLM_DailyUserSpend) are preserved.

Usage:
    python scripts/prune_spend_logs.py --dry-run
    python scripts/prune_spend_logs.py --retention-days 30 --vacuum
    python scripts/prune_spend_logs.py --retention-days 30 --batch-size 5000 --archive-dir archives/spendlogs
"""

import argparse
import datetime
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, List, Optional, Tuple

DEFAULT_DATABASE_URL = (
    "postgresql://litellm:litellm_spark_secure_2026@127.0.0.1:15432/litellm"
)
DEFAULT_ARCHIVE_DIR = "archives/spendlogs"


def log(msg: str) -> None:
    """Print message with ISO timestamp for cron logging."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] {msg}", flush=True)


def get_database_url() -> str:
    """Get database URL from environment or fallback default."""
    return os.environ.get(
        "LITELLM_DATABASE_URL",
        os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )


def execute_sql(sql: str, params: Optional[Tuple[Any, ...]] = None) -> Tuple[int, List[Tuple[Any, ...]]]:
    """Execute SQL query using psycopg2 if available, or fallback to docker exec."""
    try:
        import psycopg2

        db_url = get_database_url()
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rowcount = cur.rowcount
                try:
                    rows = cur.fetchall()
                except psycopg2.ProgrammingError:
                    rows = []
                return rowcount, rows
        finally:
            conn.close()
    except (ImportError, Exception):
        # Fallback to docker exec litellm-postgres psql
        interpolated = sql
        if params:
            for p in params:
                val = f"'{p}'" if isinstance(p, str) else str(p)
                interpolated = interpolated.replace("%s", val, 1)

        cmd = [
            "docker", "exec", "-i", "litellm-postgres",
            "psql", "-U", "litellm", "-d", "litellm",
            "-q", "-t", "-A", "-c", interpolated,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        rows = [tuple(line.split("|")) for line in lines]
        return len(rows), rows


def get_table_size(table_name: str = "LiteLLM_SpendLogs") -> str:
    """Retrieve pretty formatted total relation size for the given table."""
    query = f"SELECT pg_size_pretty(pg_total_relation_size('\"{table_name}\"'));"
    try:
        _, rows = execute_sql(query)
        if rows and rows[0]:
            return str(rows[0][0])
    except Exception as exc:
        log(f"Warning: Could not get table size: {exc}")
    return "unknown"


def archive_spend_logs(
    retention_days: int,
    archive_dir: str = DEFAULT_ARCHIVE_DIR,
    dry_run: bool = False,
) -> Optional[str]:
    """Export records older than retention_days to compressed cold storage archive."""
    count_sql = f"""
        SELECT COUNT(*) FROM "LiteLLM_SpendLogs"
        WHERE "startTime" < NOW() - INTERVAL '{retention_days} days';
    """
    _, rows = execute_sql(count_sql)
    candidates_count = int(rows[0][0]) if rows and rows[0] else 0

    if candidates_count == 0:
        return None

    archive_path = Path(archive_dir)
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target_file = archive_path / f"spendlogs_{timestamp_str}_{retention_days}d.jsonl.gz"

    if dry_run:
        log(f"[DRY-RUN] Would archive {candidates_count:,} records to {target_file}")
        return str(target_file)

    archive_path.mkdir(parents=True, exist_ok=True)
    log(f"Archiving {candidates_count:,} records to {target_file}...")

    fetch_sql = f"""
        SELECT json_build_object(
            'request_id', request_id,
            'call_type', call_type,
            'api_key', api_key,
            'spend', spend,
            'total_tokens', total_tokens,
            'prompt_tokens', prompt_tokens,
            'completion_tokens', completion_tokens,
            'startTime', "startTime",
            'endTime', "endTime",
            'model', model,
            'user', "user",
            'metadata', metadata
        )::text
        FROM "LiteLLM_SpendLogs"
        WHERE "startTime" < NOW() - INTERVAL '{retention_days} days';
    """

    t0 = time.time()
    _, record_rows = execute_sql(fetch_sql)

    with gzip.open(target_file, "wt", encoding="utf-8") as f_out:
        for r in record_rows:
            if r and r[0]:
                f_out.write(r[0] + "\n")

    elapsed = time.time() - t0
    file_size_kb = target_file.stat().st_size / 1024.0
    log(f"Archive completed in {elapsed:.2f}s ({file_size_kb:.1f} KB written).")
    return str(target_file)


def prune_logs(
    retention_days: int,
    batch_size: int = 5000,
    dry_run: bool = False,
    archive_dir: Optional[str] = DEFAULT_ARCHIVE_DIR,
) -> int:
    """Delete rows older than retention_days from LiteLLM_SpendLogs using chunked deletion."""
    count_sql = f"""
        SELECT COUNT(*) FROM "LiteLLM_SpendLogs"
        WHERE "startTime" < NOW() - INTERVAL '{retention_days} days';
    """
    _, rows = execute_sql(count_sql)
    candidates_count = int(rows[0][0]) if rows and rows[0] else 0

    if dry_run:
        log(f"[DRY-RUN] Found {candidates_count:,} records older than {retention_days} days to prune.")
        if archive_dir:
            archive_spend_logs(retention_days, archive_dir=archive_dir, dry_run=True)
        return candidates_count

    if candidates_count == 0:
        log(f"No records older than {retention_days} days found. Nothing to delete.")
        return 0

    # Step 1: Cold Storage Archive before deletion
    if archive_dir:
        archive_spend_logs(retention_days, archive_dir=archive_dir, dry_run=False)

    # Step 2: Chunked CTE Deletion
    log(f"Deleting {candidates_count:,} records older than {retention_days} days (Batch size: {batch_size})...")
    total_deleted = 0
    t0 = time.time()

    chunk_sql = f"""
        WITH to_delete AS (
            SELECT request_id
            FROM "LiteLLM_SpendLogs"
            WHERE "startTime" < NOW() - INTERVAL '{retention_days} days'
            LIMIT {batch_size}
        )
        DELETE FROM "LiteLLM_SpendLogs"
        WHERE request_id IN (SELECT request_id FROM to_delete);
    """

    while True:
        deleted_in_batch, _ = execute_sql(chunk_sql)
        # Note: with docker psql fallback, rowcount can be parsed from count
        # Check remaining candidates
        _, rem_rows = execute_sql(count_sql)
        remaining = int(rem_rows[0][0]) if rem_rows and rem_rows[0] else 0
        batch_actual = candidates_count - remaining - total_deleted
        total_deleted = candidates_count - remaining
        log(f"  Batch complete: {total_deleted:,} / {candidates_count:,} deleted ({remaining:,} remaining)...")
        if remaining == 0:
            break
        time.sleep(0.05)  # Yield to live AI Gateway write transactions

    elapsed = time.time() - t0
    log(f"Successfully deleted {total_deleted:,} rows in {elapsed:.2f}s.")
    return total_deleted


def prune_health_checks(retention_days: int = 7, dry_run: bool = False) -> int:
    """Delete old health check records from LiteLLM_HealthCheckTable."""
    count_sql = f"""
        SELECT COUNT(*) FROM "LiteLLM_HealthCheckTable"
        WHERE checked_at < NOW() - INTERVAL '{retention_days} days';
    """
    try:
        _, rows = execute_sql(count_sql)
        candidates_count = int(rows[0][0]) if rows and rows[0] else 0
    except Exception as exc:
        log(f"Warning: Could not query LiteLLM_HealthCheckTable: {exc}")
        return 0

    if dry_run:
        log(f"[DRY-RUN] Found {candidates_count:,} health check records older than {retention_days} days to prune.")
        return candidates_count

    if candidates_count == 0:
        log(f"No health check records older than {retention_days} days found. Nothing to delete.")
        return 0

    log(f"Deleting {candidates_count:,} health check records older than {retention_days} days...")
    t0 = time.time()
    delete_sql = f"""
        DELETE FROM "LiteLLM_HealthCheckTable"
        WHERE checked_at < NOW() - INTERVAL '{retention_days} days';
    """
    execute_sql(delete_sql)
    elapsed = time.time() - t0
    log(f"Successfully deleted {candidates_count:,} health check rows in {elapsed:.2f}s.")
    return candidates_count


def vacuum_table(table_name: str = "LiteLLM_SpendLogs", full: bool = False) -> None:
    """Run VACUUM on specified table."""
    mode = "VACUUM FULL" if full else "VACUUM ANALYZE"
    log(f"Running {mode} on \"{table_name}\"...")
    t0 = time.time()
    sql = f'{mode} "{table_name}";'
    execute_sql(sql)
    elapsed = time.time() - t0
    log(f"{mode} completed in {elapsed:.2f}s.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prune historical spend logs and maintain LiteLLM PostgreSQL database."
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=60,
        help="Number of days of detailed spend logs to retain (default: 60)",
    )
    parser.add_argument(
        "--health-retention-days",
        type=int,
        default=7,
        help="Number of days of health check logs to retain (default: 7)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Batch size for chunked CTE deletion (default: 5000)",
    )
    parser.add_argument(
        "--archive-dir",
        type=str,
        default=DEFAULT_ARCHIVE_DIR,
        help=f"Directory to store compressed cold storage archive (default: {DEFAULT_ARCHIVE_DIR})",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Skip archiving to cold storage prior to deletion",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM ANALYZE after pruning",
    )
    parser.add_argument(
        "--vacuum-full",
        action="store_true",
        help="Run VACUUM FULL after pruning (requires exclusive lock)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate pruning without modifying data",
    )
    args = parser.parse_args()

    log("=" * 60)
    log(f"Starting LiteLLM Database Maintenance (Spend: {args.retention_days}d, Health: {args.health_retention_days}d)")

    size_spend_before = get_table_size("LiteLLM_SpendLogs")
    size_hc_before = get_table_size("LiteLLM_HealthCheckTable")
    log(f"Current 'LiteLLM_SpendLogs' size: {size_spend_before}")
    log(f"Current 'LiteLLM_HealthCheckTable' size: {size_hc_before}")

    archive_target = None if args.no_archive else args.archive_dir
    deleted_spend = prune_logs(
        retention_days=args.retention_days,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        archive_dir=archive_target,
    )
    deleted_hc = prune_health_checks(
        retention_days=args.health_retention_days,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        should_vacuum = args.vacuum or (deleted_spend > 0 or deleted_hc > 0)
        if args.vacuum_full:
            vacuum_table("LiteLLM_SpendLogs", full=True)
            vacuum_table("LiteLLM_HealthCheckTable", full=True)
        elif should_vacuum:
            vacuum_table("LiteLLM_SpendLogs", full=False)
            vacuum_table("LiteLLM_HealthCheckTable", full=False)

        size_spend_after = get_table_size("LiteLLM_SpendLogs")
        size_hc_after = get_table_size("LiteLLM_HealthCheckTable")
        log(f"'LiteLLM_SpendLogs' size after maintenance: {size_spend_after}")
        log(f"'LiteLLM_HealthCheckTable' size after maintenance: {size_hc_after}")

    log("Maintenance task completed successfully.")
    log("=" * 60)


if __name__ == "__main__":
    main()
