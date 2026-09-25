"""Comprehensive unit tests for DGX-ChatOps Universal Gateway."""

import asyncio
import hashlib
import json
import os
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
    assert boost_cmd.get("is_heavy_op") is True
    assert boost_cmd["timeout_seconds"] == 600
    assert boost_cmd["runner"] == "host_script"
    skill_regex = re.compile(boost_cmd["param_rules"]["skill"])
    assert skill_regex.match("bigbim-risk")
    assert skill_regex.match("ccba_legal_123")
    assert not skill_regex.match("skill;rm -rf /")
    assert not skill_regex.match("skill with spaces")

    # 4. Check ccba.autotuner.status command definition
    autotuner_cmd = cmds["ccba.autotuner.status"]
    assert autotuner_cmd["slash"] == "/autotuner"
    assert autotuner_cmd["risk_tier"] == "READ_ONLY"
    assert autotuner_cmd["service_lock"] is None
    assert autotuner_cmd["runner"] == "internal"


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
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch, \
             patch("scripts.chatops_daemon.is_kernel_runner_locked", return_value=False):
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
             patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit, \
             patch("scripts.chatops_daemon.is_kernel_runner_locked", return_value=False):
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
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch, \
             patch("scripts.chatops_daemon.is_kernel_runner_locked", return_value=False):
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


def test_is_kernel_runner_locked(tmp_path):
    """Verify is_kernel_runner_locked accurately reflects file lock status."""
    import fcntl

    lock_file = tmp_path / "test_kernel.lock"
    assert not daemon.is_kernel_runner_locked(str(lock_file))

    # Create file but don't lock
    lock_file.write_text("12345")
    assert not daemon.is_kernel_runner_locked(str(lock_file))

    # Lock file with fcntl
    with open(lock_file, "r") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            assert daemon.is_kernel_runner_locked(str(lock_file))
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    assert not daemon.is_kernel_runner_locked(str(lock_file))


def test_three_tier_defense_against_kernel_lock(monkeypatch):
    """Verify Three-Tier Defense blocks ccba.skill.boost when kernel lock is active."""
    monkeypatch.setattr(daemon, "is_kernel_runner_locked", lambda *args, **kwargs: True)

    async def _test():
        daemon.action_cache.clear()

        # --- Tier 1: act: callback ---
        entry = {
            "command": "ccba.skill.boost",
            "params": {"skill": "bigbim-risk"},
            "title": "🚀 /boost bigbim-risk",
            "timeout": 600,
            "expires": time.time() + 3600,
        }
        daemon.action_cache["tier1_nonce"] = entry

        cq_update = {
            "callback_query": {
                "id": "cq_tier1",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"message_id": 999, "chat": {"id": daemon.ADMIN_USER_ID}},
                "data": "act:tier1_nonce",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_answer, \
             patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch:
            await daemon.process_telegram_update(cq_update)
            # Tier 1 blocks: answers callback with alert, restores nonce, does not dispatch
            mock_answer.assert_called_once_with(
                "cq_tier1",
                "⚠️ Hệ thống đang bận chạy ca Nightly Auto-Tuner. Vui lòng thử lại sau!",
                show_alert=True,
            )
            assert "tier1_nonce" in daemon.action_cache
            mock_send.assert_not_called()
            mock_dispatch.assert_not_called()

        # --- Tier 2: /boost slash command ---
        msg_update = {
            "message": {
                "message_id": 888,
                "from": {"id": daemon.ADMIN_USER_ID},
                "chat": {"id": daemon.ADMIN_USER_ID},
                "text": "/boost bigbim-risk",
                "date": int(time.time()),
            }
        }
        with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch:
            await daemon.process_telegram_update(msg_update)
            # Tier 2 blocks: sends warning message immediately, does not dispatch
            mock_send.assert_called_once()
            assert "Nightly Auto-Tuner" in mock_send.call_args[0][1]
            mock_dispatch.assert_not_called()

        # --- Tier 3: dispatch_command direct call ---
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_answer, \
             patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit, \
             patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send:
            mock_edit.return_value = True
            dispatched = await daemon.dispatch_command(
                "ccba.skill.boost",
                {"skill": "bigbim-risk"},
                daemon.ADMIN_USER_ID,
                777,
                cq_id="cq_tier3",
            )
            assert dispatched is False
            mock_answer.assert_called_once_with(
                "cq_tier3",
                "⚠️ Hệ thống đang bận chạy ca Nightly Auto-Tuner. Vui lòng thử lại sau!",
                show_alert=True,
            )
            mock_edit.assert_called_once()
            assert "Nightly Auto-Tuner" in mock_edit.call_args[0][2]

    asyncio.run(_test())


def test_execute_shell_job_two_phase_termination_sigkill_escalation():
    """Verify execute_shell_job escalates to SIGKILL if SIGTERM times out."""
    import signal

    async def _test():
        with patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock), \
             patch("scripts.chatops_daemon.append_audit_log"), \
             patch("os.killpg") as mock_killpg:

            mock_proc = MagicMock()
            mock_proc.pid = 99999

            async def mock_wait():
                return 0

            mock_proc.wait = mock_wait

            with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_subproc, \
                 patch("os.getpgid", return_value=99999):
                mock_subproc.return_value = mock_proc

                call_count = 0

                async def custom_wait_for(fut, timeout):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        if asyncio.iscoroutine(fut):
                            fut.close()
                        raise asyncio.TimeoutError()
                    elif call_count == 2:
                        if asyncio.iscoroutine(fut):
                            fut.close()
                        raise asyncio.TimeoutError()
                    else:
                        if asyncio.iscoroutine(fut):
                            fut.close()
                        return 0

                with patch("asyncio.wait_for", side_effect=custom_wait_for):
                    await daemon.execute_shell_job(
                        cmd="stub",
                        job_id="test_escalate",
                        chat_id=daemon.ADMIN_USER_ID,
                        status_msg_id=123,
                        title="Test Escalate",
                        timeout=1,
                    )

            assert mock_killpg.call_count == 2
            mock_killpg.assert_any_call(99999, signal.SIGTERM)
            mock_killpg.assert_any_call(99999, signal.SIGKILL)

    asyncio.run(_test())


def test_main_dashboard_markup_11_buttons():
    """Verify main dashboard markup has 11 buttons across 6 rows."""
    markup = daemon.get_main_dashboard_markup()
    keyboard = markup["inline_keyboard"]
    assert len(keyboard) == 6
    for i, row in enumerate(keyboard):
        if i == 5:
            assert len(row) == 1
        else:
            assert len(row) == 2

    callbacks = [btn["callback_data"] for row in keyboard for btn in row]
    assert "menu:status" in callbacks
    assert "menu:memory" in callbacks
    assert "menu:gpu" in callbacks
    assert "menu:stats" in callbacks
    assert "menu:restart_list" in callbacks
    assert "menu:upgrade_owu" in callbacks
    assert "menu:autotuner" in callbacks
    assert "menu:boost_list" in callbacks
    assert "menu:rag_state" in callbacks
    assert "menu:deps_menu" in callbacks
    assert "menu:help" in callbacks


def test_boost_submenu_markup_deterministic_sorting(tmp_path):
    """Verify get_boost_skills_markup sorts plateau files by mtime desc and name asc, limited to 6."""
    now = time.time()
    files_data = [
        ("skill_c_plateau.md", now - 100),
        ("skill_a_plateau.md", now - 50),
        ("skill_b_plateau.md", now - 50),
        ("skill_d_plateau.md", now - 200),
        ("skill_e_plateau.md", now - 10),
        ("skill_f_plateau.md", now - 20),
        ("skill_g_plateau.md", now - 30),
        ("skill_h_plateau.md", now - 300),
    ]
    for fname, mtime in files_data:
        f = tmp_path / fname
        f.write_text("test")
        os.utime(f, (mtime, mtime))

    markup = daemon.get_boost_skills_markup(escalations_dir=str(tmp_path))
    keyboard = markup["inline_keyboard"]

    assert len(keyboard) == 7
    expected_order = ["skill_e", "skill_f", "skill_g", "skill_a", "skill_b", "skill_c"]
    for i, exp in enumerate(expected_order):
        row = keyboard[i]
        assert len(row) == 1
        assert row[0]["text"] == f"🚀 {exp}"
        assert row[0]["callback_data"] == f"bst:{exp}"

    assert keyboard[-1][0]["callback_data"] == "menu:main"


def test_query_litellm_postgres_stats():
    """Verify _query_litellm_postgres_stats parses UNION ALL output from psql correctly."""
    fake_psql_output = (
        b"SUMMARY|42|1050000|750000|300000\n"
        b"MODEL|openai/qwen-local-primary|1000000|35|\n"
        b"MODEL|gemini/gemini-flash|50000|7|\n"
    )

    async def _test():
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(fake_psql_output, b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            stats = await daemon._query_litellm_postgres_stats()

        assert stats is not None
        assert stats["total_requests"] == 42
        assert stats["total_tokens"] == 1050000
        assert stats["prompt_tokens"] == 750000
        assert stats["completion_tokens"] == 300000
        assert len(stats["top_models"]) == 2
        assert stats["top_models"][0]["model"] == "openai/qwen-local-primary"
        assert stats["top_models"][0]["tokens"] == 1000000
        assert stats["top_models"][0]["requests"] == 35

    asyncio.run(_test())


def test_probe_autotuner_status_live():
    """Verify probe_autotuner_status renders live running mode properly with backticks."""
    fake_json = json.dumps({
        "mode": "live",
        "is_running": True,
        "pid": 54321,
        "uptime": "02:15:30",
        "current_skill": "ccba-legal-intel",
        "completed": 4,
        "total": 12,
        "commits_count": 7,
        "matrix_warning": False,
    }).encode("utf-8")

    async def _test():
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(fake_json, b""))

        with patch("os.path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await daemon.probe_autotuner_status()

        assert "TIẾN ĐỘ CCBA NIGHTLY AUTO-TUNER" in result
        assert "🟢 Đang chạy (PID: `54321`)" in result
        assert "*Thời gian chạy (Uptime):* `02:15:30`" in result
        assert "*Kỹ năng đang xử lý:* `ccba-legal-intel` (`4/12` ~ `33.3%`)" in result
        assert "*Số commits đã tạo:* `7` commits" in result
        assert "🟢 Bình thường" in result

    asyncio.run(_test())


def test_probe_autotuner_status_idle():
    """Verify probe_autotuner_status renders post-run archive mode properly."""
    fake_json = json.dumps({
        "mode": "post_run",
        "is_running": False,
        "report_file": "nightly_tuner_report_20260925_0300.md",
        "timestamp": "20260925_0300",
        "git_branch": "auto-tune/nightly-20260925",
        "total_scanned": 20,
        "improved_count": 5,
        "commit_count": 6,
        "total_tokens": "1.5M",
        "improvements": [
            {
                "skill": "bigbim-risk",
                "init": "12.0",
                "final": "15.0",
                "delta": "+3.0",
            }
        ],
    }).encode("utf-8")

    async def _test():
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(fake_json, b""))

        with patch("os.path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await daemon.probe_autotuner_status()

        assert "CCBA NIGHTLY AUTO-TUNER (LƯU TRỮ)" in result
        assert "*Báo cáo gần nhất:* `nightly_tuner_report_20260925_0300.md`" in result
        assert "*Phiên thực thi:* `20260925_0300`" in result
        assert "*Nhánh Git:* `auto-tune/nightly-20260925`" in result
        assert "*Thống kê:* `5/20` kỹ năng cải thiện | `6` commits | `1.5M` tokens" in result
        assert "`bigbim-risk`: `12.0` ➔ `15.0` (`+3.0`)" in result

    asyncio.run(_test())


def test_probe_gateway_stats_dual():
    """Verify probe_gateway_stats displays Cloud, Local GPU and unified summary with offload ratio."""
    fake_local = {
        "total_requests": 200,
        "total_tokens": 800000,
        "prompt_tokens": 600000,
        "completion_tokens": 200000,
        "top_models": [
            {"model": "openai/qwen-local-primary", "tokens": 800000, "requests": 200}
        ],
    }

    async def _test():
        with patch("scripts.chatops_daemon._query_litellm_postgres_stats", new_callable=AsyncMock) as mock_local, \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_local.return_value = fake_local

            mock_client = AsyncMock()
            mock_resp_sum = MagicMock()
            mock_resp_sum.status_code = 200
            mock_resp_sum.json.return_value = {
                "total_requests": 100,
                "total_tokens": 200000,
                "total_input_tokens": 150000,
                "total_output_tokens": 50000,
            }

            mock_resp_model = MagicMock()
            mock_resp_model.status_code = 200
            mock_resp_model.json.return_value = [
                {"model": "gemini-2.5-pro", "total_tokens": 200000, "request_count": 100}
            ]

            mock_resp_acc = MagicMock()
            mock_resp_acc.status_code = 200
            mock_resp_acc.json.return_value = {"accounts": [{"disabled": False}, {"disabled": True}]}

            async def mock_get(url, **kwargs):
                if "/summary" in url:
                    return mock_resp_sum
                if "/by-model" in url:
                    return mock_resp_model
                if "/accounts" in url:
                    return mock_resp_acc
                return MagicMock(status_code=404)

            mock_client.get = mock_get
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await daemon.probe_gateway_stats()

            assert "CỔNG CLOUD (:8045)" in result
            assert "CỔNG GPU CỤC BỘ (:8090)" in result
            assert "TỔNG HỢP TOÀN HỆ THỐNG" in result
            assert "*Tổng Requests:* `300`" in result
            assert "*Tổng Tokens:* `1,000,000`" in result
            assert "*Tỷ Lệ Tải Cục Bộ (Offload):* `80.0%`" in result
            assert "`openai/qwen-local-primary`" in result

    asyncio.run(_test())


def test_autotuner_and_boost_routing():
    """Verify menu:autotuner, menu:boost_list, bst:<skill>, and /autotuner routing."""
    async def _test():
        # 1. /autotuner text command
        msg_update = {
            "message": {
                "message_id": 301,
                "from": {"id": daemon.ADMIN_USER_ID},
                "chat": {"id": daemon.ADMIN_USER_ID},
                "text": "/autotuner",
                "date": int(time.time()),
            }
        }
        with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch:
            mock_send.return_value = 2001
            await daemon.process_telegram_update(msg_update)
            mock_send.assert_called_once()
            mock_dispatch.assert_called_once_with("ccba.autotuner.status", {}, daemon.ADMIN_USER_ID, 2001)

        # 2. menu:autotuner callback
        cq_update = {
            "callback_query": {
                "id": "cq_at_1",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"message_id": 999, "chat": {"id": daemon.ADMIN_USER_ID}},
                "data": "menu:autotuner",
            }
        }
        with patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch:
            await daemon.process_telegram_update(cq_update)
            mock_dispatch.assert_called_once_with("ccba.autotuner.status", {}, daemon.ADMIN_USER_ID, 999, cq_id="cq_at_1")

        # 3. menu:boost_list callback
        cq_boost = {
            "callback_query": {
                "id": "cq_bst_list",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"message_id": 999, "chat": {"id": daemon.ADMIN_USER_ID}},
                "data": "menu:boost_list",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_answer, \
             patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit, \
             patch("scripts.chatops_daemon.is_kernel_runner_locked", return_value=False):
            await daemon.process_telegram_update(cq_boost)
            mock_answer.assert_called_once_with("cq_bst_list")
            mock_edit.assert_called_once()
            assert "CHỌN KỸ NĂNG CẦN CAN THIỆP /BOOST" in mock_edit.call_args[0][2]

        # 4. bst:<skill> callback triggers 2-step confirmation
        cq_bst_skill = {
            "callback_query": {
                "id": "cq_bst_skill_1",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"message_id": 999, "chat": {"id": daemon.ADMIN_USER_ID}},
                "data": "bst:bigbim-risk",
            }
        }
        daemon.action_cache.clear()
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_answer, \
             patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit, \
             patch("scripts.chatops_daemon.is_kernel_runner_locked", return_value=False):
            await daemon.process_telegram_update(cq_bst_skill)
            mock_answer.assert_called_once_with("cq_bst_skill_1")
            mock_edit.assert_called_once()
            assert "XÁC NHẬN CAN THIỆP SUY LUẬN SÂU" in mock_edit.call_args[0][2]
            assert "bigbim-risk" in mock_edit.call_args[0][2]
            assert len(daemon.action_cache) == 1
            cached = list(daemon.action_cache.values())[0]
            assert cached["command"] == "ccba.skill.boost"
            assert cached["params"] == {"skill": "bigbim-risk"}

    asyncio.run(_test())


def test_edge_cases_autotuner_boost_gateway(tmp_path):
    """Verify edge cases: empty escalations dir, autotuner timeout, exit 1, and postgres query failure."""
    # 1. Empty escalations directory
    empty_dir = tmp_path / "empty_escalations"
    empty_dir.mkdir()
    empty_markup = daemon.get_boost_skills_markup(escalations_dir=str(empty_dir))
    assert len(empty_markup["inline_keyboard"]) == 2
    assert "Không có kỹ năng plateau" in empty_markup["inline_keyboard"][0][0]["text"]
    assert empty_markup["inline_keyboard"][1][0]["callback_data"] == "menu:main"

    # Non-existent escalations directory
    non_existent = tmp_path / "does_not_exist"
    non_exist_markup = daemon.get_boost_skills_markup(escalations_dir=str(non_existent))
    assert len(non_exist_markup["inline_keyboard"]) == 2

    async def _test_async():
        # 2. Autotuner script timeout
        mock_proc_timeout = MagicMock()
        mock_proc_timeout.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc_timeout.kill = MagicMock()
        mock_proc_timeout.wait = AsyncMock()

        with patch("os.path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc_timeout):
            timeout_res = await daemon.probe_autotuner_status()
            assert "Lỗi Timeout" in timeout_res
            mock_proc_timeout.kill.assert_called_once()
            mock_proc_timeout.wait.assert_called_once()

        # 3. Autotuner exit 1 (no daemon and no archive report)
        mock_proc_exit1 = MagicMock()
        mock_proc_exit1.returncode = 1
        mock_proc_exit1.communicate = AsyncMock(
            return_value=("Không tìm thấy daemon đang chạy và cũng không có báo cáo lưu trữ.".encode("utf-8"), b"")
        )

        with patch("os.path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc_exit1):
            exit1_res = await daemon.probe_autotuner_status()
            assert "Đang nghỉ" in exit1_res
            assert "Không tìm thấy tiến trình Auto-Tuner đang chạy và chưa có báo cáo lưu trữ" in exit1_res

        # 4. Autotuner script does not exist
        with patch("os.path.exists", side_effect=lambda p: False if "check_nightly_status.py" in p else True):
            missing_script_res = await daemon.probe_autotuner_status()
            assert "Không tìm thấy script" in missing_script_res

        # 5. Postgres query failure / timeout
        mock_psql_timeout = MagicMock()
        mock_psql_timeout.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_psql_timeout.kill = MagicMock()
        mock_psql_timeout.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_psql_timeout):
            pg_res = await daemon._query_litellm_postgres_stats()
            assert pg_res is None
            mock_psql_timeout.kill.assert_called_once()
            mock_psql_timeout.wait.assert_called_once()

    asyncio.run(_test_async())


def test_probe_autotuner_status_null_fields_and_embedded_json():
    """Verify probe_autotuner_status handles null values without TypeError and parses embedded JSON."""
    async def _test():
        # 1. Null fields in live mode (must not crash with '>' not supported between NoneType and int)
        null_live_json = json.dumps({
            "mode": "live",
            "is_running": True,
            "pid": None,
            "uptime": None,
            "current_skill": None,
            "completed": None,
            "total": None,
            "commits_count": None,
            "matrix_warning": False,
        }).encode("utf-8")

        mock_proc_live = MagicMock()
        mock_proc_live.returncode = 0
        mock_proc_live.communicate = AsyncMock(return_value=(null_live_json, b""))

        with patch("os.path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc_live):
            live_res = await daemon.probe_autotuner_status()
            assert "TIẾN ĐỘ CCBA NIGHTLY AUTO-TUNER" in live_res
            assert "PID: `N/A`" in live_res
            assert "(Uptime):* `N/A`" in live_res
            assert "`N/A` (`0/0` ~ `0.0%`)" in live_res
            assert "`0` commits" in live_res
            assert "Lỗi không mong muốn" not in live_res

        # 2. Embedded JSON with preceding logging lines
        embedded_json = (
            b"[INFO] Scanning git branches...\n"
            b"[DEBUG] Found worktree at /tmp/tuner\n"
            + json.dumps({
                "mode": "post_run",
                "is_running": False,
                "report_file": "report_embedded.md",
                "timestamp": "20260925_000000",
                "git_branch": "auto-tune/test",
                "total_scanned": 15,
                "improved_count": 3,
                "commit_count": 3,
                "total_tokens": "500K",
                "improvements": [],
            }).encode("utf-8")
        )

        mock_proc_emb = MagicMock()
        mock_proc_emb.returncode = 0
        mock_proc_emb.communicate = AsyncMock(return_value=(embedded_json, b""))

        with patch("os.path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc_emb):
            emb_res = await daemon.probe_autotuner_status()
            assert "CCBA NIGHTLY AUTO-TUNER (LƯU TRỮ)" in emb_res
            assert "`report_embedded.md`" in emb_res
            assert "`3/15` kỹ năng cải thiện" in emb_res

    asyncio.run(_test())


def test_probe_gateway_stats_rule5_sorting():
    """Verify probe_gateway_stats sorts cloud models deterministically by tokens desc and model asc."""
    async def _test():
        models_data = [
            {"model": "model-z", "total_tokens": 1000, "request_count": 5},
            {"model": "model-a", "total_tokens": 1000, "request_count": 5},
            {"model": "model-top", "total_tokens": 5000, "request_count": 10},
            {"model": "model-b", "total_tokens": 500, "request_count": 2},
        ]

        with patch("scripts.chatops_daemon._query_litellm_postgres_stats", new_callable=AsyncMock, return_value=None), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_resp_sum = MagicMock(status_code=200)
            mock_resp_sum.json.return_value = {"total_requests": 22, "total_tokens": 7500}
            mock_resp_model = MagicMock(status_code=200)
            mock_resp_model.json.return_value = models_data
            mock_resp_acc = MagicMock(status_code=200)
            mock_resp_acc.json.return_value = {"accounts": []}

            async def mock_get(url, **kwargs):
                if "/summary" in url:
                    return mock_resp_sum
                if "/by-model" in url:
                    return mock_resp_model
                if "/accounts" in url:
                    return mock_resp_acc
                return MagicMock(status_code=404)

            mock_client.get = mock_get
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            res = await daemon.probe_gateway_stats()

            # model-top (5000) should appear first, followed by model-a (1000, before model-z)
            idx_top = res.find("`model-top`")
            idx_a = res.find("`model-a`")
            idx_z = res.find("`model-z`")
            assert idx_top < idx_a < idx_z

    asyncio.run(_test())


def test_bst_callback_validation_and_slash_autocomplete():
    """Verify bst:<skill> rejects invalid skill names and /autotuner@bot routes properly."""
    async def _test():
        # 1. Invalid skill name in callback query
        cq_invalid_skill = {
            "callback_query": {
                "id": "cq_inv_1",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"message_id": 999, "chat": {"id": daemon.ADMIN_USER_ID}},
                "data": "bst:bad;rm -rf /",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_answer:
            await daemon.process_telegram_update(cq_invalid_skill)
            mock_answer.assert_called_once_with("cq_inv_1", "❌ Tên kỹ năng không hợp lệ!", show_alert=True)

        # 2. /autotuner@bot_username autocomplete
        msg_at = {
            "message": {
                "message_id": 501,
                "from": {"id": daemon.ADMIN_USER_ID},
                "chat": {"id": daemon.ADMIN_USER_ID},
                "text": "/autotuner@dgx_chatops_bot",
                "date": int(time.time()),
            }
        }
        with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_dispatch:
            mock_send.return_value = 5001
            await daemon.process_telegram_update(msg_at)
            mock_send.assert_called_once()
            mock_dispatch.assert_called_once_with("ccba.autotuner.status", {}, daemon.ADMIN_USER_ID, 5001)

        # 3. /help@bot_username autocomplete
        msg_help = {
            "message": {
                "message_id": 502,
                "from": {"id": daemon.ADMIN_USER_ID},
                "chat": {"id": daemon.ADMIN_USER_ID},
                "text": "/help@dgx_chatops_bot",
                "date": int(time.time()),
            }
        }
        with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send:
            await daemon.process_telegram_update(msg_help)
            mock_send.assert_called_once()
            assert "HƯỚNG DẪN SỬ DỤNG DGX-CHATOPS" in mock_send.call_args[0][1]

    asyncio.run(_test())


def test_cancelled_error_subprocess_reaping():
    """Verify asyncio.CancelledError properly kills child process and re-raises in daemon probes."""
    async def _test():
        # 1. probe_autotuner_status
        mock_proc_tuner = MagicMock()
        mock_proc_tuner.communicate = AsyncMock(side_effect=asyncio.CancelledError())
        mock_proc_tuner.kill = MagicMock()
        mock_proc_tuner.wait = AsyncMock()

        with patch("os.path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc_tuner):
            try:
                await daemon.probe_autotuner_status()
                assert False, "Should have re-raised CancelledError"
            except asyncio.CancelledError:
                pass
            mock_proc_tuner.kill.assert_called_once()
            mock_proc_tuner.wait.assert_called_once()

        # 2. _query_litellm_postgres_stats
        mock_proc_pg = MagicMock()
        mock_proc_pg.communicate = AsyncMock(side_effect=asyncio.CancelledError())
        mock_proc_pg.kill = MagicMock()
        mock_proc_pg.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc_pg):
            try:
                await daemon._query_litellm_postgres_stats()
                assert False, "Should have re-raised CancelledError"
            except asyncio.CancelledError:
                pass
            mock_proc_pg.kill.assert_called_once()
            mock_proc_pg.wait.assert_called_once()

    asyncio.run(_test())


def test_deps_submenu_markup():
    """Verify get_deps_menu_markup contains required action buttons and back button."""
    markup = daemon.get_deps_menu_markup()
    keyboard = markup["inline_keyboard"]
    callbacks = [btn["callback_data"] for row in keyboard for btn in row]
    assert "menu:deps_check" in callbacks
    assert "menu:deps_upg_patch" in callbacks
    assert "menu:deps_upg_minor" in callbacks
    assert "menu:main" in callbacks


def test_callback_deps_menu_and_actions():
    """Verify callback queries for deps menu, check, and upgrade confirmations."""
    async def _test():
        # 1. menu:deps_menu
        cq_menu = {
            "callback_query": {
                "id": "cq_deps_menu",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"chat": {"id": daemon.ADMIN_USER_ID}, "message_id": 8801},
                "data": "menu:deps_menu",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_ans, \
             patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit:
            mock_edit.return_value = True
            await daemon.process_telegram_update(cq_menu)
            mock_ans.assert_called_once_with("cq_deps_menu")
            mock_edit.assert_called_once()
            assert "QUẢN LÝ PHỤ THUỘC" in mock_edit.call_args[0][2]

        # 2. menu:deps_check
        cq_check = {
            "callback_query": {
                "id": "cq_deps_chk",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"chat": {"id": daemon.ADMIN_USER_ID}, "message_id": 8802},
                "data": "menu:deps_check",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_ans, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_disp:
            await daemon.process_telegram_update(cq_check)
            mock_ans.assert_called_once_with("cq_deps_chk", "🔍 Đang rà soát phụ thuộc...")
            mock_disp.assert_called_once_with("system.deps.check", {}, daemon.ADMIN_USER_ID, 8802, title="Rà soát phụ thuộc & bảo mật", cq_id="cq_deps_chk")

        # 3. menu:deps_upg_patch
        cq_patch = {
            "callback_query": {
                "id": "cq_deps_patch",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"chat": {"id": daemon.ADMIN_USER_ID}, "message_id": 8803},
                "data": "menu:deps_upg_patch",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_ans, \
             patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit:
            mock_edit.return_value = True
            await daemon.process_telegram_update(cq_patch)
            mock_ans.assert_called_once_with("cq_deps_patch")
            mock_edit.assert_called_once()
            assert "TIER 1 (PATCH)" in mock_edit.call_args[0][2]

        # 4. menu:deps_upg_minor
        cq_minor = {
            "callback_query": {
                "id": "cq_deps_minor",
                "from": {"id": daemon.ADMIN_USER_ID},
                "message": {"chat": {"id": daemon.ADMIN_USER_ID}, "message_id": 8804},
                "data": "menu:deps_upg_minor",
            }
        }
        with patch("scripts.chatops_daemon.answer_callback", new_callable=AsyncMock) as mock_ans, \
             patch("scripts.chatops_daemon.edit_telegram_msg", new_callable=AsyncMock) as mock_edit:
            mock_edit.return_value = True
            await daemon.process_telegram_update(cq_minor)
            mock_ans.assert_called_once_with("cq_deps_minor")
            mock_edit.assert_called_once()
            assert "TIER 2 (MINOR)" in mock_edit.call_args[0][2]

    asyncio.run(_test())


def test_message_deps_and_upgrade_deps():
    """Verify /deps and /upgrade_deps text messages trigger command dispatch."""
    async def _test():
        # 1. /deps
        msg_deps = {
            "message": {
                "message_id": 9901,
                "from": {"id": daemon.ADMIN_USER_ID},
                "chat": {"id": daemon.ADMIN_USER_ID},
                "text": "/deps",
                "date": int(time.time()),
            }
        }
        with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_disp:
            mock_send.return_value = 9902
            await daemon.process_telegram_update(msg_deps)
            mock_send.assert_called_once()
            mock_disp.assert_called_once_with("system.deps.check", {}, daemon.ADMIN_USER_ID, 9902, title="Rà soát phụ thuộc & bảo mật")

        # 2. /upgrade_deps minor
        msg_upg = {
            "message": {
                "message_id": 9903,
                "from": {"id": daemon.ADMIN_USER_ID},
                "chat": {"id": daemon.ADMIN_USER_ID},
                "text": "/upgrade_deps minor",
                "date": int(time.time()),
            }
        }
        with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send, \
             patch("scripts.chatops_daemon.dispatch_command", new_callable=AsyncMock) as mock_disp:
            mock_send.return_value = 9904
            await daemon.process_telegram_update(msg_upg)
            mock_send.assert_called_once()
            mock_disp.assert_called_once_with("system.deps.upgrade", {"tier": "minor"}, daemon.ADMIN_USER_ID, 9904, title="Nâng cấp phụ thuộc (minor)")

        # 3. /upgrade_deps invalid
        msg_invalid = {
            "message": {
                "message_id": 9905,
                "from": {"id": daemon.ADMIN_USER_ID},
                "chat": {"id": daemon.ADMIN_USER_ID},
                "text": "/upgrade_deps major",
                "date": int(time.time()),
            }
        }
        with patch("scripts.chatops_daemon.send_telegram_msg", new_callable=AsyncMock) as mock_send:
            await daemon.process_telegram_update(msg_invalid)
            mock_send.assert_called_once()
            assert "Cú pháp: `/upgrade_deps [patch|minor]`" in mock_send.call_args[0][1]

    asyncio.run(_test())


