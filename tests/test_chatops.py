"""Comprehensive unit tests for DGX-ChatOps Universal Gateway."""

import asyncio
import hashlib
import json
from pathlib import Path
import re
import time
from unittest.mock import AsyncMock, MagicMock, patch
import yaml

from fastapi.testclient import TestClient
import httpx

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
    """Verify hash chain restoration from existing audit.jsonl file with corruption resilience."""
    fake_audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(daemon, "AUDIT_FILE", fake_audit)

    # When file does not exist
    assert daemon.load_last_audit_hash() == "0" * 64

    # Create fake audit file with chained records and trailing corrupted line
    rec1_hash = hashlib.sha256(b"record_1").hexdigest()
    rec2_hash = hashlib.sha256(b"record_2").hexdigest()

    with open(fake_audit, "w", encoding="utf-8") as f:
        f.write(json.dumps({"record_hash": rec1_hash}) + "\n")
        f.write(json.dumps({"record_hash": rec2_hash}) + "\n")
        f.write("corrupted trailing json line without closing brace\n")

    # Should skip the corrupted trailing line and restore rec2_hash
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
        lines = [line.strip() for line in f if line.strip()]

    # Last line should be the newly appended record
    last_rec = json.loads(lines[-1])
    assert last_rec["prev_hash"] == rec2_hash
    assert last_rec["record_hash"] == daemon.last_audit_hash


def test_anti_replay_protection():
    """Verify updates older than 120s are dropped and logged to audit trail."""
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
                with patch("scripts.chatops_daemon.append_audit_log") as mock_audit:
                    mock_send.return_value = 999

                    # Stale update should be dropped and logged
                    await daemon.process_telegram_update(stale_update)
                    mock_dispatch.assert_not_called()
                    mock_audit.assert_called_once()
                    assert mock_audit.call_args[1]["status"] == "STALE_DROPPED"

                    # Fresh update should be processed
                    mock_audit.reset_mock()
                    await daemon.process_telegram_update(fresh_update)
                    mock_dispatch.assert_called_once()

    asyncio.run(_test())


def test_failed_pin_attempt_audit_logging(tmp_path, monkeypatch):
    """Verify failed PIN attempts (< 3) are logged to audit trail."""
    fake_lockout = tmp_path / "chatops_lockout.json"
    monkeypatch.setattr(daemon, "LOCKOUT_FILE", fake_lockout)
    monkeypatch.setattr(daemon, "CHATOPS_EMERGENCY_PIN", "654321")

    async def _test():
        update = {
            "update_id": 2001,
            "message": {
                "message_id": 601,
                "chat": {"id": daemon.ADMIN_USER_ID},
                "from": {"id": daemon.ADMIN_USER_ID},
                "text": "/exec 111111 ls -la",
                "date": int(time.time()),
            },
        }

        with patch("scripts.chatops_daemon.delete_telegram_msg", new_callable=AsyncMock):
            with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send:
                with patch("scripts.chatops_daemon.append_audit_log") as mock_audit:
                    await daemon.process_telegram_update(update)

                    # Should report invalid PIN
                    assert mock_send.call_count == 1
                    assert "SAI MÃ PIN" in mock_send.call_args[0][1]

                    # Should record AUTH_FAILED audit log
                    mock_audit.assert_called_once()
                    assert mock_audit.call_args[0][4] == "AUTH_FAILED"

    asyncio.run(_test())


def test_persistent_http_client():
    """Verify get_http_client creates, reuses, and re-binds across loops."""
    # 1. Reuse in same loop
    c1 = daemon.get_http_client()
    c2 = daemon.get_http_client()
    assert c1 is c2
    assert not c1.is_closed

    # 2. Recreate cleanly across different event loops
    async def _check_in_loop():
        c_loop = daemon.get_http_client()
        assert not c_loop.is_closed
        return c_loop

    loop_client_1 = asyncio.run(_check_in_loop())
    loop_client_2 = asyncio.run(_check_in_loop())
    assert loop_client_1 is not loop_client_2
    assert not loop_client_2.is_closed


def test_action_cache_cleanup():
    """Verify purge_expired_action_cache directly removes expired nonces."""
    now = time.time()
    daemon.action_cache.clear()

    daemon.action_cache["expired_1"] = {"expires": now - 10, "cmd": "old1"}
    daemon.action_cache["expired_2"] = {"expires": now - 1, "cmd": "old2"}
    daemon.action_cache["valid_1"] = {"expires": now + 60, "cmd": "valid"}

    # Invoke real production purge function
    purged_count = daemon.purge_expired_action_cache()
    assert purged_count == 2
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


def test_probe_rag_state_offline():
    """Verify probe_rag_state handles offline rag-service without hanging on stats."""
    async def _test():
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("scripts.chatops_daemon.get_http_client", return_value=mock_client):
            result = await daemon.probe_rag_state()

        assert "Không thể kết nối" in result
        assert "Bỏ qua do `rag-service` không khả dụng" in result
        # Only 1 request attempted (short-circuited stats)
        assert mock_client.get.call_count == 1

    asyncio.run(_test())


def test_internal_notify_security(monkeypatch):
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

    # When CHATOPS_INTERNAL_SECRET is unconfigured / empty
    monkeypatch.setattr(daemon, "CHATOPS_INTERNAL_SECRET", "")
    res = client.post(
        "/api/v1/notify",
        json={"title": "Test", "body": "Alert"},
        headers={"X-ChatOps-Secret": ""},
    )
    assert res.status_code == 401
    monkeypatch.setattr(daemon, "CHATOPS_INTERNAL_SECRET", "dgx_test_secret_123")

    # With correct header
    with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = 8888
        res = client.post(
            "/api/v1/notify",
            json={"title": "Test Valid", "body": "Alert Content", "severity": "WARNING"},
            headers={"X-ChatOps-Secret": "dgx_test_secret_123"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "dispatched"


def test_execute_shell_job_timeout_reaping():
    """Verify execute_shell_job kills process group and reaps child process on timeout."""
    async def _test():
        with patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit:
            with patch("scripts.chatops_daemon.append_audit_log") as mock_audit:
                start = time.time()
                await daemon.execute_shell_job(
                    cmd="sleep 5",
                    job_id="test_timeout",
                    chat_id=daemon.ADMIN_USER_ID,
                    status_msg_id=1234,
                    title="Test Sleep",
                    timeout=1,
                )
                elapsed = time.time() - start
                # Timeout was 1s, should exit cleanly within ~2.5s without waiting for sleep 5
                assert elapsed < 3.5
                assert mock_edit.call_count >= 2
                last_call_text = mock_edit.call_args[0][2]
                assert "TIMEOUT" in last_call_text
                mock_audit.assert_called_once()
                assert mock_audit.call_args[0][4] == "TIMEOUT"

    asyncio.run(_test())


def test_dispatch_command_callback_handling():
    """Verify dispatch_command answers callback queries on invalid command or params."""
    async def _test():
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_answer:
            with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock):
                # 1. Invalid command
                await daemon.dispatch_command("nonexistent.command", {}, 123, 456, cq_id="cq_test_1")
                mock_answer.assert_called_with("cq_test_1", "❌ Lệnh không tồn tại!", show_alert=True)

                # 2. Invalid parameter violating regex
                mock_answer.reset_mock()
                await daemon.dispatch_command(
                    "system.container.restart",
                    {"service": "invalid_container;rm -rf /"},
                    123,
                    456,
                    cq_id="cq_test_2",
                )
                mock_answer.assert_called_with("cq_test_2", "❌ Lỗi tham số service!", show_alert=True)

    asyncio.run(_test())


def test_is_newer_version():
    """Verify version comparison logic."""
    assert not daemon.is_newer_version("0.11.4", "0.11.4")
    assert not daemon.is_newer_version("0.11.3", "0.11.4")
    assert daemon.is_newer_version("0.11.5", "0.11.4")
    assert daemon.is_newer_version("0.12.0", "0.11.4")
    assert daemon.is_newer_version("1.0.0", "0.11.4")
    assert not daemon.is_newer_version("unknown", "0.11.4")
    assert not daemon.is_newer_version("0.11.4", "unknown")


def test_check_openwebui_versions():
    """Verify check_openwebui_versions detects updates correctly."""
    async def _test():
        # Scenario 1: Already at latest version
        mock_client = AsyncMock()
        mock_res_local = MagicMock()
        mock_res_local.status_code = 200
        mock_res_local.json.return_value = {"version": "0.11.4"}

        mock_res_gh = MagicMock()
        mock_res_gh.status_code = 200
        mock_res_gh.json.return_value = {
            "tag_name": "v0.11.4",
            "published_at": "2026-09-21T00:00:00Z",
            "html_url": "https://github.com/open-webui/open-webui/releases/tag/v0.11.4",
        }

        mock_client.get = AsyncMock(side_effect=[mock_res_local, mock_res_gh])

        with patch("scripts.chatops_daemon.get_http_client", return_value=mock_client):
            info = await daemon.check_openwebui_versions()
            assert info["current_version"] == "0.11.4"
            assert info["latest_version"] == "0.11.4"
            assert not info["has_update"]

        # Scenario 2: Newer version available on GitHub
        mock_res_gh_newer = MagicMock()
        mock_res_gh_newer.status_code = 200
        mock_res_gh_newer.json.return_value = {
            "tag_name": "v0.11.5",
            "published_at": "2026-09-22T00:00:00Z",
            "html_url": "https://github.com/open-webui/open-webui/releases/tag/v0.11.5",
        }

        mock_client.get = AsyncMock(side_effect=[mock_res_local, mock_res_gh_newer])

        with patch("scripts.chatops_daemon.get_http_client", return_value=mock_client):
            info = await daemon.check_openwebui_versions()
            assert info["current_version"] == "0.11.4"
            assert info["latest_version"] == "0.11.5"
            assert info["has_update"]

    asyncio.run(_test())
