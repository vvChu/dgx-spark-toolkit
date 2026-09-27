"""Unit tests for Smart Watchdog Quorum Guard and Antigravity Pool monitoring."""

import time
from unittest.mock import MagicMock, patch

import scripts.smart_watchdog as sw


def test_extract_validation_url():
    """Verify validation url extraction from various metadata fields."""
    # 1. Direct validation_url
    acc1 = {"validation_url": "https://accounts.google.com/signin/continue?id=123"}
    assert sw.extract_validation_url(acc1) == "https://accounts.google.com/signin/continue?id=123"

    # 2. Embedded in raw reason string with unicode escapes
    acc2 = {
        "disabled_reason": "Failed: https://accounts.google.com/signin/continue?id=abc\\u0026hl=vi required"
    }
    assert sw.extract_validation_url(acc2) == "https://accounts.google.com/signin/continue?id=abc&hl=vi"

    # 3. No url present
    acc3 = {"disabled_reason": "Warmup 403 Forbidden"}
    assert sw.extract_validation_url(acc3) is None


def test_quorum_guard_mass_failure_triggers_critical_alert(monkeypatch):
    """Verify Quorum Guard dispatches CRITICAL alert and suppresses individual isolation on mass failure."""
    monkeypatch.setattr(sw, "GATEWAY_PROXY_KEY", "test_proxy_key")
    sw.known_blocked_accounts.clear()
    if hasattr(sw.check_quota_pool, "last_quorum_alert"):
        delattr(sw.check_quota_pool, "last_quorum_alert")

    # 5 out of 7 accounts failing (failed_ratio = 5/7 = 0.714 >= 0.5, active = 2 <= 2)
    fake_accounts = [
        {"id": "acc_1", "email": "a1@gmail.com", "disabled": False},
        {"id": "acc_2", "email": "a2@gmail.com", "disabled": False},
        {"id": "acc_3", "email": "a3@gmail.com", "disabled": True, "disabled_reason": "Verify your account"},
        {"id": "acc_4", "email": "a4@gmail.com", "proxy_disabled": True, "proxy_disabled_reason": "403 Forbidden"},
        {"id": "acc_5", "email": "a5@gmail.com", "validation_blocked": True},
        {"id": "acc_6", "email": "a6@gmail.com", "quota": {"is_forbidden": True}},
        {"id": "acc_7", "email": "a7@gmail.com", "disabled": True},
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"accounts": fake_accounts}

    with patch("requests.get", return_value=mock_resp), \
         patch("scripts.smart_watchdog.notify_chatops") as mock_notify:
        mock_notify.return_value = True

        sw.check_quota_pool()

        # Must trigger CRITICAL network/quorum alert
        mock_notify.assert_called_once()
        title, body = mock_notify.call_args[0][0], mock_notify.call_args[0][1]
        severity = mock_notify.call_args[1].get("severity")

        assert "QUORUM GUARD" in title
        assert severity == "CRITICAL"
        assert "5/7" in body
        assert "71.4%" in body
        # Individual account isolation alerts must NOT be added to known_blocked_accounts
        assert len(sw.known_blocked_accounts) == 0


def test_quorum_guard_healthy_individual_failure_triggers_action_payload(monkeypatch):
    """Verify healthy quorum triggers individual alert with re-enable interactive action."""
    monkeypatch.setattr(sw, "GATEWAY_PROXY_KEY", "test_proxy_key")
    sw.known_blocked_accounts.clear()
    if hasattr(sw.check_quota_pool, "last_quorum_alert"):
        delattr(sw.check_quota_pool, "last_quorum_alert")

    # 1 out of 5 accounts failing (failed_ratio = 1/5 = 0.2 < 0.5, active = 4 > 2)
    fake_accounts = [
        {"id": "acc_1", "email": "active1@gmail.com", "disabled": False},
        {"id": "acc_2", "email": "active2@gmail.com", "disabled": False},
        {"id": "acc_3", "email": "active3@gmail.com", "disabled": False},
        {"id": "acc_4", "email": "active4@gmail.com", "disabled": False},
        {
            "id": "acc_5",
            "email": "blocked1@gmail.com",
            "disabled": True,
            "validation_url": "https://accounts.google.com/signin/continue?id=test",
            "disabled_reason": "Verify your account",
        },
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"accounts": fake_accounts}

    with patch("requests.get", return_value=mock_resp), \
         patch("scripts.smart_watchdog.notify_chatops") as mock_notify:
        mock_notify.return_value = True

        sw.check_quota_pool()

        mock_notify.assert_called_once()
        title, body = mock_notify.call_args[0][0], mock_notify.call_args[0][1]
        actions = mock_notify.call_args[1].get("actions", [])
        severity = mock_notify.call_args[1].get("severity")

        assert "CẦN XÁC MINH" in title
        assert severity == "WARNING"
        assert "blocked1@gmail.com" in body
        assert len(actions) == 1
        assert actions[0]["action_id"] == "antigravity_reenable_acc_5"
        assert actions[0]["command"] == "antigravity.account.reenable"
        assert actions[0]["params"] == {"account_id": "acc_5"}
        assert actions[0]["callback_data"] == "act:antigravity_reenable:acc_5"
        assert "blocked1@gmail.com" in sw.known_blocked_accounts


def test_quota_pool_recovery_alert(monkeypatch):
    """Verify recovered account sends INFO alert and clears from known_blocked_accounts."""
    monkeypatch.setattr(sw, "GATEWAY_PROXY_KEY", "test_proxy_key")
    sw.known_blocked_accounts.clear()
    sw.known_blocked_accounts["recovered@gmail.com"] = time.time() - 100

    # All accounts active
    fake_accounts = [
        {"id": "acc_1", "email": "recovered@gmail.com", "disabled": False},
        {"id": "acc_2", "email": "other@gmail.com", "disabled": False},
        {"id": "acc_3", "email": "other3@gmail.com", "disabled": False},
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"accounts": fake_accounts}

    with patch("requests.get", return_value=mock_resp), \
         patch("scripts.smart_watchdog.notify_chatops") as mock_notify:
        mock_notify.return_value = True

        sw.check_quota_pool()

        mock_notify.assert_called_once()
        title, body = mock_notify.call_args[0][0], mock_notify.call_args[0][1]
        severity = mock_notify.call_args[1].get("severity")

        assert "ĐÃ PHỤC HỒI" in title
        assert severity == "INFO"
        assert "recovered@gmail.com" in body
        assert "recovered@gmail.com" not in sw.known_blocked_accounts
