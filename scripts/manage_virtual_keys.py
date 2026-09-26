#!/usr/bin/env python3
"""Automated Virtual Key Provisioning & Quota Management for LiteLLM Gateway.

This script manages LiteLLM virtual keys, monthly budgets, RPM/TPM limits,
and generates secure .env configuration files for federated spokes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import stat
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


# --- Standard Spoke Configurations ---
STANDARD_SPOKES: List[Dict[str, Any]] = [
    {
        "alias": "spoke-bim-planner",
        "budget": 50.0,
        "budget_duration": "30d",
        "models": [
            "qwen-3.5-35b",
            "embedding-default",
            "gpt-oss-120b-medium",
            "gemini-3.8-flash",
            "rag-core",
        ],
    },
    {
        "alias": "spoke-idop",
        "budget": 30.0,
        "budget_duration": "30d",
        "models": [
            "qwen-3.5-35b",
            "embedding-default",
            "gemini-3.8-flash",
        ],
    },
    {
        "alias": "spoke-legal",
        "budget": 30.0,
        "budget_duration": "30d",
        "models": [
            "qwen-3.5-35b",
            "embedding-default",
            "gemini-3.8-flash",
            "rag-core",
        ],
    },
    {
        "alias": "dev-tta",
        "budget": 20.0,
        "budget_duration": "30d",
        "models": None,
    },
    {
        "alias": "dev-tat",
        "budget": 20.0,
        "budget_duration": "30d",
        "models": None,
    },
]


# --- Custom Exception Hierarchy & Exit Codes ---
class VirtualKeyError(Exception):
    """Base exception for virtual key management operations."""

    exit_code: int = 1


class MasterKeyError(VirtualKeyError):
    """Raised when master key is missing or authentication fails."""

    exit_code: int = 1


class KeyNotFoundError(VirtualKeyError):
    """Raised when the specified key or alias is not found."""

    exit_code: int = 2


class ValidationError(VirtualKeyError):
    """Raised when parameters are invalid or duplicate alias exists."""

    exit_code: int = 3


class GatewayConnectionError(VirtualKeyError):
    """Raised when gateway connection fails or server returns 5xx error."""

    exit_code: int = 4


def mask_key(key: Optional[str]) -> str:
    """Mask sensitive API key for safe console display.

    Args:
        key: Raw or already masked API key.

    Returns:
        Masked string format e.g. 'sk-...XXXX'.
    """
    if not key:
        return "N/A"
    if "..." in key:
        return key
    if len(key) <= 8:
        return "sk-...XXXX"
    return f"{key[:5]}...{key[-4:]}"


def normalize_gateway_url(host_or_url: str) -> str:
    """Normalize gateway host or URL into a http(s) URL ending with /v1.

    Args:
        host_or_url: Host string (e.g. '100.83.192.30:8090') or full URL.

    Returns:
        Clean URL ending with '/v1'.
    """
    clean = host_or_url.strip().rstrip("/")
    if not (clean.startswith("http://") or clean.startswith("https://")):
        clean = f"http://{clean}"
    if not clean.endswith("/v1"):
        clean = f"{clean}/v1"
    return clean


def load_project_env() -> None:
    """Load .env from the project root if available."""
    if load_dotenv is not None:
        root_dir = Path(__file__).resolve().parent.parent
        env_file = root_dir / ".env"
        if env_file.is_file():
            load_dotenv(env_file)


class VirtualKeyManager:
    """Admin manager for LiteLLM virtual key lifecycle and budgets."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        master_key: Optional[str] = None,
        timeout: int = 15,
        load_env: bool = False,
    ) -> None:
        """Initialize VirtualKeyManager with gateway URL and master key.

        Args:
            base_url: LiteLLM proxy base URL (default from env or localhost).
            master_key: LiteLLM master key (default from env).
            timeout: HTTP request timeout in seconds.
            load_env: Whether to automatically load project .env file.

        Raises:
            MasterKeyError: If master key is not provided or configured.
        """
        if load_env:
            load_project_env()

        resolved_url = (
            base_url
            or os.getenv("LITELLM_URL")
            or os.getenv("LITELLM_BASE_URL")
            or "http://localhost:8090"
        )
        self.base_url = resolved_url.rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]

        self.master_key = master_key or os.getenv("LITELLM_MASTER_KEY")
        if not self.master_key:
            raise MasterKeyError(
                "LiteLLM master key is required. "
                "Set LITELLM_MASTER_KEY in environment or pass --master-key."
            )

        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.master_key}",
                "Content-Type": "application/json",
            }
        )

    def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> requests.Response:
        """Execute HTTP request against LiteLLM proxy with error handling.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path starting with '/'.
            **kwargs: Extra arguments passed to requests.Session.request.

        Returns:
            requests.Response object.

        Raises:
            MasterKeyError: On HTTP 401 or 403.
            KeyNotFoundError: On HTTP 404.
            ValidationError: On HTTP 400 or 422.
            GatewayConnectionError: On network error, timeout, or HTTP 5xx.
        """
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise GatewayConnectionError(
                f"Failed to connect to gateway at {url}: {exc}"
            ) from exc

        if resp.status_code in (401, 403):
            raise MasterKeyError(
                f"Authentication failed ({resp.status_code}): {resp.text}"
            )
        if resp.status_code == 404:
            raise KeyNotFoundError(
                f"Resource not found at {path}: {resp.text}"
            )
        if resp.status_code in (400, 422):
            raise ValidationError(
                f"Validation/Bad Request ({resp.status_code}): {resp.text}"
            )
        if resp.status_code >= 500:
            raise GatewayConnectionError(
                f"Gateway server error ({resp.status_code}): {resp.text}"
            )
        return resp

    def list_keys(
        self, return_full_object: bool = True
    ) -> List[Dict[str, Any]]:
        """List all virtual keys from LiteLLM proxy in a single call.

        Args:
            return_full_object: Whether to fetch full metadata objects.

        Returns:
            List of virtual key summary/metadata dictionaries.
        """
        params = {"return_full_object": "true"} if return_full_object else {}
        resp = self._request("GET", "/key/list", params=params)
        data = resp.json()
        keys = data.get("keys", [])
        return keys if isinstance(keys, list) else []

    def get_key_by_alias(self, alias: str) -> Dict[str, Any]:
        """Fetch full details of a virtual key by its unique alias.

        Args:
            alias: Unique key alias string.

        Returns:
            Dict containing full key metadata.

        Raises:
            KeyNotFoundError: If no key matches the given alias.
        """
        resp = self._request(
            "GET",
            "/key/list",
            params={"key_alias": alias, "return_full_object": "true"},
        )
        data = resp.json()
        keys = data.get("keys", [])
        if not keys:
            raise KeyNotFoundError(f"Key with alias '{alias}' not found.")
        return keys[0]

    def get_key_by_token(self, token: str) -> Dict[str, Any]:
        """Fetch details of a virtual key by its token hash or raw key.

        Args:
            token: SHA-256 token hash or raw secret key.

        Returns:
            Dict containing key metadata.

        Raises:
            KeyNotFoundError: If the token hash is not found.
        """
        resp = self._request("GET", "/key/info", params={"key": token})
        data = resp.json()
        info = data.get("info", data)
        if isinstance(info, dict):
            if "token" not in info:
                info["token"] = data.get("key", token)
            return info
        return {}

    def get_available_models(self) -> List[str]:
        """Retrieve the list of active models deployed on LiteLLM.

        Returns:
            List of model ID strings, or empty list if unavailable.
        """
        try:
            resp = self._request("GET", "/v1/models")
            data = resp.json()
            model_items = data.get("data", [])
            return [
                m["id"]
                for m in model_items
                if isinstance(m, dict) and "id" in m
            ]
        except (VirtualKeyError, KeyError, ValueError):
            return []

    def generate_key(
        self,
        key_alias: str,
        max_budget: Optional[float] = None,
        budget_duration: str = "30d",
        models: Optional[List[str]] = None,
        tpm_limit: Optional[int] = None,
        rpm_limit: Optional[int] = None,
        warn_unknown_models: bool = True,
    ) -> Dict[str, Any]:
        """Generate a new virtual key with budget and rate limits.

        Args:
            key_alias: Unique identifier for the key.
            max_budget: Optional spending limit in USD.
            budget_duration: Reset period (e.g. '30d'). Default '30d'.
            models: List of allowed models. None allows all models.
            tpm_limit: Optional tokens-per-minute limit.
            rpm_limit: Optional requests-per-minute limit.
            warn_unknown_models: Warn if model is missing in /v1/models.

        Returns:
            Dict containing the created key object (including raw secret key).
        """
        if warn_unknown_models and models:
            available = self.get_available_models()
            if available:
                unknown = [m for m in models if m not in available]
                if unknown:
                    logging.warning(
                        "Models not found in gateway /v1/models: %s", unknown
                    )

        payload: Dict[str, Any] = {
            "key_alias": key_alias,
            "budget_duration": budget_duration,
        }
        if max_budget is not None:
            payload["max_budget"] = float(max_budget)
        if models is not None:
            payload["models"] = models
        if tpm_limit is not None:
            payload["tpm_limit"] = int(tpm_limit)
        if rpm_limit is not None:
            payload["rpm_limit"] = int(rpm_limit)

        resp = self._request("POST", "/key/generate", json=payload)
        return resp.json()

    def update_budget(
        self,
        identifier: str,
        max_budget: Optional[float] = None,
        budget_duration: Optional[str] = None,
        is_alias: bool = True,
    ) -> Dict[str, Any]:
        """Update budget ceiling and duration for a virtual key.

        Args:
            identifier: Key alias or token hash.
            max_budget: Optional new budget limit in USD.
            budget_duration: Optional new duration (e.g. '30d').
            is_alias: True if identifier is an alias, False if token hash.

        Returns:
            Dict containing updated key info.
        """
        if is_alias:
            key_obj = self.get_key_by_alias(identifier)
            token = key_obj.get("token")
            if not token:
                raise KeyNotFoundError(
                    f"Token hash not found for alias '{identifier}'"
                )
        else:
            token = identifier

        payload: Dict[str, Any] = {"key": token}
        if max_budget is not None:
            payload["max_budget"] = float(max_budget)
        if budget_duration is not None:
            payload["budget_duration"] = budget_duration

        resp = self._request("POST", "/key/update", json=payload)
        return resp.json()

    def delete_keys(
        self,
        key_aliases: Optional[List[str]] = None,
        tokens: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Revoke virtual keys by plural aliases or tokens.

        Args:
            key_aliases: List of key aliases to delete.
            tokens: List of token hashes to delete.

        Returns:
            Dict containing deletion response.
        """
        payload: Dict[str, Any] = {}
        if key_aliases:
            payload["key_aliases"] = key_aliases
        elif tokens:
            payload["keys"] = tokens
        else:
            raise ValidationError(
                "Must provide either key_aliases or tokens to delete."
            )

        resp = self._request("POST", "/key/delete", json=payload)
        return resp.json()

    def _write_env_file(
        self,
        env_path: Path,
        alias: str,
        budget: float,
        budget_duration: str,
        tailscale_host: str,
        raw_key: str,
    ) -> None:
        """Write a secure .env file with 0600 permissions."""
        gateway_url = normalize_gateway_url(tailscale_host)
        content = (
            f"# Generated by dgx-spark-toolkit manage_virtual_keys.py\n"
            f"# Spoke: {alias} | Budget: ${budget:.2f}/{budget_duration}\n"
            f"OPENAI_API_BASE={gateway_url}\n"
            f"OPENAI_BASE_URL={gateway_url}\n"
            f"OPENAI_API_KEY={raw_key}\n"
            f"LITELLM_VIRTUAL_KEY={raw_key}\n"
            f"CCBA_AI_GATEWAY_URL={gateway_url}\n"
            f"CCBA_AI_API_KEY={raw_key}\n"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(str(env_path), flags, 0o600)
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
        finally:
            os.chmod(str(env_path), stat.S_IRUSR | stat.S_IWUSR)

    def _create_spoke_env(
        self,
        alias: str,
        budget: float,
        duration: str,
        models: Optional[List[str]],
        target_env: Path,
        tailscale_host: str,
    ) -> str:
        """Generate key on gateway and write secure .env file."""
        gen_res = self.generate_key(
            key_alias=alias,
            max_budget=budget,
            budget_duration=duration,
            models=models,
        )
        raw_key = gen_res.get("key")
        if not raw_key:
            raise GatewayConnectionError(
                f"Gateway did not return raw key for '{alias}'"
            )
        self._write_env_file(
            target_env, alias, budget, duration, tailscale_host, raw_key
        )
        return raw_key

    def _provision_single_spoke(
        self,
        spoke: Dict[str, Any],
        existing_map: Dict[str, Any],
        out_path: Path,
        dry_run: bool,
        force: bool,
        tailscale_host: str,
    ) -> Dict[str, Any]:
        """Provision or preview provisioning for an individual spoke."""
        alias, budget = spoke["alias"], float(spoke["budget"])
        duration, models = spoke["budget_duration"], spoke["models"]
        exists = alias in existing_map

        if exists and not force:
            return {
                "alias": alias, "budget": budget, "duration": duration,
                "action": "SKIPPED", "env_file": None,
                "reason": "Already exists (use --force to recreate)",
            }

        action = "RECREATED" if exists else "CREATED"
        target_env = out_path / f".env.{alias}"
        if dry_run:
            return {
                "alias": alias, "budget": budget, "duration": duration,
                "action": f"DRY-RUN ({action})",
                "env_file": str(target_env), "reason": "Dry run mode",
            }

        if exists and force:
            self.delete_keys(key_aliases=[alias])

        raw_key = self._create_spoke_env(
            alias, budget, duration, models, target_env, tailscale_host
        )
        return {
            "alias": alias, "budget": budget, "duration": duration,
            "action": action, "env_file": str(target_env),
            "masked_key": mask_key(raw_key),
        }

    def provision_spokes(
        self,
        output_dir: str = ".md/scratch/spokes_env",
        dry_run: bool = False,
        force: bool = False,
        tailscale_host: str = "100.83.192.30:8090",
    ) -> List[Dict[str, Any]]:
        """Provision standard virtual keys for federated spokes.

        Args:
            output_dir: Output directory for .env files.
            dry_run: Preview actions without modifying database.
            force: Recreate existing keys (delete old then generate).
            tailscale_host: Gateway host and port for spoke connection.

        Returns:
            List of action records per spoke.
        """
        existing_keys = self.list_keys()
        existing_map = {
            k["key_alias"]: k for k in existing_keys if k.get("key_alias")
        }

        out_path = Path(output_dir)
        if not dry_run:
            out_path.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(str(out_path), stat.S_IRWXU)
            except OSError:
                pass

        return [
            self._provision_single_spoke(
                spoke=spoke,
                existing_map=existing_map,
                out_path=out_path,
                dry_run=dry_run,
                force=force,
                tailscale_host=tailscale_host,
            )
            for spoke in STANDARD_SPOKES
        ]


# --- Formatting Helpers ---
def format_table(
    headers: List[str],
    rows: List[List[str]],
    alignments: Optional[List[str]] = None,
) -> str:
    """Render a clean ASCII table with column padding.

    Args:
        headers: List of column header names.
        rows: List of row cell strings.
        alignments: Optional alignment per column ('<' or '>').

    Returns:
        Formatted ASCII table string.
    """
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))

    align = alignments or ["<"] * len(headers)
    sep_line = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    lines = [sep_line]
    h_cells = [
        f" {headers[i]:{align[i]}{col_widths[i]}} "
        for i in range(len(headers))
    ]
    lines.append("|" + "|".join(h_cells) + "|")
    lines.append(sep_line)

    for row in rows:
        r_cells = [
            f" {row[i]:{align[i]}{col_widths[i]}} "
            if i < len(row)
            else f" {'':{align[i]}{col_widths[i]}} "
            for i in range(len(headers))
        ]
        lines.append("|" + "|".join(r_cells) + "|")

    lines.append(sep_line)
    return "\n".join(lines)


# --- CLI Command Handlers ---
def handle_list(manager: VirtualKeyManager, args: argparse.Namespace) -> int:
    """Handle virtual keys list command."""
    keys = manager.list_keys(return_full_object=True)
    if args.json:
        print(json.dumps(keys, indent=2))
        return 0

    headers = [
        "Key Alias",
        "Masked Key",
        "Spend / Budget",
        "Duration",
        "Models",
        "Status",
    ]
    rows = []
    sorted_keys = sorted(
        keys,
        key=lambda k: (k.get("key_alias") or "", k.get("token") or ""),
    )
    for k in sorted_keys:
        alias = k.get("key_alias") or "(no-alias)"
        masked = mask_key(k.get("key_name"))
        spend = float(k.get("spend") or 0.0)
        max_b = k.get("max_budget")
        if max_b is not None:
            budget_str = f"${spend:.2f} / ${max_b:.2f}"
        else:
            budget_str = f"${spend:.2f} / Unlimited"
        dur = k.get("budget_duration") or "N/A"
        models = k.get("models")
        if not models:
            models_str = "all"
        elif len(models) <= 2:
            models_str = ",".join(models)
        else:
            models_str = f"{len(models)} models"
        status = "Blocked" if k.get("blocked") else "Active"
        rows.append([alias, masked, budget_str, dur, models_str, status])

    print(format_table(headers, rows))
    return 0


def handle_generate(
    manager: VirtualKeyManager, args: argparse.Namespace
) -> int:
    """Handle virtual key generate command."""
    models = None
    if args.models:
        models = [m.strip() for m in args.models.split(",")]
    res = manager.generate_key(
        key_alias=args.alias,
        max_budget=args.budget,
        budget_duration=args.budget_duration,
        models=models,
        tpm_limit=args.tpm,
        rpm_limit=args.rpm,
    )
    raw_key = res.get("key") or "N/A"
    print("\n✅ Virtual Key Generated Successfully!")
    print(f"Alias:           {res.get('key_alias')}")
    print(f"Raw Key:         {raw_key}")
    print(f"Masked Key:      {mask_key(res.get('key_name') or raw_key)}")
    max_b = res.get("max_budget")
    if max_b is not None:
        print(f"Max Budget:      ${max_b:.2f}")
    else:
        print("Max Budget:      Unlimited")
    print(f"Budget Duration: {res.get('budget_duration') or 'N/A'}")
    print(f"Allowed Models:  {res.get('models') or 'all'}")
    print("\n⚠️ WARNING: The raw key is only shown once! Save it securely.\n")
    return 0


def _resolve_target(
    args: argparse.Namespace,
) -> Tuple[Optional[str], bool]:
    """Determine target identifier and whether it is an alias.

    Args:
        args: Parsed CLI namespace.

    Returns:
        Tuple of (target_string, is_alias_boolean).

    Raises:
        ValidationError: If both --alias and --key are specified.
    """
    has_key = getattr(args, "key", None)
    has_alias = getattr(args, "alias", None)
    if has_key and has_alias:
        raise ValidationError(
            "Cannot specify both --alias and --key. Choose one."
        )
    if has_key:
        return args.key, False
    if has_alias:
        return args.alias, True

    ident = getattr(args, "identifier", None)
    if not ident:
        return None, True
    if ident.startswith("sk-"):
        return ident, False
    if len(ident) == 64 and all(c in "0123456789abcdefABCDEF" for c in ident):
        return ident, False
    return ident, True


def handle_info(manager: VirtualKeyManager, args: argparse.Namespace) -> int:
    """Handle virtual key info command."""
    target, is_alias = _resolve_target(args)
    if not target:
        raise ValidationError("Please provide a key alias or token hash.")

    if is_alias:
        info = manager.get_key_by_alias(target)
    else:
        info = manager.get_key_by_token(target)

    if args.json:
        print(json.dumps(info, indent=2))
        return 0

    print("\nVirtual Key Information:")
    for field in [
        "key_alias",
        "key_name",
        "token",
        "spend",
        "max_budget",
        "budget_duration",
        "budget_reset_at",
        "models",
        "tpm_limit",
        "rpm_limit",
        "blocked",
        "created_at",
    ]:
        val = info.get(field)
        print(f"  {field:<18}: {val}")
    print()
    return 0


def handle_update_budget(
    manager: VirtualKeyManager, args: argparse.Namespace
) -> int:
    """Handle update-budget command."""
    target, is_alias = _resolve_target(args)
    if not target:
        raise ValidationError("Please provide a key alias or token hash.")
    if args.budget is None and args.budget_duration is None:
        raise ValidationError(
            "Must provide at least one of --budget or --budget-duration."
        )

    res = manager.update_budget(
        target,
        max_budget=args.budget,
        budget_duration=args.budget_duration,
        is_alias=is_alias,
    )
    print(f"\n✅ Budget updated successfully for '{target}':")
    print(f"  Max Budget:      ${res.get('max_budget')}")
    print(f"  Budget Duration: {res.get('budget_duration')}")
    print(f"  Reset At:        {res.get('budget_reset_at')}\n")
    return 0


def handle_revoke(manager: VirtualKeyManager, args: argparse.Namespace) -> int:
    """Handle revoke/delete command."""
    target, is_alias = _resolve_target(args)
    if not target:
        raise ValidationError(
            "Please provide a key alias or token hash to revoke."
        )

    if is_alias:
        manager.delete_keys(key_aliases=[target])
    else:
        manager.delete_keys(tokens=[target])

    print(f"\n✅ Successfully revoked virtual key: {target}\n")
    return 0


def handle_provision_spokes(
    manager: VirtualKeyManager, args: argparse.Namespace
) -> int:
    """Handle provision-spokes command."""
    results = manager.provision_spokes(
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        force=args.force,
        tailscale_host=args.tailscale_host,
    )
    headers = [
        "Spoke Alias", "Budget", "Duration", "Action", "Env File / Note"
    ]
    rows = []
    for r in results:
        rows.append(
            [
                r["alias"],
                f"${r['budget']:.1f}",
                r["duration"],
                r["action"],
                r.get("env_file") or r.get("reason", ""),
            ]
        )
    print("\nSpoke Provisioning Summary:")
    print(format_table(headers, rows))
    print()
    return 0


# --- Parser Builder ---
def _add_list_subparser(subparsers: Any) -> None:
    p = subparsers.add_parser("list", help="List all virtual keys")
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _add_generate_subparser(subparsers: Any) -> None:
    p = subparsers.add_parser("generate", help="Generate virtual key")
    p.add_argument("--alias", required=True, help="Unique key alias")
    p.add_argument(
        "--budget", type=float, default=None, help="Budget limit ($)"
    )
    p.add_argument(
        "--budget-duration",
        default="30d",
        help="Budget reset duration (default: 30d)",
    )
    p.add_argument(
        "--models", default=None, help="Comma-separated model names"
    )
    p.add_argument(
        "--tpm", type=int, default=None, help="Tokens/min limit"
    )
    p.add_argument(
        "--rpm", type=int, default=None, help="Requests/min limit"
    )


def _add_info_subparser(subparsers: Any) -> None:
    p = subparsers.add_parser("info", help="Get key details")
    p.add_argument(
        "identifier", nargs="?", default=None, help="Key alias or token hash"
    )
    p.add_argument("--alias", default=None, help="Lookup by alias")
    p.add_argument("--key", default=None, help="Lookup by token hash")
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _add_update_budget_subparser(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "update-budget", help="Update budget or duration"
    )
    p.add_argument(
        "identifier", nargs="?", default=None, help="Key alias or token hash"
    )
    p.add_argument("--alias", default=None, help="Target alias")
    p.add_argument("--key", default=None, help="Target token hash")
    p.add_argument(
        "--budget", type=float, default=None, help="New budget ($)"
    )
    p.add_argument(
        "--budget-duration", default=None, help="New duration (e.g. 30d)"
    )


def _add_revoke_subparser(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "revoke", aliases=["delete"], help="Revoke/delete virtual key"
    )
    p.add_argument(
        "identifier", nargs="?", default=None, help="Key alias or token hash"
    )
    p.add_argument("--alias", default=None, help="Target alias")
    p.add_argument("--key", default=None, help="Target token hash")


def _add_provision_spokes_subparser(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "provision-spokes", help="Provision standard keys for spokes"
    )
    p.add_argument(
        "--output-dir",
        default=".md/scratch/spokes_env",
        help="Directory to write spoke .env files",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview provisioning without mutating DB or files",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Recreate keys if they already exist",
    )
    p.add_argument(
        "--tailscale-host",
        default="100.83.192.30:8090",
        help="Tailscale gateway host:port (default: 100.83.192.30:8090)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Construct command line interface parser."""
    parser = argparse.ArgumentParser(
        description="LiteLLM Gateway Virtual Key Manager & Spoke Provisioner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url",
        default=None,
        help="LiteLLM proxy base URL (default: LITELLM_URL or :8090)",
    )
    parser.add_argument(
        "--master-key",
        default=None,
        help="LiteLLM master key (default: LITELLM_MASTER_KEY from env)",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    _add_list_subparser(subparsers)
    _add_generate_subparser(subparsers)
    _add_info_subparser(subparsers)
    _add_update_budget_subparser(subparsers)
    _add_revoke_subparser(subparsers)
    _add_provision_spokes_subparser(subparsers)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point.

    Args:
        argv: Command-line arguments list (defaults to sys.argv[1:]).

    Returns:
        Process exit code integer.
    """
    load_project_env()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        manager = VirtualKeyManager(
            base_url=args.url, master_key=args.master_key
        )
        if args.subcommand == "list":
            return handle_list(manager, args)
        if args.subcommand == "generate":
            return handle_generate(manager, args)
        if args.subcommand == "info":
            return handle_info(manager, args)
        if args.subcommand == "update-budget":
            return handle_update_budget(manager, args)
        if args.subcommand in ("revoke", "delete"):
            return handle_revoke(manager, args)
        if args.subcommand == "provision-spokes":
            return handle_provision_spokes(manager, args)
        return 0
    except VirtualKeyError as err:
        logging.error("%s", err)
        print(f"❌ Error [{err.__class__.__name__}]: {err}", file=sys.stderr)
        return err.exit_code
    except Exception as exc:  # pylint: disable=broad-except
        logging.exception("Unexpected error: %s", exc)
        print(f"❌ Unexpected Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s: %(message)s"
    )
    sys.exit(main())
