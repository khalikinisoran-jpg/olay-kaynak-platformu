"""UTF-8 BOM tolerance for the generic proposal contract.

Windows PowerShell prepends a UTF-8 BOM when piping JSON to the CLI;
the canonical `tanuq propose --stdin-json` entry must accept it.
"""
import io
import json

from tanuq import agent_adapter, cli
from tanuq.config import init_workspace, tanuq_data_dir
from tanuq.runtime import load_environment


def test_parse_payload_accepts_bom_prefixed_json():
    obj = {"path": "a.txt", "old_content": "x", "new_content": "y"}
    parsed = agent_adapter.parse_payload("\ufeff" + json.dumps(obj))
    assert parsed == [obj]


def test_parse_payload_accepts_bom_prefixed_array():
    obj = {"path": "a.txt", "old_content": "x", "new_content": "y"}
    parsed = agent_adapter.parse_payload("\ufeff" + json.dumps([obj]))
    assert parsed == [obj]


def test_parse_payload_without_bom_unchanged():
    obj = {"path": "a.txt", "old_content": "x", "new_content": "y"}
    parsed = agent_adapter.parse_payload(json.dumps(obj))
    assert parsed == [obj]


class _StdinWithBuffer:
    def __init__(self, data: bytes):
        self.buffer = io.BytesIO(data)


def test_cli_stdin_json_with_utf8_bom_full_governed_flow(
        tmp_path, monkeypatch, capsys):
    """End-to-end: BOM-prefixed stdin JSON through the real governed
    pipeline reaches PROPOSED and executes to VERIFIED."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    assert cli.main(["init", "--workspace", str(ws), "--yes"]) == 0
    capsys.readouterr()

    payload = json.dumps({
        "path": str(ws / "demo.txt"),
        "action": "modify",
        "reason": "bom regression",
        "old_content": "hello",
        "new_content": "hello with bom tolerance",
    })
    monkeypatch.setattr(
        "sys.stdin",
        type("S", (), {"buffer": io.BytesIO(b"\xef\xbb\xbf" +
                                        payload.encode("utf-8"))})())
    assert cli.main(["propose", "--workspace", str(ws),
                     "--stdin-json", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["proposals"][0]["state"] == "PROPOSED"
    fingerprint = report["proposals"][0]["fingerprint"]

    assert cli.main(["execute", "--workspace", str(ws),
                     "--fingerprint", fingerprint]) == 0
    out = capsys.readouterr().out
    assert "terminal state: VERIFIED" in out
    assert (ws / "demo.txt").read_text(
        encoding="utf-8") == "hello with bom tolerance"
