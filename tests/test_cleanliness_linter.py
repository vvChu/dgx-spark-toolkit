"""Unit tests for check_spoke_cleanliness linter rules:

- Raw model string leakage (AST-based detection)
- Raw IPv4 address leakage (ipaddress-based detection)
- Exemption mechanisms (# ccba:allow-raw-model, # ccba:allow-raw-ip, # ccba:allow-raw-model-file)
"""

from pathlib import Path
from scripts.check_spoke_cleanliness import (
    check_raw_ip_leakage,
    check_raw_model_leakage,
)


def test_detect_raw_model_strings(tmp_path: Path):
    """Verifies that raw provider model strings in code trigger violations."""
    code_file = tmp_path / "bad_models.py"
    code_file.write_text(
        """
def run_llm():
    m1 = "gemini-3-flash"
    m2 = "claude-haiku-4"
    m3 = "openai/gemma-4-26b-a4b-it"
    m4 = "gpt-4o"
    m5 = "deepseek-v3"
    return [m1, m2, m3, m4, m5]
""",
        encoding="utf-8",
    )

    violations = check_raw_model_leakage([code_file])
    assert len(violations) == 5
    violation_texts = [v[2] for v in violations]
    assert any("gemini-3-flash" in v for v in violation_texts)
    assert any("claude-haiku-4" in v for v in violation_texts)
    assert any("openai/gemma-4-26b-a4b-it" in v for v in violation_texts)
    assert any("gpt-4o" in v for v in violation_texts)
    assert any("deepseek-v3" in v for v in violation_texts)


def test_allowed_capability_aliases(tmp_path: Path):
    """Verifies that approved capability aliases do NOT trigger violations."""
    code_file = tmp_path / "good_aliases.py"
    code_file.write_text(
        """
def run_llm():
    a1 = "ocr-primary"
    a2 = "ocr-fallback"
    a3 = "fast-realtime"
    a4 = "text-auto"
    a5 = "text-gemma"
    a6 = "rag-core"
    return [a1, a2, a3, a4, a5, a6]
""",
        encoding="utf-8",
    )

    violations = check_raw_model_leakage([code_file])
    assert len(violations) == 0


def test_raw_model_exemptions(tmp_path: Path):
    """Verifies inline and file-level exemptions for raw model strings."""
    # 1. Inline exemption
    inline_file = tmp_path / "inline_exempt.py"
    inline_file.write_text(
        """
def legacy():
    model = "gemini-3-flash"  # ccba:allow-raw-model
    return model
""",
        encoding="utf-8",
    )
    assert len(check_raw_model_leakage([inline_file])) == 0

    # 2. File-level exemption header
    file_exempt = tmp_path / "file_exempt.py"
    file_exempt.write_text(
        """# ccba:allow-raw-model-file
def benchmark():
    return ["gemini-3.5-flash-lite", "claude-haiku-4"]
""",
        encoding="utf-8",
    )
    assert len(check_raw_model_leakage([file_exempt])) == 0

    # 3. Docstring exemption
    docstring_file = tmp_path / "docstring_only.py"
    docstring_file.write_text(
        '''
"""
This module talks about gemini-3-flash and claude-haiku-4 in docstrings.
"""
def foo():
    """Inner docstring mentioning gpt-4o."""
    pass
''',
        encoding="utf-8",
    )
    assert len(check_raw_model_leakage([docstring_file])) == 0


def test_detect_raw_ip_leakage(tmp_path: Path):
    """Verifies detection of raw non-local IPv4 addresses in code, scripts, and configs."""
    ip_file = tmp_path / "config_with_ips.py"
    ip_file.write_text(
        """
PROXY_URL = "http://100.83.192.30:8090/v1"
DIRECT_IP = "100.79.241.120"
""",
        encoding="utf-8",
    )

    violations = check_raw_ip_leakage([ip_file])
    assert len(violations) == 2
    assert any("100.83.192.30" in v[2] for v in violations)
    assert any("100.79.241.120" in v[2] for v in violations)


def test_allowed_ips_and_exemptions(tmp_path: Path):
    """Verifies that loopback, 0.0.0.0, public DNS, comments, and annotations are ignored."""
    allowed_file = tmp_path / "safe_config.py"
    allowed_file.write_text(
        """
# Commented IP should be ignored: 100.83.192.30
LOCAL_BASE = "http://127.0.0.1:8090/v1"
BIND_ALL = "0.0.0.0"
DNS_PRIMARY = "8.8.8.8"
DNS_SECONDARY = "1.1.1.1"
ANALYTICS_TARGET = "100.83.192.30"  # ccba:allow-raw-ip
""",
        encoding="utf-8",
    )

    violations = check_raw_ip_leakage([allowed_file])
    assert len(violations) == 0
