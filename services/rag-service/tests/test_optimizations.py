"""Unit tests for core.circuit_breaker and retrieval.query_classifier."""
import os
import time
import pytest

os.environ.setdefault("NEO4J_PASSWORD", "ci_test")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test")


# ── CircuitBreaker tests ──────────────────────────────────────────────────────

class TestCircuitBreaker:
    def _fresh(self, **kw):
        # Import fresh each time to avoid module singleton reuse in tests
        from core.circuit_breaker import CircuitBreaker
        return CircuitBreaker("test-model", **kw)

    def test_starts_closed(self):
        cb = self._fresh(failure_threshold=3)
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        cb = self._fresh(failure_threshold=3)
        for _ in range(3):
            cb.record_failure(Exception("err"))
        assert cb.state == "open"
        assert cb.allow_request() is False

    def test_does_not_open_before_threshold(self):
        cb = self._fresh(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"

    def test_success_resets_count(self):
        cb = self._fresh(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"  # Count reset by success

    def test_half_open_after_recovery_timeout(self):
        cb = self._fresh(failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        assert cb.state == "open"
        time.sleep(0.07)
        # Accessing state triggers transition
        assert cb.state == "half_open"
        assert cb.allow_request() is True

    def test_half_open_failure_reopens(self):
        cb = self._fresh(failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        time.sleep(0.07)
        cb.allow_request()  # Enter half_open
        cb.record_failure()
        assert cb.state == "open"

    def test_half_open_success_closes(self):
        cb = self._fresh(failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        time.sleep(0.07)
        cb.allow_request()  # Enter half_open
        cb.record_success()
        assert cb.state == "closed"

    def test_status_dict_structure(self):
        cb = self._fresh(failure_threshold=3)
        status = cb.status()
        assert "model" in status
        assert "state" in status
        assert "failure_count" in status
        assert status["state"] == "closed"


class TestKeyRateLimiter:
    def test_allows_up_to_rpm(self):
        from core.circuit_breaker import KeyRateLimiter
        lim = KeyRateLimiter(rpm=3, rpd=100)
        results = [lim.allow() for _ in range(4)]
        assert results[:3] == [True, True, True]
        assert results[3] is False

    def test_rpd_limit_blocks_after_daily_quota(self):
        from core.circuit_breaker import KeyRateLimiter
        lim = KeyRateLimiter(rpm=1000, rpd=3)
        results = [lim.allow() for _ in range(4)]
        assert results[:3] == [True, True, True]
        assert results[3] is False

    def test_remaining_shows_available(self):
        from core.circuit_breaker import KeyRateLimiter
        lim = KeyRateLimiter(rpm=10, rpd=100, key_id="my-key")
        lim.allow()
        lim.allow()
        r = lim.remaining()
        assert r["key_id"] == "my-key"
        assert r["rpm_available"] < 10
        assert r["rpd_available"] < 100

    def test_singleton_registry(self):
        from core.circuit_breaker import get_circuit_breaker
        cb1 = get_circuit_breaker("model-a")
        cb2 = get_circuit_breaker("model-a")
        assert cb1 is cb2  # Same instance

    def test_all_statuses_returns_list(self):
        from core.circuit_breaker import all_circuit_statuses, get_circuit_breaker
        get_circuit_breaker("test-status-1")
        get_circuit_breaker("test-status-2")
        statuses = all_circuit_statuses()
        assert isinstance(statuses, list)
        assert len(statuses) >= 2


# ── QueryClassifier tests ─────────────────────────────────────────────────────

class TestQueryClassifier:
    def classify(self, q):
        from retrieval.query_classifier import classify_query
        return classify_query(q).intent.value

    def test_doc_number_is_exact(self):
        assert self.classify("Nghị định 87/2023/NĐ-CP") == "exact"
        assert self.classify("Thông tư 16/2025/TT-BXD") == "exact"
        assert self.classify("1417/QĐ-TTg") == "exact"  # QD format

    def test_article_reference_is_exact(self):
        assert self.classify("Điều 15 khoản 3") == "exact"
        assert self.classify("Chương II Mục 1") == "exact"
        assert self.classify("Phần 4 của văn bản") == "exact"

    def test_technical_standard_is_exact(self):
        assert self.classify("QCVN 06:2022/BXD") == "exact"
        assert self.classify("TCVN 9385:2012") == "exact"

    def test_comparison_is_complex(self):
        assert self.classify("so sánh hai văn bản") == "complex"
        assert self.classify("khác nhau giữa Nghị định cũ và mới") == "complex"
        assert self.classify("phân biệt TT 01 và TT 02") == "complex"

    def test_timeline_is_complex(self):
        assert self.classify("văn bản nào thay thế NĐ này") == "complex"
        assert self.classify("lịch sử sửa đổi văn bản") == "complex"
        assert self.classify("còn hiệu lực không") == "complex"

    def test_conflict_is_complex(self):
        assert self.classify("mâu thuẫn giữa hai quy định") == "complex"
        assert self.classify("xung đột điều khoản") == "complex"

    def test_general_question_is_semantic(self):
        assert self.classify("yêu cầu phòng cháy chữa cháy nhà cao tầng") == "semantic"
        assert self.classify("thủ tục xin cấp phép xây dựng") == "semantic"
        assert self.classify("tiêu chuẩn kỹ thuật an toàn điện") == "semantic"

    def test_empty_query_is_semantic(self):
        assert self.classify("") == "semantic"
        assert self.classify("   ") == "semantic"

    def test_confidence_is_high_for_exact(self):
        from retrieval.query_classifier import classify_query
        r = classify_query("Điều 15 Nghị định 87/2023/NĐ-CP")
        assert r.confidence >= 0.85

    def test_search_weights_sum_to_one(self):
        from retrieval.query_classifier import get_search_weights, QueryIntent
        for intent in QueryIntent:
            w = get_search_weights(intent)
            assert abs(w["dense_weight"] + w["sparse_weight"] - 1.0) < 0.01

    def test_exact_has_high_sparse_weight(self):
        from retrieval.query_classifier import get_search_weights, QueryIntent
        w = get_search_weights(QueryIntent.EXACT)
        assert w["sparse_weight"] > w["dense_weight"]

    def test_complex_has_high_dense_weight(self):
        from retrieval.query_classifier import get_search_weights, QueryIntent
        w = get_search_weights(QueryIntent.COMPLEX)
        assert w["dense_weight"] > w["sparse_weight"]


# ── HITLService tests ─────────────────────────────────────────────────────────

class TestHITLService:
    def _fresh_hitl(self, **kw):
        from services.hitl_service import HITLService
        return HITLService(**kw)

    def test_low_confidence_always_flags(self):
        hitl = self._fresh_hitl(low_confidence_threshold=0.9, sample_rate=0.0)
        results = [{"score": 0.3, "text": "t"}]
        assert hitl.maybe_sample("query", results) is True
        assert hitl.queue_size() == 1

    def test_high_confidence_respects_sample_rate_0(self):
        hitl = self._fresh_hitl(low_confidence_threshold=0.1, sample_rate=0.0)
        results = [{"score": 0.95, "text": "t"}]
        assert hitl.maybe_sample("query", results) is False
        assert hitl.queue_size() == 0

    def test_sample_rate_1_always_queues(self):
        hitl = self._fresh_hitl(low_confidence_threshold=0.1, sample_rate=1.0)
        results = [{"score": 0.95, "text": "t"}]
        assert hitl.maybe_sample("query", results) is True

    def test_flag_for_review_explicit(self):
        hitl = self._fresh_hitl(sample_rate=0.0)
        hitl.flag_for_review("manual query", [], reason="manual")
        assert hitl.queue_size() == 1

    def test_queue_max_size_enforced(self):
        hitl = self._fresh_hitl(sample_rate=1.0, max_queue_size=3)
        for i in range(5):
            hitl.flag_for_review(f"query {i}", [])
        assert hitl.queue_size() == 3

    def test_get_pending_returns_list(self):
        hitl = self._fresh_hitl(sample_rate=1.0)
        hitl.flag_for_review("test query", [{"score": 0.5}])
        pending = hitl.get_pending_reviews(limit=10)
        assert isinstance(pending, list)
        assert len(pending) == 1
        assert "query" in pending[0]

    def test_submit_review_invalid_rating(self):
        hitl = self._fresh_hitl()
        with pytest.raises(ValueError):
            hitl.submit_review("q", rating=0)
        with pytest.raises(ValueError):
            hitl.submit_review("q", rating=6)
