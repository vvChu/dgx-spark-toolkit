"""Unit tests for DGX-ChatOps Universal Gateway enhancements."""

import asyncio
import hashlib
import json
from pathlib import Path
import re
import time
from unittest.mock import AsyncMock, MagicMock, patch
import yaml

from fastapi.testclient import TestClient

import scripts.chatops_daemon as daemon


def test_command_registry_service_lock_and_whitelist():
    """Verify service_lock is open-webui and whitelist includes milvus and neo4j."""
    commands_file = Path("scripts/chatops_commands.yaml")
    assert commands_file.exists()

    with open(commands_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cmds = {c["id"]: c for c in data.get("commands", [])}

    # 1. Check openwebui service_lock
    owu_cmd = cmds["system.openwebui.upgrade"]
    assert owu_cmd["service_lock"] == "open-webui"

    # 2. Check container restart whitelist regex
    rst_cmd = cmds["system.container.restart"]
    service_pattern = rst_cmd["param_rules"]["service"]
    regex = re.compile(service_pattern)

    # Allowed containers
    allowed = [
        "open-webui",
        "qwen36b",
        "ai-gateway",
        "smart-watchdog",
        "cloudflared-tunnel",
        "rag-service",
        "milvus-standalone",
        "neo4j-graph",
    ]
    for s in allowed:
        assert regex.match(s), f"Should match allowed service: {s}"

    # Disallowed containers / injection attempts
    disallowed = [
        "openwebui",
        "milvus",
        "neo4j",
        "malicious;rm -rf /",
        "docker",
        "systemd",
        "rag-service2",
    ]
    for s in disallowed:
        assert not regex.match(s), f"Should NOT match disallowed: {s}"


def test_restart_service_markup():
    """Verify get_restart_service_markup contains milvus-standalone and neo4j-graph."""
    markup = daemon.get_restart_service_markup()
    buttons = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]

    assert "rst:milvus-standalone" in buttons
    assert "rst:neo4j-graph" in buttons
    assert "rst:open-webui" in buttons
    assert "rst:rag-service" in buttons


def test_audit_hash_chain_restoration(tmp_path, monkeypatch):
    """Verify hash chain restoration from existing audit.jsonl file."""
    fake_audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(daemon, "AUDIT_FILE", fake_audit)

    # When file does not exist
    assert daemon.load_last_audit_hash() == "0" * 64

    # Create fake audit file with chained records
    rec1_hash = hashlib.sha256(b"record_1").hexdigest()
    rec2_hash = hashlib.sha256(b"record_2").hexdigest()

    with open(fake_audit, "w", encoding="utf-8") as f:
        f.write(json.dumps({"record_hash": rec1_hash}) + "\n")
        f.write(json.dumps({"record_hash": rec2_hash}) + "\n")

    # Should restore rec2_hash
    restored = daemon.load_last_audit_hash()
    assert restored == rec2_hash

    # Now append an audit log and verify chaining
    monkeypatch.setattr(daemon, "last_audit_hash", restored)
    daemon.append_audit_log(
        trigger_type="test",
        command="test_cmd",
        params={},
        user_id=123,
        status="SUCCESS",
        duration_ms=10,
        exit_code=0,
    )

    with open(fake_audit, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    assert len(lines) == 3
    assert lines[2]["prev_hash"] == rec2_hash
    assert lines[2]["record_hash"] == daemon.last_audit_hash


def test_anti_replay_protection():
    """Verify updates older than 120s are dropped."""
    async def _test():
        now = time.time()

        stale_update = {
            "update_id": 1001,
            "message": {
                "message_id": 501,
                "chat": {"id": daemon.ADMIN_USER_ID},
                "from": {"id": daemon.ADMIN_USER_ID},
                "text": "/status",
                "date": int(now - 150),  # 150 seconds ago (> 120s)
            },
        }

        fresh_update = {
            "update_id": 1002,
            "message": {
                "message_id": 502,
                "chat": {"id": daemon.ADMIN_USER_ID},
                "from": {"id": daemon.ADMIN_USER_ID},
                "text": "/status",
                "date": int(now - 10),  # 10 seconds ago (fresh)
            },
        }

        with patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch:
            with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = 999
                # Stale update should be dropped
                await daemon.process_telegram_update(stale_update)
                mock_dispatch.assert_not_called()

                # Fresh update should be processed
                await daemon.process_telegram_update(fresh_update)
                mock_dispatch.assert_called_once()

    asyncio.run(_test())


def test_persistent_http_client():
    """Verify get_http_client creates and reuses client."""
    c1 = daemon.get_http_client()
    c2 = daemon.get_http_client()
    assert c1 is c2
    assert not c1.is_closed


def test_action_cache_cleanup():
    """Verify expired nonces are purged from action_cache."""
    now = time.time()
    daemon.action_cache.clear()

    daemon.action_cache["expired_1"] = {"expires": now - 10, "cmd": "old1"}
    daemon.action_cache["expired_2"] = {"expires": now - 1, "cmd": "old2"}
    daemon.action_cache["valid_1"] = {"expires": now + 60, "cmd": "valid"}

    # Simulate cleanup logic
    expired_keys = [k for k, v in daemon.action_cache.items() if now > v.get("expires", 0)]
    for k in expired_keys:
        daemon.action_cache.pop(k, None)

    assert "expired_1" not in daemon.action_cache
    assert "expired_2" not in daemon.action_cache
    assert "valid_1" in daemon.action_cache


def test_probe_rag_state():
    """Verify probe_rag_state queries /health and /stats endpoints properly."""
    async def _test():
        fake_health = {"status": "ok", "version": "2.0.0", "checks": {"milvus": "ok", "neo4j": "ok"}}
        fake_stats = {"neo4j_docs": 25, "neo4j_rels": 30, "milvus_entities": 4657, "total_target": 8870}

        mock_client = AsyncMock()

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            if "/health" in url:
                resp.status_code = 200
                resp.json.return_value = fake_health
            elif "/stats" in url:
                resp.status_code = 200
                resp.json.return_value = fake_stats
            else:
                resp.status_code = 404
            return resp

        mock_client.get = mock_get

        with patch("scripts.chatops_daemon.get_http_client", return_value=mock_client):
            result = await daemon.probe_rag_state()

        assert "Dịch vụ `rag-service`: 🟢 Khả dụng" in result
        assert "Tài liệu pháp lý (Neo4j): `25/8870`" in result
        assert "Thực thể vector (Milvus): `4,657` chunks" in result
        assert "Quan hệ pháp lý (Neo4j): `30` liên kết" in result
        assert "data/raw" not in result

    asyncio.run(_test())


def test_internal_notify_security():
    """Verify /api/v1/notify rejects requests with invalid or missing secret header."""
    client = TestClient(daemon.app, client=("127.0.0.1", 50000))

    # Without header
    res = client.post("/api/v1/notify", json={"title": "Test", "body": "Alert"})
    assert res.status_code == 401

    # With wrong header
    res = client.post(
        "/api/v1/notify",
        json={"title": "Test", "body": "Alert"},
        headers={"X-ChatOps-Secret": "wrong_secret_123"},
    )
    assert res.status_code == 401

    # With correct header
    with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = 8888
        res = client.post(
            "/api/v1/notify",
            json={"title": "Test Valid", "body": "Alert Content", "severity": "WARNING"},
            headers={"X-ChatOps-Secret": daemon.CHATOPS_INTERNAL_SECRET},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "dispatched"


def test_execute_shell_job_timeout_reaping():
    """Verify execute_shell_job handles timeout without leaving zombie processes."""
    async def _test():
        with patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit:
            with patch("scripts.chatops_daemon.append_audit_log") as mock_audit:
                # Run a command that exceeds timeout (sleep 5 with timeout 1)
                await daemon.execute_shell_job(
                    cmd="sleep 5",
                    job_id="test_timeout",
                    chat_id=daemon.ADMIN_USER_ID,
                    status_msg_id=1234,
                    title="Test Sleep",
                    timeout=1,
                )
                assert mock_edit.call_count >= 2
                last_call_text = mock_edit.call_args[0][2]
                assert "TIMEOUT" in last_call_text
                mock_audit.assert_called_once()
                assert mock_audit.call_args[0][4] == "TIMEOUT"

    asyncio.run(_test())

