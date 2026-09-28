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


# ==============================================================================
# PHASE 2: AUTO-HEALING LOOP TESTS & SAFETY INVARIANTS
# ==============================================================================

def test_is_eligible_for_auto_heal():
    """Verify strict Zero-Upstream-Challenge invariants for auto-healing eligibility."""
    # 1. Challenge with validation_url must be rejected
    acc_val = {
        "id": "1",
        "email": "val@gmail.com",
        "proxy_disabled": True,
        "validation_url": "https://accounts.google.com/signin/continue",
    }
    assert sw.is_eligible_for_auto_heal(acc_val) is False

    # 2. validation_blocked must be rejected
    acc_vb = {"id": "2", "email": "vb@gmail.com", "validation_blocked": True, "proxy_disabled": True}
    assert sw.is_eligible_for_auto_heal(acc_vb) is False

    # 3. Disabled manually by user or manual lock must be rejected
    acc_manual = {
        "id": "3",
        "email": "manual@gmail.com",
        "proxy_disabled": True,
        "disabled_reason": "Disabled manually by user",
    }
    assert sw.is_eligible_for_auto_heal(acc_manual) is False

    # 4. invalid_grant or unauthorized_client must be rejected
    acc_grant = {
        "id": "4",
        "email": "grant@gmail.com",
        "proxy_disabled": True,
        "disabled_reason": "invalid_grant: token revoked",
    }
    assert sw.is_eligible_for_auto_heal(acc_grant) is False

    # 5. Pure temporary rate-limit / quota lock without challenge IS ELIGIBLE
    acc_eligible = {
        "id": "5",
        "email": "quota@gmail.com",
        "proxy_disabled": True,
        "quota": {"is_forbidden": True, "forbidden_reason": "Resource has been exhausted (rate limit)"},
    }
    assert sw.is_eligible_for_auto_heal(acc_eligible) is True


def test_auto_heal_skips_young_lockout_age():
    """Verify auto-healing skips accounts locked out for less than 60 minutes."""
    sw._healer_memory_first_seen.clear()
    sw._healer_memory_attempts.clear()
    sw._healer_memory_last_attempt.clear()

    now = time.time()
    # Account blocked only 10 minutes ago (600s < 3600s)
    sw._healer_memory_first_seen["acc_young"] = now - 600

    account = {
        "id": "acc_young",
        "email": "young@gmail.com",
        "proxy_disabled": True,
        "quota": {"is_forbidden": True},
    }

    with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
        res = sw.auto_heal_single_candidate([account], "http://127.0.0.1:8045", {})
        assert res is None
        mock_get.assert_not_called()
        mock_post.assert_not_called()


def test_auto_heal_skips_when_max_attempts_reached():
    """Verify auto-healing caps attempts at 3 per 24 hours."""
    sw._healer_memory_first_seen.clear()
    sw._healer_memory_attempts.clear()
    sw._healer_memory_last_attempt.clear()

    now = time.time()
    # Account blocked 4000s ago (> 3600s), but already attempted 3 times
    sw._healer_memory_first_seen["acc_maxed"] = now - 4000
    sw._healer_memory_attempts["acc_maxed"] = 3
    sw._healer_memory_last_attempt["acc_maxed"] = now - 3700

    account = {
        "id": "acc_maxed",
        "email": "maxed@gmail.com",
        "proxy_disabled": True,
        "quota": {"is_forbidden": True},
    }

    with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
        res = sw.auto_heal_single_candidate([account], "http://127.0.0.1:8045", {})
        assert res is None
        mock_get.assert_not_called()
        mock_post.assert_not_called()


def test_auto_heal_success_flow():
    """Verify successful auto-healing probe reloads account and dispatches Telegram notification."""
    sw._healer_memory_first_seen.clear()
    sw._healer_memory_attempts.clear()
    sw._healer_memory_last_attempt.clear()

    now = time.time()
    sw._healer_memory_first_seen["acc_ok"] = now - 4000
    sw._healer_memory_attempts["acc_ok"] = 0

    account = {
        "id": "acc_ok",
        "email": "healed@gmail.com",
        "proxy_disabled": True,
        "quota": {"is_forbidden": True},
    }

    mock_quota_resp = MagicMock()
    mock_quota_resp.status_code = 200
    mock_quota_resp.content = b'{"quota": {"is_forbidden": false}}'
    mock_quota_resp.json.return_value = {"quota": {"is_forbidden": False}}

    mock_toggle_resp = MagicMock()
    mock_toggle_resp.status_code = 200
    mock_toggle_resp.json.return_value = {"ok": True}

    with patch("requests.get", return_value=mock_quota_resp) as mock_get, \
         patch("requests.post", return_value=mock_toggle_resp) as mock_post, \
         patch("scripts.smart_watchdog.notify_chatops") as mock_notify:
        mock_notify.return_value = True

        healed_email = sw.auto_heal_single_candidate([account], "http://127.0.0.1:8045", {"Auth": "Bearer test"})

        assert healed_email == "healed@gmail.com"
        # 1. Quota probed
        mock_get.assert_called_once_with(
            "http://127.0.0.1:8045/api/accounts/acc_ok/quota",
            headers={"Auth": "Bearer test"},
            timeout=30,
        )
        # 2. Toggle-proxy called with enable=True
        mock_post.assert_called_once_with(
            "http://127.0.0.1:8045/api/accounts/acc_ok/toggle-proxy",
            headers={"Auth": "Bearer test"},
            json={"enable": True},
            timeout=10,
        )
        # 3. Notification dispatched
        mock_notify.assert_called_once()
        title = mock_notify.call_args[0][0]
        assert "TỰ ĐỘNG PHỤC HỒI" in title

        # 4. State cleared on success
        assert "acc_ok" not in sw._healer_memory_first_seen


def test_auto_heal_forbidden_probe_retains_lock():
    """Verify that if Google upstream quota is still exhausted, toggle-proxy is NOT called."""
    sw._healer_memory_first_seen.clear()
    sw._healer_memory_attempts.clear()
    sw._healer_memory_last_attempt.clear()

    now = time.time()
    sw._healer_memory_first_seen["acc_still_blocked"] = now - 4000
    sw._healer_memory_attempts["acc_still_blocked"] = 0

    account = {
        "id": "acc_still_blocked",
        "email": "still@gmail.com",
        "proxy_disabled": True,
        "quota": {"is_forbidden": True},
    }

    mock_quota_resp = MagicMock()
    mock_quota_resp.status_code = 200
    mock_quota_resp.content = b'{"quota": {"is_forbidden": true, "forbidden_reason": "403 Rate Limit"}}'
    mock_quota_resp.json.return_value = {"quota": {"is_forbidden": True, "forbidden_reason": "403 Rate Limit"}}

    with patch("requests.get", return_value=mock_quota_resp) as mock_get, \
         patch("requests.post") as mock_post:
        res = sw.auto_heal_single_candidate([account], "http://127.0.0.1:8045", {})

        assert res is None
        mock_get.assert_called_once()
        # Toggle proxy must NEVER be called
        mock_post.assert_not_called()
        # Attempt recorded
        assert sw._healer_memory_attempts["acc_still_blocked"] == 1


def test_auto_heal_rate_limit_one_per_cycle():
    """Verify exactly one candidate is healed per cycle, prioritized deterministically."""
    sw._healer_memory_first_seen.clear()
    sw._healer_memory_attempts.clear()
    sw._healer_memory_last_attempt.clear()

    now = time.time()
    # Candidate A: 0 attempts, age 4000s
    sw._healer_memory_first_seen["acc_A"] = now - 4000
    sw._healer_memory_attempts["acc_A"] = 0

    # Candidate B: 1 attempt, age 5000s
    sw._healer_memory_first_seen["acc_B"] = now - 5000
    sw._healer_memory_attempts["acc_B"] = 1
    sw._healer_memory_last_attempt["acc_B"] = now - 3700

    accounts = [
        {"id": "acc_B", "email": "b@gmail.com", "proxy_disabled": True, "quota": {"is_forbidden": True}},
        {"id": "acc_A", "email": "a@gmail.com", "proxy_disabled": True, "quota": {"is_forbidden": True}},
    ]

    mock_quota_resp = MagicMock()
    mock_quota_resp.status_code = 200
    mock_quota_resp.content = b'{"quota": {"is_forbidden": false}}'
    mock_quota_resp.json.return_value = {"quota": {"is_forbidden": False}}

    mock_toggle_resp = MagicMock()
    mock_toggle_resp.status_code = 200
    mock_toggle_resp.json.return_value = {"ok": True}

    with patch("requests.get", return_value=mock_quota_resp) as mock_get, \
         patch("requests.post", return_value=mock_toggle_resp) as mock_post, \
         patch("scripts.smart_watchdog.notify_chatops"):
        # Candidate A should be prioritized because attempts (0) < attempts (1)
        healed_email = sw.auto_heal_single_candidate(accounts, "http://127.0.0.1:8045", {})

        assert healed_email == "a@gmail.com"
        assert mock_get.call_count == 1
        assert "acc_A" in mock_get.call_args[0][0]
        assert mock_post.call_count == 1
