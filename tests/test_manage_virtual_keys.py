"""Unit tests for LiteLLM virtual key manager and spoke provisioner."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.manage_virtual_keys import (
    GatewayConnectionError,
    KeyNotFoundError,
    MasterKeyError,
    STANDARD_SPOKES,
    ValidationError,
    VirtualKeyManager,
    main,
    mask_key,
    normalize_gateway_url,
)


@pytest.fixture
def mock_manager() -> VirtualKeyManager:
    """Fixture providing a VirtualKeyManager with dummy master key."""
    return VirtualKeyManager(
        base_url="http://localhost:8090",
        master_key="sk-test-master-key",
    )


def test_list_keys_full_object(mock_manager: VirtualKeyManager) -> None:
    """Verify list_keys calls /key/list?return_full_object=true."""
    fake_keys = [
        {
            "token": "tok1",
            "key_alias": "spoke-bim-planner",
            "key_name": "sk-...1234",
            "spend": 5.0,
            "max_budget": 50.0,
        },
        {
            "token": "tok2",
            "key_alias": "spoke-idop",
            "key_name": "sk-...5678",
            "spend": 0.0,
            "max_budget": 30.0,
        },
    ]
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"keys": fake_keys}

    with patch.object(mock_manager.session, "request", return_value=mock_resp):
        keys = mock_manager.list_keys(return_full_object=True)

    assert len(keys) == 2
    assert keys[0]["key_alias"] == "spoke-bim-planner"
    assert keys[1]["key_alias"] == "spoke-idop"


def test_generate_key_success(mock_manager: VirtualKeyManager) -> None:
    """Verify generate_key payload includes budget_duration and models."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "key": "sk-secret-abc-123",
        "key_name": "sk-..._123",
        "key_alias": "spoke-bim-planner",
        "max_budget": 50.0,
        "budget_duration": "30d",
        "models": ["qwen-3.5-35b", "embedding-default"],
    }

    with patch.object(
        mock_manager.session, "request", return_value=mock_resp
    ) as mock_req:
        res = mock_manager.generate_key(
            key_alias="spoke-bim-planner",
            max_budget=50.0,
            budget_duration="30d",
            models=["qwen-3.5-35b", "embedding-default"],
            tpm_limit=50000,
            rpm_limit=120,
            warn_unknown_models=False,
        )

    mock_req.assert_called_once()
    _, kwargs = mock_req.call_args
    sent_payload = kwargs.get("json", {})
    assert sent_payload["key_alias"] == "spoke-bim-planner"
    assert sent_payload["max_budget"] == 50.0
    assert sent_payload["budget_duration"] == "30d"
    assert sent_payload["models"] == ["qwen-3.5-35b", "embedding-default"]
    assert sent_payload["tpm_limit"] == 50000
    assert sent_payload["rpm_limit"] == 120
    assert res["key"] == "sk-secret-abc-123"


def test_generate_key_duplicate_alias_error(
    mock_manager: VirtualKeyManager,
) -> None:
    """Verify duplicate alias raises ValidationError and CLI exits with 3."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 400
    mock_resp.text = (
        '{"error":{"message":"Key with alias \'spoke-bim-planner\' already '
        'exists. Unique key aliases across all keys are required."}}'
    )

    with patch.object(mock_manager.session, "request", return_value=mock_resp):
        with pytest.raises(ValidationError):
            mock_manager.generate_key(
                key_alias="spoke-bim-planner",
                warn_unknown_models=False,
            )

    # Test CLI exit code 3
    with patch(
        "scripts.manage_virtual_keys.VirtualKeyManager",
        return_value=mock_manager,
    ), patch.object(mock_manager.session, "request", return_value=mock_resp):
        code = main(["generate", "--alias", "spoke-bim-planner"])
        assert code == 3


def test_info_by_alias_success_and_not_found(
    mock_manager: VirtualKeyManager,
) -> None:
    """Verify info by alias returns object when found and raises 404/exit 2."""
    found_resp = MagicMock(spec=requests.Response)
    found_resp.status_code = 200
    found_resp.json.return_value = {
        "keys": [{"key_alias": "spoke-idop", "token": "hash-idop"}]
    }

    with patch.object(
        mock_manager.session, "request", return_value=found_resp
    ):
        info = mock_manager.get_key_by_alias("spoke-idop")
        assert info["key_alias"] == "spoke-idop"
        assert info["token"] == "hash-idop"

    empty_resp = MagicMock(spec=requests.Response)
    empty_resp.status_code = 200
    empty_resp.json.return_value = {"keys": []}

    with patch.object(
        mock_manager.session, "request", return_value=empty_resp
    ):
        with pytest.raises(KeyNotFoundError):
            mock_manager.get_key_by_alias("nonexistent-alias")

    # Verify CLI exits with code 2 on missing alias
    with patch(
        "scripts.manage_virtual_keys.VirtualKeyManager",
        return_value=mock_manager,
    ):
        with patch.object(
            mock_manager.session, "request", return_value=empty_resp
        ):
            code = main(["info", "--alias", "nonexistent-alias"])
            assert code == 2


def test_update_budget_resolves_alias_to_token(
    mock_manager: VirtualKeyManager,
) -> None:
    """Verify update_budget resolves alias before calling /key/update."""
    lookup_resp = MagicMock(spec=requests.Response)
    lookup_resp.status_code = 200
    lookup_resp.json.return_value = {
        "keys": [{"key_alias": "spoke-legal", "token": "token-hash-legal"}]
    }

    update_resp = MagicMock(spec=requests.Response)
    update_resp.status_code = 200
    update_resp.json.return_value = {
        "key": "token-hash-legal",
        "max_budget": 45.0,
        "budget_duration": "60d",
    }

    with patch.object(
        mock_manager.session,
        "request",
        side_effect=[lookup_resp, update_resp],
    ) as mock_req:
        res = mock_manager.update_budget(
            "spoke-legal",
            max_budget=45.0,
            budget_duration="60d",
            is_alias=True,
        )

    assert mock_req.call_count == 2
    # Check that second request was POST /key/update with token hash
    second_call_url = mock_req.call_args_list[1][0][1]
    second_call_kwargs = mock_req.call_args_list[1][1]
    assert second_call_url.endswith("/key/update")
    assert second_call_kwargs["json"]["key"] == "token-hash-legal"
    assert second_call_kwargs["json"]["max_budget"] == 45.0
    assert second_call_kwargs["json"]["budget_duration"] == "60d"
    assert res["max_budget"] == 45.0


def test_delete_key_plural_payload(mock_manager: VirtualKeyManager) -> None:
    """Verify delete_keys sends plural arrays for key_aliases and keys."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"deleted_keys": ["spoke-legal"]}

    with patch.object(
        mock_manager.session, "request", return_value=mock_resp
    ) as mock_req:
        mock_manager.delete_keys(key_aliases=["spoke-legal"])
        _, kwargs_alias = mock_req.call_args
        assert kwargs_alias["json"] == {"key_aliases": ["spoke-legal"]}

        mock_manager.delete_keys(tokens=["token-hash-123"])
        _, kwargs_token = mock_req.call_args
        assert kwargs_token["json"] == {"keys": ["token-hash-123"]}


def test_provision_spokes_idempotent_skip(
    mock_manager: VirtualKeyManager, tmp_path: Path
) -> None:
    """Verify provision_spokes skips existing keys idempotently."""
    existing_keys = [
        {"key_alias": spoke["alias"], "token": f"hash-{spoke['alias']}"}
        for spoke in STANDARD_SPOKES
    ]

    with patch.object(
        mock_manager, "list_keys", return_value=existing_keys
    ), patch.object(mock_manager, "generate_key") as mock_gen:
        results = mock_manager.provision_spokes(
            output_dir=str(tmp_path), dry_run=False, force=False
        )

    assert len(results) == len(STANDARD_SPOKES)
    for r in results:
        assert r["action"] == "SKIPPED"
        assert r["env_file"] is None
    mock_gen.assert_not_called()


def test_provision_spokes_force_recreate(
    mock_manager: VirtualKeyManager, tmp_path: Path
) -> None:
    """Verify provision_spokes --force deletes old key before recreating."""
    existing_keys = [
        {"key_alias": "spoke-bim-planner", "token": "hash-bim"}
    ]

    fake_gen_res = {
        "key": "sk-new-recreated-key",
        "key_name": "sk-..._key",
        "key_alias": "spoke-bim-planner",
    }

    with patch.object(
        mock_manager, "list_keys", return_value=existing_keys
    ), patch.object(
        mock_manager, "delete_keys"
    ) as mock_del, patch.object(
        mock_manager, "generate_key", return_value=fake_gen_res
    ) as mock_gen:
        results = mock_manager.provision_spokes(
            output_dir=str(tmp_path), dry_run=False, force=True
        )

    # spoke-bim-planner should be deleted first then generated
    mock_del.assert_any_call(key_aliases=["spoke-bim-planner"])
    assert mock_gen.call_count == len(STANDARD_SPOKES)
    bim_record = next(r for r in results if r["alias"] == "spoke-bim-planner")
    assert bim_record["action"] == "RECREATED"


def test_env_file_generation_permissions(
    mock_manager: VirtualKeyManager, tmp_path: Path
) -> None:
    """Verify generated .env files have 0600 permissions and proper keys."""
    fake_gen_res = {
        "key": "sk-secret-spoke-token-999",
        "key_name": "sk-..._999",
        "key_alias": "spoke-bim-planner",
    }

    with patch.object(
        mock_manager, "list_keys", return_value=[]
    ), patch.object(
        mock_manager, "generate_key", return_value=fake_gen_res
    ):
        results = mock_manager.provision_spokes(
            output_dir=str(tmp_path), dry_run=False, force=False
        )

    assert len(results) == len(STANDARD_SPOKES)
    for r in results:
        env_file_path = Path(r["env_file"])
        assert env_file_path.is_file()

        # Check permissions: 0o600 (-rw-------)
        file_mode = stat.S_IMODE(os.stat(env_file_path).st_mode)
        assert file_mode == 0o600

        content = env_file_path.read_text(encoding="utf-8")
        assert "OPENAI_API_KEY=sk-secret-spoke-token-999" in content
        assert "LITELLM_VIRTUAL_KEY=sk-secret-spoke-token-999" in content
        assert "CCBA_AI_GATEWAY_URL=http://127.0.0.1:8090/v1" in content


def test_missing_master_key_fails_safely() -> None:
    """Verify missing master key raises MasterKeyError and CLI exits with 1."""
    with patch.dict(os.environ, {}, clear=True), patch(
        "scripts.manage_virtual_keys.load_project_env"
    ):
        with pytest.raises(MasterKeyError):
            VirtualKeyManager(master_key=None)

        code = main(["list"])
        assert code == 1


def test_mask_key_formatting() -> None:
    """Verify mask_key safely masks secrets and handles edge cases."""
    assert mask_key("") == "N/A"
    assert mask_key("sk-...mEcA") == "sk-...mEcA"
    assert mask_key("short") == "sk-...XXXX"
    assert mask_key("sk-66yFFNdgbogzhIwcRI_q3Q") == "sk-66..._q3Q"


def test_normalize_gateway_url() -> None:
    """Verify normalize_gateway_url formats hosts correctly."""
    assert (
        normalize_gateway_url("100.83.192.30:8090")
        == "http://100.83.192.30:8090/v1"
    )
    assert (
        normalize_gateway_url("http://100.83.192.30:8090")
        == "http://100.83.192.30:8090/v1"
    )
    assert (
        normalize_gateway_url("https://gateway.internal/v1")
        == "https://gateway.internal/v1"
    )
    assert (
        normalize_gateway_url("https://gateway.internal/v1/")
        == "https://gateway.internal/v1"
    )


def test_info_by_token_and_raw_key(mock_manager: VirtualKeyManager) -> None:
    """Verify info by token populates token field and supports raw sk-."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "key": "hash123",
        "info": {"key_name": "sk-...123", "key_alias": "dev-tta"},
    }

    with patch.object(mock_manager.session, "request", return_value=mock_resp):
        info = mock_manager.get_key_by_token("hash123")
        assert info["token"] == "hash123"
        assert info["key_alias"] == "dev-tta"

    # Test CLI resolving positional raw sk- key
    with patch(
        "scripts.manage_virtual_keys.VirtualKeyManager",
        return_value=mock_manager,
    ), patch.object(mock_manager.session, "request", return_value=mock_resp):
        code = main(["info", "sk-secret-key-123"])
        assert code == 0


def test_resolve_target_mutual_exclusion(
    mock_manager: VirtualKeyManager,
) -> None:
    """Verify specifying both --alias and --key raises ValidationError."""
    with patch(
        "scripts.manage_virtual_keys.VirtualKeyManager",
        return_value=mock_manager,
    ):
        code = main(["info", "--alias", "spoke-idop", "--key", "hash123"])
        assert code == 3


def test_gateway_connection_error_code_4(
    mock_manager: VirtualKeyManager,
) -> None:
    """Verify gateway connection failure raises error and exits with 4."""
    with patch.object(
        mock_manager.session,
        "request",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        with pytest.raises(GatewayConnectionError):
            mock_manager.list_keys()

    with patch(
        "scripts.manage_virtual_keys.VirtualKeyManager",
        return_value=mock_manager,
    ), patch.object(
        mock_manager.session,
        "request",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        code = main(["list"])
        assert code == 4


def test_warn_unknown_models_in_generate(
    mock_manager: VirtualKeyManager,
) -> None:
    """Verify warning when generating key with models missing in /v1/models."""
    models_resp = MagicMock(spec=requests.Response)
    models_resp.status_code = 200
    models_resp.json.return_value = {
        "data": [{"id": "model-a"}, {"id": "model-b"}]
    }

    gen_resp = MagicMock(spec=requests.Response)
    gen_resp.status_code = 200
    gen_resp.json.return_value = {
        "key": "sk-test",
        "key_alias": "test-alias",
        "models": ["model-a", "nonexistent-model"],
    }

    with patch.object(
        mock_manager.session,
        "request",
        side_effect=[models_resp, gen_resp],
    ), patch("logging.warning") as mock_warn:
        mock_manager.generate_key(
            key_alias="test-alias",
            models=["model-a", "nonexistent-model"],
            warn_unknown_models=True,
        )
        mock_warn.assert_called_once()
        assert "nonexistent-model" in str(mock_warn.call_args)
