"""P6 config — localhost-only, validated, fail-closed."""
import os
import tempfile
from pathlib import Path
import pytest
from p5.config import load_config, is_within_workspace_root

def test_valid_localhost_accepted():
    cfg = load_config(cli_host="127.0.0.1", cli_port=8765)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765
    cfg2 = load_config(cli_host="localhost")
    assert cfg2.host == "localhost"

def test_reject_0_0_0_0():
    with pytest.raises(ValueError, match="loopback"):
        load_config(cli_host="0.0.0.0")

def test_reject_non_loopback():
    for bad in ["10.0.0.1", "192.168.1.1", "example.com", "::1"]:
        with pytest.raises(ValueError):
            load_config(cli_host=bad)

def test_invalid_port_rejected():
    for bad in ["abc", "0", "99999", "-1", ""]:
        with pytest.raises(ValueError):
            load_config(cli_port=bad)

def test_invalid_max_body_rejected():
    for bad in ["abc", "0", "-1", "99999999"]:
        with pytest.raises(ValueError):
            load_config(cli_max_body=bad)
    cfg = load_config(cli_max_body=1024)
    assert cfg.max_body == 1024

def test_workspace_root_safe():
    with tempfile.TemporaryDirectory() as td:
        cfg = load_config(cli_workspace_root=td)
        assert cfg.workspace_root_resolved == Path(td).resolve()
        # within check
        sub = Path(td) / "sub" / "ws"
        assert is_within_workspace_root(sub, cfg.workspace_root_resolved) or not sub.exists()  # before mkdir, but after resolve check
        sub.mkdir(parents=True)
        assert is_within_workspace_root(sub, cfg.workspace_root_resolved) is True
        # outside
        other = Path(tempfile.gettempdir()) / "outside_p6_test"
        # Ensure other is not within td (unless td is tempdir itself)
        if Path(td).resolve() != Path(tempfile.gettempdir()).resolve():
            assert is_within_workspace_root(other, cfg.workspace_root_resolved) is False

def test_cli_overrides_env():
    os.environ["P5_PORT"] = "9999"
    try:
        cfg = load_config(cli_port=8888)
        assert cfg.port == 8888
        # env without CLI
        cfg2 = load_config()
        assert cfg2.port == 9999
    finally:
        os.environ.pop("P5_PORT", None)

def test_token_length_validation():
    with pytest.raises(ValueError, match="at least 8"):
        load_config(cli_token="short")
    cfg = load_config(cli_token="valid-token-12345678")
    assert cfg.local_token == "valid-token-12345678"
    cfg2 = load_config(cli_token=None)
    assert cfg2.local_token is None
