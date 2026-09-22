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

    # 3. Check ccba.skill.boost command definition
    boost_cmd = cmds["ccba.skill.boost"]
    assert boost_cmd["slash"] == "/boost"
    assert boost_cmd["service_lock"] == "ccba-tuner"
    assert boost_cmd["timeout_seconds"] == 600
    assert boost_cmd["runner"] == "host_script"
    skill_regex = re.compile(boost_cmd["param_rules"]["skill"])
    assert skill_regex.match("bigbim-risk")
    assert skill_regex.match("ccba_legal_123")
    assert not skill_regex.match("skill;rm -rf /")
    assert not skill_regex.match("skill with spaces")


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
    with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
         patch("scripts.chatops_daemon.append_audit_log") as mock_audit:
        mock_send.return_value = 8888
        res = client.post(
            "/api/v1/notify",
            json={"title": "Test Valid", "body": "Alert Content", "severity": "WARNING"},
            headers={"X-ChatOps-Secret": "dgx_test_secret_123"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "dispatched"
        mock_audit.assert_called_once()


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


def test_dynamic_action_callback_handling():
    """Verify dynamic action callback handles expired actions and dispatches valid actions cleanly."""
    async def _test():
        # Scenario 1: Expired or missing nonce -> only answer_callback with alert, NO edit/send
        daemon.action_cache.clear()
        cq_expired = {
            "callback_query": {
                "id": "cq_exp_1",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"message_id": 999, "chat": {"id": daemon.ADMIN_USER_ID}},
                "data": "act:nonexistent_nonce",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_answer, \
             patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit, \
             patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch:
            await daemon.process_telegram_update(cq_expired)
            mock_answer.assert_called_once_with("cq_exp_1", "⚠️ Thao tác đã hết hạn hoặc đã được thực thi!", show_alert=True)
            mock_edit.assert_not_called()
            mock_send.assert_not_called()
            mock_dispatch.assert_not_called()

        # Scenario 2: Valid nonce -> answer_callback, send separate status message, dispatch with status_msg_id
        daemon.action_cache["valid_nonce_1"] = {
            "command": "ccba.skill.boost",
            "params": {"skill": "bigbim-risk"},
            "title": "🚀 /boost bigbim-risk",
            "timeout": 600,
            "expires": time.time() + 3600,
        }
        cq_valid = {
            "callback_query": {
                "id": "cq_valid_1",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"message_id": 999, "chat": {"id": daemon.ADMIN_USER_ID}},
                "data": "act:valid_nonce_1",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_answer, \
             patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch:
            mock_send.return_value = 1001  # status_msg_id
            await daemon.process_telegram_update(cq_valid)
            mock_answer.assert_called_once_with("cq_valid_1", "🚀 Khởi chạy 🚀 /boost bigbim-risk...")
            mock_send.assert_called_once()
            assert "ĐANG CHẠY" in mock_send.call_args[0][1]
            mock_dispatch.assert_called_once_with(
                "ccba.skill.boost",
                {"skill": "bigbim-risk"},
                daemon.ADMIN_USER_ID,
                1001,
                title="🚀 /boost bigbim-risk",
                cq_id="cq_valid_1",
                timeout=600,
            )

    asyncio.run(_test())


def test_dynamic_action_callback_restores_nonce_on_busy_lock():
    """Verify dynamic action callback preserves nonce in action_cache if service lock is busy."""
    async def _test():
        daemon.action_cache.clear()
        svc_lock = daemon.get_service_lock("ccba-tuner")
        await svc_lock.acquire()  # Simulate ongoing runner holding lock

        entry = {
            "command": "ccba.skill.boost",
            "params": {"skill": "stagnant-skill"},
            "title": "🚀 /boost stagnant-skill",
            "timeout": 600,
            "expires": time.time() + 3600,
        }
        daemon.action_cache["busy_nonce_1"] = entry

        cq_busy = {
            "callback_query": {
                "id": "cq_busy_1",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"message_id": 999, "chat": {"id": daemon.ADMIN_USER_ID}},
                "data": "act:busy_nonce_1",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_answer, \
             patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit:
            mock_send.return_value = 1002

            await daemon.process_telegram_update(cq_busy)

            # Nonce must be preserved in cache because command was rejected due to lock
            assert "busy_nonce_1" in daemon.action_cache
            assert daemon.action_cache["busy_nonce_1"] == entry

            # Progress message must be edited with busy warning
            mock_edit.assert_called_once()
            assert "đang có tác vụ khác thực thi" in mock_edit.call_args[0][2]

        svc_lock.release()

    asyncio.run(_test())


def test_boost_text_command_handling():
    """Verify /boost <skill> text command parses arguments and dispatches command."""
    async def _test():
        # Scenario 1: Missing argument
        msg_missing = {
            "message": {
                "message_id": 101,
                "from": {"id": daemon.ADMIN_USER_ID},
                "chat": {"id": daemon.ADMIN_USER_ID},
                "text": "/boost",
                "date": int(time.time()),
            }
        }
        with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send:
            await daemon.process_telegram_update(msg_missing)
            mock_send.assert_called_once_with(daemon.ADMIN_USER_ID, "Cú pháp: `/boost <skill_name>` (Ví dụ: `/boost bigbim-risk`)")

        # Scenario 2: Valid argument dispatches ccba.skill.boost
        msg_valid = {
            "message": {
                "message_id": 102,
                "from": {"id": daemon.ADMIN_USER_ID},
                "chat": {"id": daemon.ADMIN_USER_ID},
                "text": "/boost bigbim-risk",
                "date": int(time.time()),
            }
        }
        with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch:
            mock_send.return_value = 1003
            mock_dispatch.return_value = True

            await daemon.process_telegram_update(msg_valid)
            mock_send.assert_called_once()
            assert "bigbim-risk" in mock_send.call_args[0][1]
            mock_dispatch.assert_called_once_with(
                "ccba.skill.boost",
                {"skill": "bigbim-risk"},
                daemon.ADMIN_USER_ID,
                1003,
                title="🚀 /boost bigbim-risk",
            )

    asyncio.run(_test())


def test_notify_action_timeout_handling(monkeypatch):
    """Verify /api/v1/notify preserves custom timeout or sets None to fallback to command timeout."""
    client = TestClient(daemon.app, client=("127.0.0.1", 50000))
    monkeypatch.setattr(daemon, "CHATOPS_INTERNAL_SECRET", "test_secret_timeout")
    daemon.action_cache.clear()

    with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
         patch("scripts.chatops_daemon.append_audit_log"):
        mock_send.return_value = 8888

        # 1. Action with custom timeout
        res = client.post(
            "/api/v1/notify",
            json={
                "title": "Boost Request",
                "body": "Stagnant skill detected",
                "actions": [
                    {
                        "action_id": "boost_bigbim",
                        "label": "🚀 /boost bigbim-risk",
                        "command": "ccba.skill.boost",
                        "params": {"skill": "bigbim-risk"},
                        "timeout": 600,
                    }
                ],
            },
            headers={"X-ChatOps-Secret": "test_secret_timeout"},
        )
        assert res.status_code == 200
        assert len(daemon.action_cache) == 1
        cached_entry = list(daemon.action_cache.values())[0]
        assert cached_entry["timeout"] == 600

        # 2. Action without timeout falls back to None (so dispatch_command uses command default)
        daemon.action_cache.clear()
        res2 = client.post(
            "/api/v1/notify",
            json={
                "title": "Default Timeout Request",
                "body": "No explicit timeout specified",
                "actions": [
                    {
                        "action_id": "generic_act",
                        "label": "Do Work",
                        "command": "ccba.skill.boost",
                        "params": {"skill": "bigbim-risk"},
                    }
                ],
            },
            headers={"X-ChatOps-Secret": "test_secret_timeout"},
        )
        assert res2.status_code == 200
        cached_entry2 = list(daemon.action_cache.values())[0]
        assert cached_entry2["timeout"] is None


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


def test_internal_notify_telegram_failure_returns_502(monkeypatch):
    """Verify /api/v1/notify returns 502 and records FAILED in audit when Telegram dispatch fails."""
    client = TestClient(daemon.app, client=("127.0.0.1", 50000))
    monkeypatch.setattr(daemon, "CHATOPS_INTERNAL_SECRET", "dgx_test_secret_123")

    with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
         patch("scripts.chatops_daemon.append_audit_log") as mock_audit:
        mock_send.return_value = None  # Telegram delivery failed
        res = client.post(
            "/api/v1/notify",
            json={"title": "Test Delivery Failure", "body": "Alert Content"},
            headers={"X-ChatOps-Secret": "dgx_test_secret_123"},
        )
        assert res.status_code == 502
        assert "Failed to dispatch message to Telegram" in res.json()["detail"]
        mock_audit.assert_called_once()
        assert mock_audit.call_args[0][4] == "FAILED"


def test_watchdog_notify_chatops_success(monkeypatch):
    """Verify watchdog notify_chatops dispatches with proper secret header and payload."""
    import scripts.smart_watchdog as sw

    monkeypatch.setattr(sw, "CHATOPS_GATEWAY_URL", "http://127.0.0.1:8095")
    monkeypatch.setattr(sw, "CHATOPS_INTERNAL_SECRET", "test_watchdog_secret")

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        actions = [{"label": "Restart", "command": "system.container.restart"}]
        result = sw.notify_chatops("Test Title", "Test Body", actions=actions, severity="WARNING")

        assert result is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://127.0.0.1:8095/api/v1/notify"
        assert kwargs["headers"]["X-ChatOps-Secret"] == "test_watchdog_secret"
        assert kwargs["json"]["title"] == "Test Title"
        assert kwargs["json"]["severity"] == "WARNING"
        assert len(kwargs["json"]["actions"]) == 1


def test_watchdog_notify_chatops_fallback_on_401(monkeypatch):
    """Verify watchdog falls back to send_telegram_raw when gateway returns 401."""
    import scripts.smart_watchdog as sw

    monkeypatch.setattr(sw, "CHATOPS_GATEWAY_URL", "http://127.0.0.1:8095")
    monkeypatch.setattr(sw, "CHATOPS_INTERNAL_SECRET", "wrong_secret")

    with patch("requests.post") as mock_post, \
         patch("scripts.smart_watchdog.send_telegram_raw") as mock_raw:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_post.return_value = mock_resp
        mock_raw.return_value = True

        result = sw.notify_chatops("Test Alert", "Some body")

        assert result is True
        mock_post.assert_called_once()
        mock_raw.assert_called_once()
        assert "Test Alert" in mock_raw.call_args[0][0]


def test_watchdog_notify_chatops_fallback_on_network_error(monkeypatch):
    """Verify watchdog falls back to send_telegram_raw when gateway is unreachable."""
    import scripts.smart_watchdog as sw

    monkeypatch.setattr(sw, "CHATOPS_GATEWAY_URL", "http://127.0.0.1:8095")
    monkeypatch.setattr(sw, "CHATOPS_INTERNAL_SECRET", "valid_secret")

    with patch("requests.post", side_effect=Exception("Connection refused")) as mock_post, \
         patch("scripts.smart_watchdog.send_telegram_raw") as mock_raw:
        mock_raw.return_value = True

        result = sw.notify_chatops("Net Error", "Gateway Down")

        assert result is True
        mock_post.assert_called_once()
        mock_raw.assert_called_once()
        assert "Net Error" in mock_raw.call_args[0][0]


def test_watchdog_notify_chatops_unconfigured_secret(monkeypatch):
    """Verify watchdog skips HTTP post and directly calls send_telegram_raw if secret is empty."""
    import scripts.smart_watchdog as sw

    monkeypatch.setattr(sw, "CHATOPS_INTERNAL_SECRET", "")

    with patch("requests.post") as mock_post, \
         patch("scripts.smart_watchdog.send_telegram_raw") as mock_raw:
        mock_raw.return_value = True

        result = sw.notify_chatops("No Secret", "Direct telegram only")

        assert result is True
        mock_post.assert_not_called()
        mock_raw.assert_called_once()


def test_watchdog_core_services_monitoring():
    """Verify smart_watchdog checks all 7 other core containers."""
    import inspect
    import scripts.smart_watchdog as sw

    src = inspect.getsource(sw.check_docker_containers)
    expected_containers = [
        "open-webui",
        "qwen36b",
        "ai-gateway",
        "cloudflared-tunnel",
        "rag-service",
        "milvus-standalone",
        "neo4j-graph",
    ]
    for c in expected_containers:
        assert f'"{c}"' in src, f"Expected container {c} to be in check_docker_containers core_services"

