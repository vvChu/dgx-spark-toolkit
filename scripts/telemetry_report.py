#!/usr/bin/env python3
"""Telemetry & Performance Analytics Report for DGX Spark AI Gateway.

Queries PostgreSQL database (`litellm`) to aggregate token usage, request volume,
latency distributions (P50/P90/P99), and success rates across served models.

Usage:
    python scripts/telemetry_report.py
    python scripts/telemetry_report.py --days 14
    python scripts/telemetry_report.py --model qwen-local-primary
    python scripts/telemetry_report.py --format json
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DATABASE_URL = (
    "postgresql://litellm:litellm_spark_secure_2026@127.0.0.1:15432/litellm"
)


def get_connection_url() -> str:
    """Retrieve database connection URL from environment or default."""
    return os.environ.get(
        "LITELLM_DATABASE_URL",
        os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )


def query_db_psycopg2(sql: str, params: Optional[Tuple[Any, ...]] = None) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    """Execute SQL query using native psycopg2 driver."""
    import psycopg2

    db_url = get_connection_url()
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                columns = [col[0] for col in cur.description]
                rows = cur.fetchall()
                return columns, rows
            return [], []
    finally:
        conn.close()


def query_db_docker_exec(sql: str) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    """Fallback: Execute SQL query via docker exec psql if psycopg2 is absent."""
    cmd = [
        "docker", "exec", "-i", "litellm-postgres",
        "psql", "-U", "litellm", "-d", "litellm",
        "--csv", "-c", sql
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    reader = csv.reader(io.StringIO(result.stdout.strip()))
    lines = list(reader)
    if not lines:
        return [], []
    columns = lines[0]
    rows = [tuple(r) for r in lines[1:]]
    return columns, rows


def execute_query(sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
    """Execute SQL query using psycopg2 if available, or docker exec fallback."""
    try:
        import psycopg2  # noqa: F401
        columns, rows = query_db_psycopg2(sql, params)
    except (ImportError, Exception) as exc:
        if isinstance(exc, ImportError):
            pass  # Fall back to docker exec
        else:
            # If native connection fails (e.g. host port blocked), try docker exec
            pass
        # Fallback to docker exec
        interpolated_sql = sql
        if params:
            # Safe basic interpolation for simple parameter types
            for p in params:
                val = f"'{p}'" if isinstance(p, str) else str(p)
                interpolated_sql = interpolated_sql.replace("%s", val, 1)
        columns, rows = query_db_docker_exec(interpolated_sql)

    result = []
    for row in rows:
        result.append(dict(zip(columns, row)))
    return result


def fetch_model_telemetry(days: int, model_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query model performance statistics for the past N days."""
    sql = """
        SELECT 
            model,
            COUNT(*) AS total_requests,
            ROUND(COUNT(*) FILTER (WHERE status = 'success')::numeric / NULLIF(COUNT(*), 0) * 100, 1) AS success_rate_pct,
            SUM(total_tokens) AS total_tokens,
            SUM(prompt_tokens) AS prompt_tokens,
            SUM(completion_tokens) AS completion_tokens,
            ROUND(AVG(EXTRACT(EPOCH FROM ("endTime" - "startTime")))::numeric, 2) AS avg_latency_s,
            ROUND(percentile_cont(0.50) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM ("endTime" - "startTime")))::numeric, 2) AS p50_latency_s,
            ROUND(percentile_cont(0.90) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM ("endTime" - "startTime")))::numeric, 2) AS p90_latency_s,
            ROUND(percentile_cont(0.99) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM ("endTime" - "startTime")))::numeric, 2) AS p99_latency_s
        FROM "LiteLLM_SpendLogs"
        WHERE "startTime" >= NOW() - INTERVAL '%s days'
    """
    params: List[Any] = [days]

    if model_filter:
        sql += " AND model ILIKE %s"
        params.append(f"%{model_filter}%")

    sql += """
        GROUP BY model
        ORDER BY total_requests DESC
    """
    return execute_query(sql, tuple(params))


def fetch_daily_trend(days: int) -> List[Dict[str, Any]]:
    """Query daily request volume and token count trend."""
    sql = """
        SELECT 
            DATE("startTime") AS date,
            COUNT(*) AS requests,
            SUM(total_tokens) AS tokens,
            COUNT(DISTINCT model) AS active_models
        FROM "LiteLLM_SpendLogs"
        WHERE "startTime" >= NOW() - INTERVAL '%s days'
        GROUP BY DATE("startTime")
        ORDER BY date DESC
    """
    return execute_query(sql, (days,))


def format_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Format tabular data into an aligned Markdown table."""
    str_rows = [[str(cell if cell is not None else "") for cell in row] for row in rows]
    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for idx, cell in enumerate(row):
            if len(cell) > col_widths[idx]:
                col_widths[idx] = len(cell)

    header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    separator_line = "|-" + "-|-".join("-" * col_widths[i] for i in range(len(headers))) + "-|"
    data_lines = [
        "| " + " | ".join(row[i].ljust(col_widths[i]) for i in range(len(headers))) + " |"
        for row in str_rows
    ]
    return "\n".join([header_line, separator_line] + data_lines)


def print_report(days: int, model_filter: Optional[str] = None, output_format: str = "table") -> None:
    """Generate and display the telemetry report."""
    models_data = fetch_model_telemetry(days, model_filter)
    daily_data = fetch_daily_trend(days)

    if output_format == "json":
        output = {
            "window_days": days,
            "filter_model": model_filter,
            "models": models_data,
            "daily_trend": daily_data,
        }
        print(json.dumps(output, indent=2, default=str))
        return

    # Markdown Table Output
    print(f"\n# 📊 AI Gateway Telemetry Report (Past {days} Days)")
    if model_filter:
        print(f"Filter Model: `{model_filter}`\n")
    else:
        print("Scope: All Models\n")

    total_requests = sum(int(m.get("total_requests", 0)) for m in models_data)
    total_tokens = sum(int(m.get("total_tokens", 0) or 0) for m in models_data)
    print(f"- **Total Requests**: {total_requests:,}")
    print(f"- **Total Tokens Logged**: {total_tokens:,}")
    print(f"- **Active Models**: {len(models_data)}\n")

    print("### Model Performance Breakdown")
    headers = [
        "Model", "Requests", "Success %", "Total Tokens", 
        "Avg Lat (s)", "P50 (s)", "P90 (s)", "P99 (s)"
    ]
    rows = []
    for m in models_data:
        req = int(m.get("total_requests", 0))
        tok = int(m.get("total_tokens", 0) or 0)
        rows.append([
            m.get("model", ""),
            f"{req:,}",
            f"{m.get('success_rate_pct', 0)}%",
            f"{tok:,}",
            f"{m.get('avg_latency_s', 0)}",
            f"{m.get('p50_latency_s', 0)}",
            f"{m.get('p90_latency_s', 0)}",
            f"{m.get('p99_latency_s', 0)}",
        ])
    print(format_table(headers, rows))

    if daily_data:
        print("\n### Daily Request Volume Trend")
        d_headers = ["Date", "Requests", "Tokens", "Active Models"]
        d_rows = []
        for d in daily_data:
            req = int(d.get("requests", 0))
            tok = int(d.get("tokens", 0) or 0)
            d_rows.append([
                str(d.get("date", "")),
                f"{req:,}",
                f"{tok:,}",
                str(d.get("active_models", "")),
            ])
        print(format_table(d_headers, d_rows))
    print("")


def main() -> None:
    """Parse CLI arguments and run telemetry report."""
    parser = argparse.ArgumentParser(
        description="Query and analyze AI Gateway telemetry from LiteLLM PostgreSQL."
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Number of past days to analyze (default: 7)"
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Filter by model name substring"
    )
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", help="Output format"
    )
    args = parser.parse_args()

    print_report(days=args.days, model_filter=args.model, output_format=args.format)


if __name__ == "__main__":
    main()
