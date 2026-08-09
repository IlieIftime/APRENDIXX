from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_audit_module():
    path = ROOT / "scripts" / "audit_aaa.py"
    spec = importlib.util.spec_from_file_location("audit_aaa", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aaa_audit_is_aggregate_and_does_not_false_pass(tmp_path):
    report = _load_audit_module().audit(tmp_path / "profile")

    assert report["database"]["integrity"] == "ok"
    assert report["privacy"] == {
        "aggregate_only": True,
        "contains_user_content": False,
        "contains_user_identifiers": False,
        "contains_paths": False,
    }
    assert report["counts"]["learning_tracks"] >= 12
    assert report["counts"]["learning_units"] >= 150
    assert report["curriculum"]["status"] == "open"
    assert report["curriculum"]["targets"]["authored_cards"]["passed"] is False
    assert report["curriculum"]["targets"]["glossary_entries"]["passed"] is False
