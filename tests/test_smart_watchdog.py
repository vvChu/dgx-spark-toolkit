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
    # Flat QuotaData schema returned by Antigravity-Manager server.rs
    mock_quota_resp.content = b'{"is_forbidden": false, "models": [], "last_updated": 1727540000}'
    mock_quota_resp.json.return_value = {"is_forbidden": False, "models": [], "last_updated": 1727540000}

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
    """Verify that if Google upstream quota is still exhausted (flat QuotaData schema), toggle-proxy is NOT called."""
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

    # Flat QuotaData schema with is_forbidden: True
    mock_quota_resp = MagicMock()
    mock_quota_resp.status_code = 200
    mock_quota_resp.content = b'{"is_forbidden": true, "forbidden_reason": "RESOURCE_EXHAUSTED", "models": []}'
    mock_quota_resp.json.return_value = {
        "is_forbidden": True,
        "forbidden_reason": "RESOURCE_EXHAUSTED",
        "models": [],
    }

    with patch("requests.get", return_value=mock_quota_resp) as mock_get, \
         patch("requests.post") as mock_post:
        res = sw.auto_heal_single_candidate([account], "http://127.0.0.1:8045", {})

        assert res is None
        mock_get.assert_called_once()
        # Toggle proxy must NEVER be called
        mock_post.assert_not_called()
        # Attempt recorded
        assert sw._healer_memory_attempts["acc_still_blocked"] == 1


def test_auto_heal_malformed_or_corrupted_payload_retains_lock():
    """Verify corrupted or empty quota responses fail closed without calling toggle-proxy."""
    sw._healer_memory_first_seen.clear()
    sw._healer_memory_attempts.clear()

    now = time.time()
    account = {"id": "acc_malformed", "email": "malformed@gmail.com", "proxy_disabled": True}

    for bad_content, bad_json in [
        (b"{}", {}),
        (b'{"is_forbidden": "false"}', {"is_forbidden": "false"}),  # non-boolean string
        (b'{"quota": {}}', {"quota": {}}),
        (b"null", None),
    ]:
        sw._healer_memory_first_seen["acc_malformed"] = now - 4000
        sw._healer_memory_attempts["acc_malformed"] = 0

        mock_quota_resp = MagicMock()
        mock_quota_resp.status_code = 200
        mock_quota_resp.content = bad_content
        mock_quota_resp.json.return_value = bad_json

        with patch("requests.get", return_value=mock_quota_resp), \
             patch("requests.post") as mock_post:
            res = sw.auto_heal_single_candidate([account], "http://127.0.0.1:8045", {})
            assert res is None, f"Failed closed expectation for {bad_content}"
            mock_post.assert_not_called()


def test_healer_redis_isolated_db5_and_state_tracking(monkeypatch):
    """Verify watchdog healer isolates state to Redis DB 5 and clears state when accounts recover."""
    monkeypatch.setenv("REDIS_URL", "redis://litellm-redis:6379/0")  # compose default points to DB 0
    monkeypatch.delenv("WATCHDOG_REDIS_URL", raising=False)

    captured_url = None

    class FakeRedis:
        def __init__(self):
            self.data = {}

        def get(self, k):
            return self.data.get(k)

        def set(self, k, v, nx=False, ex=None):
            if nx and k in self.data:
                return False
            self.data[k] = v
            return True

        def delete(self, *keys):
            for k in keys:
                self.data.pop(k, None)

        def pipeline(self):
            return self

        def incr(self, k):
            self.data[k] = str(int(self.data.get(k, 0)) + 1)

        def expire(self, k, ex):
            pass

        def execute(self):
            return [True]

        def scan_iter(self, match=None, count=100):
            return [b"watchdog:healer:first_seen:acc_recovered"]

    fake_r = FakeRedis()

    def fake_from_url(url, **kwargs):
        nonlocal captured_url
        captured_url = url
        return fake_r

    with patch("redis.Redis.from_url", side_effect=fake_from_url):
        # 1. Check DB 5 URL rewrite
        client = sw._get_redis_client()
        assert client is fake_r
        assert captured_url == "redis://litellm-redis:6379/5", f"Expected isolated DB 5, got {captured_url}"

        # 2. Record first seen
        sw.record_account_first_seen("acc_test_redis")
        assert f"watchdog:healer:first_seen:acc_test_redis" in fake_r.data

        # 3. Record attempt
        sw.record_healing_attempt("acc_test_redis")
        assert fake_r.data.get("watchdog:healer:attempts:acc_test_redis") == "1"

        # 4. Check lockout info
        fs, att, la = sw.get_account_lockout_info("acc_test_redis")
        assert att == 1
        assert fs > 0

        # 5. Clear state
        sw.clear_account_healer_state("acc_test_redis")
        assert f"watchdog:healer:first_seen:acc_test_redis" not in fake_r.data


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
    mock_quota_resp.content = b'{"is_forbidden": false, "models": []}'
    mock_quota_resp.json.return_value = {"is_forbidden": False, "models": []}

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


def test_auto_heal_nested_forbidden_retains_lock():
    """Verify backward compatibility that nested quota.is_forbidden: true also retains lock."""
    sw._healer_memory_first_seen.clear()
    sw._healer_memory_attempts.clear()

    now = time.time()
    sw._healer_memory_first_seen["acc_nest_block"] = now - 4000
    sw._healer_memory_attempts["acc_nest_block"] = 0

    account = {
        "id": "acc_nest_block",
        "email": "nest@gmail.com",
        "proxy_disabled": True,
        "quota": {"is_forbidden": True},
    }

    mock_quota_resp = MagicMock()
    mock_quota_resp.status_code = 200
    mock_quota_resp.content = b'{"quota": {"is_forbidden": true, "forbidden_reason": "NESTED_EXHAUSTED"}}'
    mock_quota_resp.json.return_value = {"quota": {"is_forbidden": True, "forbidden_reason": "NESTED_EXHAUSTED"}}

    with patch("requests.get", return_value=mock_quota_resp) as mock_get, \
         patch("requests.post") as mock_post:
        res = sw.auto_heal_single_candidate([account], "http://127.0.0.1:8045", {})

        assert res is None
        mock_get.assert_called_once()
        mock_post.assert_not_called()
        assert sw._healer_memory_attempts["acc_nest_block"] == 1


def test_auto_heal_clears_state_by_account_id_on_recovery(monkeypatch):
    """Verify check_quota_pool clears healer state by account_id for recovered accounts across RAM and Redis SCAN."""
    monkeypatch.setattr(sw, "GATEWAY_PROXY_KEY", "test_key")
    sw._healer_memory_first_seen.clear()
    sw._healer_memory_attempts.clear()
    sw._healer_memory_last_attempt.clear()

    # Pre-populate healer memory for an account
    sw._healer_memory_first_seen["acc_rec_1"] = time.time() - 5000
    sw._healer_memory_attempts["acc_rec_1"] = 2

    # Mock Redis client with scan_iter
    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = [b"watchdog:healer:first_seen:acc_rec_1", b"watchdog:healer:first_seen:acc_rec_2"]

    # All accounts are now healthy (0 blocked)
    accounts = [
        {"id": "acc_rec_1", "email": "rec1@gmail.com", "disabled": False, "proxy_disabled": False},
        {"id": "acc_rec_2", "email": "rec2@gmail.com", "disabled": False, "proxy_disabled": False},
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"accounts": accounts}

    with patch("scripts.smart_watchdog._get_redis_client", return_value=mock_redis), \
         patch("requests.get", return_value=mock_resp):
        sw.check_quota_pool()

        # Both acc_rec_1 and acc_rec_2 should have clear_account_healer_state called
        assert "acc_rec_1" not in sw._healer_memory_first_seen
        # Redis delete must have been called for both
        assert mock_redis.delete.call_count >= 2


def test_watchdog_redis_url_db5_resolution(monkeypatch):
    """Verify _get_redis_client resolves DB 5 correctly with explicit URL, fallback, and default."""
    # 1. Explicit WATCHDOG_REDIS_URL retains path /15
    monkeypatch.setenv("WATCHDOG_REDIS_URL", "redis://127.0.0.1:1/15")
    with patch("redis.Redis.from_url") as mock_from_url:
        sw._get_redis_client()
        mock_from_url.assert_called_with("redis://127.0.0.1:1/15", socket_timeout=2)

    # 2. Derived from REDIS_URL switching path to /5
    monkeypatch.delenv("WATCHDOG_REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://:secret_pass@litellm-redis:6379/0")
    with patch("redis.Redis.from_url") as mock_from_url:
        sw._get_redis_client()
        call_url = mock_from_url.call_args[0][0]
        assert "/5" in call_url
        assert "secret_pass" in call_url
        assert "litellm-redis:6379" in call_url

    # 3. Default when both unset
    monkeypatch.delenv("WATCHDOG_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with patch("redis.Redis.from_url") as mock_from_url:
        sw._get_redis_client()
        call_url = mock_from_url.call_args[0][0]
        assert call_url == "redis://litellm-redis:6379/5"


def test_daily_digest_counts_validation_blocked_account():
    """Verify build_daily_digest_message correctly counts validation_blocked accounts as blocked."""
    fake_accounts = [
        {"id": "acc_1", "email": "a1@gmail.com", "disabled": False, "proxy_disabled": False},
        {"id": "acc_2", "email": "a2@gmail.com", "disabled": False, "proxy_disabled": False, "validation_blocked": True},
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"accounts": fake_accounts}

    with patch("requests.get", return_value=mock_resp), \
         patch("scripts.smart_watchdog.get_hardware_metrics", return_value="RAM: OK"), \
         patch("scripts.smart_watchdog.get_top_models", return_value="Top: None"), \
         patch("scripts.smart_watchdog.get_gateway_telemetry_digest", return_value="GW: OK"):
        digest = sw.build_daily_digest_message("29/09/2026")
        assert "1/2" in digest
        assert "1 tạm ngắt" in digest

