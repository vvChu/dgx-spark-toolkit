"""Unit tests for LiteLLM SpendLogs & Health Check Pruning Script."""

import gzip
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Ensure scripts dir is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import prune_spend_logs


def test_argument_parser_defaults():
    with patch("sys.argv", ["prune_spend_logs.py"]):
        parser = prune_spend_logs.argparse.ArgumentParser()
        # Test default values
        assert prune_spend_logs.DEFAULT_ARCHIVE_DIR == "archives/spendlogs"
        assert prune_spend_logs.DEFAULT_DATABASE_URL.startswith("postgresql://")


def test_log_output(capsys):
    prune_spend_logs.log("Testing logging output")
    captured = capsys.readouterr()
    assert "Testing logging output" in captured.out


@patch("prune_spend_logs.execute_sql")
def test_get_table_size(mock_execute_sql):
    mock_execute_sql.return_value = (1, [("105 MB",)])
    size = prune_spend_logs.get_table_size("LiteLLM_SpendLogs")
    assert size == "105 MB"
    mock_execute_sql.assert_called_once()


@patch("prune_spend_logs.execute_sql")
def test_prune_logs_dry_run(mock_execute_sql):
    mock_execute_sql.return_value = (1, [(1340,)])
    deleted = prune_spend_logs.prune_logs(retention_days=30, dry_run=True)
    assert deleted == 1340


@patch("prune_spend_logs.execute_sql")
def test_prune_logs_empty(mock_execute_sql):
    mock_execute_sql.return_value = (1, [(0,)])
    deleted = prune_spend_logs.prune_logs(retention_days=30, dry_run=False)
    assert deleted == 0


@patch("prune_spend_logs.execute_sql")
def test_archive_spend_logs(mock_execute_sql, tmp_path):
    mock_records = [
        (json.dumps({"request_id": "req-1", "spend": 0.05, "total_tokens": 100}),),
        (json.dumps({"request_id": "req-2", "spend": 0.12, "total_tokens": 250}),),
    ]
    # First call: count sql, Second call: fetch sql
    mock_execute_sql.side_effect = [
        (1, [(2,)]),
        (2, mock_records),
    ]

    archive_file = prune_spend_logs.archive_spend_logs(
        retention_days=30,
        archive_dir=str(tmp_path),
        dry_run=False,
    )
    assert archive_file is not None
    assert Path(archive_file).exists()

    # Read back gzip
    with gzip.open(archive_file, "rt", encoding="utf-8") as f_in:
        lines = [json.loads(line) for line in f_in if line.strip()]
    assert len(lines) == 2
    assert lines[0]["request_id"] == "req-1"
    assert lines[1]["request_id"] == "req-2"


@patch("prune_spend_logs.execute_sql")
def test_prune_health_checks_dry_run(mock_execute_sql):
    mock_execute_sql.return_value = (1, [(50,)])
    deleted = prune_spend_logs.prune_health_checks(retention_days=7, dry_run=True)
    assert deleted == 50


@patch("prune_spend_logs.execute_sql")
def test_vacuum_table(mock_execute_sql):
    mock_execute_sql.return_value = (0, [])
    prune_spend_logs.vacuum_table("LiteLLM_SpendLogs", full=False)
    mock_execute_sql.assert_called_with('VACUUM ANALYZE "LiteLLM_SpendLogs";')

    mock_execute_sql.reset_mock()
    prune_spend_logs.vacuum_table("LiteLLM_SpendLogs", full=True)
    mock_execute_sql.assert_called_with('VACUUM FULL "LiteLLM_SpendLogs";')


@patch("prune_spend_logs.execute_sql")
@patch("prune_spend_logs.archive_spend_logs")
def test_chunked_deletion_loop(mock_archive, mock_execute_sql):
    # Simulate candidates: 10, then after first chunk 0 remaining
    mock_execute_sql.side_effect = [
        (1, [(10,)]),  # initial count
        (5, []),       # first chunk delete
        (1, [(0,)]),   # remaining check -> 0
    ]
    total = prune_spend_logs.prune_logs(
        retention_days=30,
        batch_size=5,
        dry_run=False,
        archive_dir=None,
    )
    assert total == 10
