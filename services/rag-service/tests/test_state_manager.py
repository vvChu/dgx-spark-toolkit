"""Unit tests for the refactored PostgresStateManager (Fixes 1-6).

These tests verify the source code structure without requiring sqlalchemy
(which is only installed inside the Docker container).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Read source as text to avoid import dependency on sqlalchemy
_SOURCE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "ingestion", "state_manager.py")
with open(_SOURCE_PATH) as f:
    _SOURCE = f.read()


class TestFix1Indexes:
    """Fix 1: doc_id and completed_timestamp indexes should be created."""

    def test_docid_index(self):
        assert "idx_ingestion_docid" in _SOURCE

    def test_completed_index(self):
        assert "idx_ingestion_completed" in _SOURCE

    def test_status_index(self):
        assert "idx_ingestion_status" in _SOURCE

    def test_claim_index(self):
        assert "idx_ingestion_claim" in _SOURCE


class TestFix2NoSession:
    """Fix 2: No more Session() — only engine.begin()/connect()."""

    def test_no_session_attribute(self):
        assert "self.Session" not in _SOURCE

    def test_no_sessionmaker_import(self):
        assert "sessionmaker" not in _SOURCE

    def test_uses_engine_begin(self):
        assert "self.engine.begin()" in _SOURCE

    def test_uses_engine_connect(self):
        assert "self.engine.connect()" in _SOURCE


class TestFix3MilestoneCTE:
    """Fix 3: Milestone check should use CTE."""

    def test_cte_query(self):
        assert "WITH counts AS" in _SOURCE

    def test_left_join(self):
        assert "LEFT JOIN checkpoint" in _SOURCE


class TestFix4StatusSummary:
    """Fix 4: get_status_summary should exist and use GROUP BY."""

    def test_method_exists(self):
        assert "def get_status_summary" in _SOURCE

    def test_uses_group_by(self):
        assert "GROUP BY status" in _SOURCE


class TestFix5UpdateStatus:
    """Fix 5: update_status should use engine.begin()."""

    def test_update_uses_engine(self):
        # Extract just the update_status method body
        start = _SOURCE.index("def update_status")
        # Find next def at same indentation
        end = _SOURCE.index("\n    def ", start + 1)
        method = _SOURCE[start:end]
        assert "self.engine.begin()" in method
        assert "self.Session" not in method


class TestFix6HealthCheck:
    """Fix 6: health_check method should exist."""

    def test_method_exists(self):
        assert "def health_check" in _SOURCE

    def test_returns_pool_stats(self):
        start = _SOURCE.index("def health_check")
        method = _SOURCE[start:]
        assert "pool_size" in method
        assert "checked_out" in method
        assert "overflow" in method


def run_all():
    passed = 0
    failed = 0

    for cls_name, cls in [
        ("TestFix1Indexes", TestFix1Indexes),
        ("TestFix2NoSession", TestFix2NoSession),
        ("TestFix3MilestoneCTE", TestFix3MilestoneCTE),
        ("TestFix4StatusSummary", TestFix4StatusSummary),
        ("TestFix5UpdateStatus", TestFix5UpdateStatus),
        ("TestFix6HealthCheck", TestFix6HealthCheck),
    ]:
        instance = cls()
        for attr in sorted(dir(instance)):
            if attr.startswith("test_"):
                try:
                    getattr(instance, attr)()
                    passed += 1
                    print(f"  ✅ {cls_name}.{attr}")
                except AssertionError as e:
                    failed += 1
                    print(f"  ❌ {cls_name}.{attr}: {e}")
                except Exception as e:
                    failed += 1
                    print(f"  💥 {cls_name}.{attr}: {type(e).__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
