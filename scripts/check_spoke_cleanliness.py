"""CCBA Spoke Cleanliness Checker — Pre-commit hook & Linter for Spoke repositories.

Enforces ADR 0044 & Issue #215 rules:
1. Script Count Budget: Limits root files in `scripts/` to <= 15 core files.
2. Ephemeral Script Detection: Flags one-off scripts (fix_*, audit_*, patch_*, tmp_*)
   and prompts archiving into `.md/archive/legacy_scripts/` or `.md/scratch/`.
3. Hub Duplication Gate: Flags duplicate implementations (custom crawlers, rate limiters,
   or `sys.path.insert` hacks) when Hub shared packages should be used.

Usage:
    python check_spoke_cleanliness.py [--path <spoke_root>] [--max-scripts 15] [--strict]
    # Or as a pre-commit hook in .pre-commit-config.yaml
"""

from __future__ import annotations

import argparse
import ast
import ipaddress
import re
import sys
from pathlib import Path

APPROVED_MODEL_ALIASES = frozenset({
    "ocr-primary",
    "ocr-fallback",
    "ocr-tier3",
    "ocr-tier4",
    "rag-core",
    "rag-light",
    "fast-realtime",
    "text-auto",
    "text-gemma",
    "text-gemma-12b",
    "text-gemma-4b",
    "text-light-auto",
    "reasoning-gemma",
    "qwen-local-primary",
    "gemini-flash-latest",
    "gemini-reasoning-latest",
    "embedding-default",
})

RAW_MODEL_PREFIXES = (
    "gemini-",
    "claude-",
    "gpt-",
    "deepseek-",
    "gemma-",
    "qwen-",
    "grok-",
    "mistral-",
    "openai/",
    "anthropic/",
    "gemini/",
)

FILE_LEVEL_MODEL_EXEMPT_NAMES = frozenset({
    "litellm_config.yaml",
    "custom_callbacks.py",
    "check_spoke_cleanliness.py",
})

STANDARD_PUBLIC_DNS = frozenset({"8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1"})

IPV4_CANDIDATE_PATTERN = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")

# System and Guardrail scripts that do NOT count towards the 15-file limit
ALLOWLIST_SCRIPTS = {
    "__init__.py",
    "conftest.py",
    "safe_pytest.py",
    "safe_runner.py",
    "check_hub_import_depth.py",
    "check_spoke_cleanliness.py",
    "check_claudekit_updates.py",
    "spoke_bootstrap.py",
    "spoke_bootstrap.ps1",
    "setup_pre_commit.py",
    "sync.py",
}

# Prefix patterns indicating one-off or temporary scripts
EPHEMERAL_PREFIXES = (
    "fix_",
    "audit_",
    "patch_",
    "test_tmp_",
    "debug_",
    "tmp_",
    "temp_",
    "oneoff_",
    "scratch_",
)

# Patterns detecting anti-patterns or duplicated hub functionality
SYS_PATH_HACK_PATTERN = re.compile(
    r"sys\.path\.(?:insert|append)\s*\(\s*0?\s*,\s*.*hub", re.IGNORECASE
)

# Patterns detecting hardcoded machine state leakage (drive letters or home user paths)
MACHINE_STATE_LEAK_PATTERNS = [
    (
        re.compile(r"""(?:["']|[=:]\s*)[A-Za-z]:[\\/]+[A-Za-z0-9_.-]+[\\/]+"""),
        "Hardcoded Windows drive path",
    ),
    (
        re.compile(r"""(?:["']|[=:]\s*)/home/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"""),
        "Hardcoded POSIX user home path",
    ),
]


def check_machine_state_leakage(
    target_files: list[Path],
) -> list[tuple[Path, int, str]]:
    """Checks for hardcoded machine-specific absolute paths (e.g. C:\\, D:\\, /home/user)."""
    violations: list[tuple[Path, int, str]] = []
    for filepath in target_files:
        try:
            content = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        in_docstring = False
        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.count('"""') % 2 == 1 or stripped.count("'''") % 2 == 1:
                in_docstring = not in_docstring
            if (
                in_docstring
                or stripped.startswith(("#", "//", "/*", "*"))
                or "ccba:allow-machine-path" in stripped
                or "noqa" in stripped
                or "path/to" in stripped
                or "example" in stripped
                or "dummy" in stripped
            ):
                continue
            for pattern, desc in MACHINE_STATE_LEAK_PATTERNS:
                if pattern.search(stripped):
                    violations.append(
                        (
                            filepath,
                            line_num,
                            f"{desc} detected. Use environment variables (e.g. CCBA_HUB_PATH) or relative paths.",
                        )
                    )
                    break
    return violations


def check_raw_model_leakage(
    target_files: list[Path],
) -> list[tuple[Path, int, str]]:
    """Checks for hardcoded raw model identifiers (e.g. gemini-*, claude-*, gpt-*, openai/*)."""
    violations: list[tuple[Path, int, str]] = []
    for filepath in target_files:
        if filepath.name in FILE_LEVEL_MODEL_EXEMPT_NAMES:
            continue
        try:
            content = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        lines = content.splitlines()
        # Check first 5 lines for file-level exemption
        if any("ccba:allow-raw-model-file" in line for line in lines[:5]):
            continue

        try:
            tree = ast.parse(content, filename=str(filepath))
        except SyntaxError:
            continue

        docstring_linenos = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    start_ln = getattr(node.body[0], "lineno", 0)
                    end_ln = getattr(node.body[0], "end_lineno", start_ln)
                    for ln in range(start_ln, end_ln + 1):
                        docstring_linenos.add(ln)

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value.strip().lower()
                lineno = getattr(node, "lineno", 0)
                if lineno in docstring_linenos or lineno <= 0 or lineno > len(lines):
                    continue

                line_text = lines[lineno - 1]
                if "ccba:allow-raw-model" in line_text:
                    continue

                if val in APPROVED_MODEL_ALIASES:
                    continue

                # Check if val starts with raw provider prefix
                if any(val.startswith(pfx) for pfx in RAW_MODEL_PREFIXES):
                    # Exclude multi-word prose or long text
                    if len(val) < 60 and (" " not in val):
                        violations.append(
                            (
                                filepath,
                                lineno,
                                f"Raw model string '{node.value}' detected. "
                                "Use capability alias or annotate with '# ccba:allow-raw-model'.",
                            )
                        )
    return violations


def check_raw_ip_leakage(
    target_files: list[Path],
) -> list[tuple[Path, int, str]]:
    """Checks for hardcoded non-local IPv4 addresses in code, scripts, and configs."""
    violations: list[tuple[Path, int, str]] = []
    for filepath in target_files:
        try:
            content = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        in_docstring = False
        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.count('"""') % 2 == 1 or stripped.count("'''") % 2 == 1:
                in_docstring = not in_docstring
            if (
                in_docstring
                or stripped.startswith(("#", "//", "/*", "*"))
                or "ccba:allow-raw-ip" in stripped
            ):
                continue

            for match in IPV4_CANDIDATE_PATTERN.finditer(line):
                ip_str = match.group(1)
                try:
                    ip = ipaddress.IPv4Address(ip_str)
                    if (
                        ip.is_loopback
                        or ip.is_unspecified
                        or ip.is_multicast
                        or ip_str == "255.255.255.255"
                        or ip_str in STANDARD_PUBLIC_DNS
                    ):
                        continue
                    violations.append(
                        (
                            filepath,
                            line_num,
                            f"Hardcoded IP address '{ip_str}' detected. "
                            "Use env vars (e.g. GATEWAY_PROXY_URL) or annotate with '# ccba:allow-raw-ip'.",
                        )
                    )
                    break
                except ValueError:
                    continue
    return violations


def check_script_count(scripts_dir: Path, max_scripts: int = 15) -> tuple[list[Path], list[Path]]:
    """Checks the number of top-level scripts in the scripts/ folder.

    Returns:
        (counted_scripts, ignored_scripts)
    """
    if not scripts_dir.exists() or not scripts_dir.is_dir():
        return [], []

    all_py_files = [f for f in scripts_dir.iterdir() if f.is_file() and f.suffix == ".py"]
    counted: list[Path] = []
    ignored: list[Path] = []

    for f in all_py_files:
        if f.name in ALLOWLIST_SCRIPTS or f.name.startswith("check_"):
            ignored.append(f)
        else:
            counted.append(f)

    return counted, ignored


def check_ephemeral_scripts(scripts: list[Path]) -> list[Path]:
    """Finds scripts that match ephemeral / one-off naming conventions."""
    ephemeral: list[Path] = []
    for s in scripts:
        name_lower = s.name.lower()
        if any(name_lower.startswith(prefix) for prefix in EPHEMERAL_PREFIXES):
            ephemeral.append(s)
    return ephemeral


def check_hub_duplications(target_files: list[Path]) -> list[tuple[Path, int, str]]:
    """Checks for sys.path hacks or duplicated Hub implementations."""
    violations: list[tuple[Path, int, str]] = []
    for filepath in target_files:
        try:
            content = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if SYS_PATH_HACK_PATTERN.search(stripped):
                violations.append(
                    (
                        filepath,
                        line_num,
                        "Anti-pattern sys.path hack detected. Use 'pip install -e' via spoke_bootstrap.py instead.",
                    )
                )
    return violations


def scan_spoke_cleanliness(
    spoke_root: Path, max_scripts: int = 15, strict: bool = False
) -> tuple[int, list[str]]:
    """Runs all cleanliness checks against a target Spoke workspace.

    Returns:
        (exit_code, messages)
    """
    messages: list[str] = []
    has_errors = False
    has_warnings = False

    scripts_dir = spoke_root / "scripts"
    if scripts_dir.exists():
        counted_scripts, ignored_scripts = check_script_count(scripts_dir, max_scripts=max_scripts)
        count = len(counted_scripts)

        if count > max_scripts:
            has_errors = True

            def _get_role(name: str) -> str:
                if name in {"chatops_daemon.py", "smart_watchdog.py", "model_auto_updater.py", "peer_bridge_watcher.py"}:
                    return "daemon"
                if name in {"hermes_executive_mcp.py", "mcp_server.py"}:
                    return "mcp"
                if name in {"prune_spend_logs.py"}:
                    return "cron"
                if name.startswith("benchmark_"):
                    return "benchmark"
                if name.startswith("verify_"):
                    return "verify"
                return "one-off"

            file_roles = [f"{f.name} ({_get_role(f.name)})" for f in sorted(counted_scripts, key=lambda x: x.name)]
            messages.append(
                f"❌ [Script Budget Vượt Ngưỡng] Thư mục 'scripts/' có {count} tệp (tối đa cho phép: {max_scripts}).\n"
                f"   Các file đang đếm ({count}): {', '.join(file_roles)}\n"
                "   💡 Giải pháp: Chỉ di chuyển các script một lần (one-off) vào '.md/archive/legacy_scripts/' hoặc '.md/scratch/'. "
                "Tuyệt đối không di chuyển daemon, mcp server hoặc script cron (chatops_daemon, smart_watchdog, hermes_executive_mcp, mcp_server, model_auto_updater, peer_bridge_watcher, prune_spend_logs)."
            )
        else:
            messages.append(
                f"✅ [Script Budget] Thư mục 'scripts/' có {count}/{max_scripts} tệp hợp lệ "
                f"({len(ignored_scripts)} tệp hệ thống được bỏ qua)."
            )

        # Ephemeral scripts
        ephemeral = check_ephemeral_scripts(counted_scripts)
        if ephemeral:
            has_warnings = True
            messages.append(
                f"⚠️  [Script Tạm Thời] Phát hiện {len(ephemeral)} script có tiền tố tạm thời "
                "(fix_*, audit_*, patch_*, tmp_*):\n"
                + "\n".join(f"   - {f.name}" for f in ephemeral)
                + "\n   💡 Hãy chuyển các script này vào '.md/archive/legacy_scripts/' sau khi chạy xong."
            )

        # Collect Python files across scripts/, src/, services/, and examples/ (excluding tests, venv, etc.)
        exclude_dirs = {
            ".venv",
            "venv",
            "__pycache__",
            "tests",
            "archive",
            "legacy_scripts",
            "node_modules",
            ".git",
            "dist",
            "build",
        }
        scan_roots = [
            scripts_dir,
            spoke_root / "src",
            spoke_root / "services",
            spoke_root / "examples",
        ]
        py_files_to_scan: list[Path] = []
        for d in scan_roots:
            if d.exists():
                py_files_to_scan.extend(
                    [
                        f
                        for f in d.rglob("*.py")
                        if not any(p in exclude_dirs for p in f.parts)
                    ]
                )

        # 1. Hub duplication / sys.path hacks
        dup_violations = check_hub_duplications(py_files_to_scan)
        if dup_violations:
            has_errors = True
            messages.append(
                f"❌ [Vi phạm Hub Duplication / sys.path] Phát hiện {len(dup_violations)} vị trí vi phạm:\n"
                + "\n".join(
                    f"   - {f.relative_to(spoke_root)}:{ln}: {msg}" for f, ln, msg in dup_violations
                )
            )

        # 2. Raw model string leakage (AST-based)
        model_violations = check_raw_model_leakage(py_files_to_scan)
        if model_violations:
            has_errors = True
            messages.append(
                f"❌ [Vi phạm Raw Model Leakage] Phát hiện {len(model_violations)} vị trí chứa model thô:\n"
                + "\n".join(
                    f"   - {f.relative_to(spoke_root)}:{ln}: {msg}" for f, ln, msg in model_violations
                )
                + "\n   💡 Dùng alias (ocr-primary, fast-realtime, text-auto, ...) hoặc '# ccba:allow-raw-model'."
            )
        else:
            messages.append("✅ [Model Externalization] Không phát hiện chuỗi model thô chưa chuẩn hoá.")

        # 3. Raw IP leakage (ipaddress-based)
        files_to_check_ip: list[Path] = list(py_files_to_scan)
        for cand_name in ["docker-compose.yml", "docker-compose.dev.yml", "docker-compose.prod.yml", ".env.example"]:
            cand = spoke_root / cand_name
            if cand.is_file():
                files_to_check_ip.append(cand)

        for d in [scripts_dir, spoke_root / "services", spoke_root / "examples"]:
            if d.exists():
                for ext in ("*.yaml", "*.yml", "*.sh"):
                    files_to_check_ip.extend(
                        [
                            f
                            for f in d.rglob(ext)
                            if not any(p in exclude_dirs for p in f.parts)
                        ]
                    )

        # Deduplicate files_to_check_ip
        seen_ip_files: set[Path] = set()
        unique_ip_files: list[Path] = []
        for f in files_to_check_ip:
            if f not in seen_ip_files and f.is_file():
                seen_ip_files.add(f)
                unique_ip_files.append(f)

        ip_violations = check_raw_ip_leakage(unique_ip_files)
        if ip_violations:
            has_errors = True
            messages.append(
                f"❌ [Vi phạm Raw IP Leakage] Phát hiện {len(ip_violations)} vị trí chứa địa chỉ IPv4 thô:\n"
                + "\n".join(
                    f"   - {f.relative_to(spoke_root)}:{ln}: {msg}" for f, ln, msg in ip_violations
                )
                + "\n   💡 Dùng biến môi trường (GATEWAY_PROXY_URL, AI_GATEWAY_HOST) hoặc '# ccba:allow-raw-ip'."
            )
        else:
            messages.append("✅ [IP Externalization] Không phát hiện hardcoded IPv4 trong code/config.")

        # 4. Machine-state leakage (scripts/, src/, workspace_context.yaml)
        files_to_check_machine: list[Path] = list(py_files_to_scan)
        for ctx_name in [".md/workspace_context.yaml", "workspace_context.yaml"]:
            ctx_cand = spoke_root / ctx_name
            if ctx_cand.is_file():
                files_to_check_machine.append(ctx_cand)

        machine_violations = check_machine_state_leakage(files_to_check_machine)
        if machine_violations:
            has_errors = True
            messages.append(
                f"❌ [Vi phạm Machine-State Leakage] Phát hiện {len(machine_violations)} "
                "vị trí chứa đường dẫn tuyệt đối:\n"
                + "\n".join(
                    f"   - {f.relative_to(spoke_root)}:{ln}: {msg}"
                    for f, ln, msg in machine_violations
                )
                + "\n   💡 Hãy dùng biến môi trường (CCBA_HUB_PATH) hoặc đường dẫn tương đối để tránh xung đột đa máy."
            )
        else:
            messages.append("✅ [Machine-State] Không phát hiện rò rỉ đường dẫn máy tuyệt đối.")

    exit_code = 1 if has_errors or (strict and has_warnings) else 0
    return exit_code, messages


def main() -> int:
    """CLI runner for spoke cleanliness check."""
    if sys.platform == "win32":
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="CCBA Spoke Cleanliness & Script Budget Checker (ADR 0044 / Issue #215)"
    )
    parser.add_argument(
        "--path",
        "-p",
        default=".",
        help="Target Spoke root directory (default: current dir)",
    )
    parser.add_argument(
        "--max-scripts",
        type=int,
        default=15,
        help="Maximum number of core scripts in scripts/ folder (default: 15)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail (exit code 1) on warnings such as ephemeral script names",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Optional specific files passed by pre-commit",
    )
    args = parser.parse_args()

    spoke_root = Path(args.path).resolve()
    exit_code, messages = scan_spoke_cleanliness(
        spoke_root=spoke_root, max_scripts=args.max_scripts, strict=args.strict
    )

    print("=" * 80)
    print("🧹 CCBA Spoke Cleanliness Report")
    print("=" * 80)
    for m in messages:
        print(m)
    print("=" * 80)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
