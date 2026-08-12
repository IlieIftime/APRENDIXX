from scripts.audit_iteration13 import audit


def test_iteration13_end_to_end_audit_is_green_and_private(tmp_path) -> None:
    report = audit(tmp_path / "iteration13")
    assert report["passed"] is True
    assert all(item["passed"] for item in report["journeys"].values())
    assert report["privacy"] == {
        "aggregate_only": True,
        "contains_user_content": False,
        "contains_user_identifiers": False,
        "contains_paths": False,
    }
    assert report["journeys"]["pedagogical_compiler"]["passed"] is True
    assert report["journeys"]["bibliography"]["passed"] is True
    assert report["journeys"]["mobile_parity"]["passed"] is True
