from scripts.audit_iteration21 import audit


def test_iteration21_desktop_audit_is_green_aggregate_and_mobile_frozen(tmp_path) -> None:
    report = audit(tmp_path / "iteration21")

    assert report["passed"] is True
    assert report["platform_scope"] == "Windows desktop only; mobile subtree frozen"
    assert all(item["passed"] for item in report["checks"].values())
    assert report["privacy"] == {
        "aggregate_only": True,
        "temporary_profile": True,
        "contains_user_content": False,
        "contains_user_identifiers": False,
        "contains_paths": False,
    }
    assert report["metrics"]["schema_version"] == 38
    assert report["metrics"]["catalog_delta"] == {
        "source": 500,
        "card": 1_000,
        "glossary": 1_000,
        "exercise": 500,
        "project": 50,
    }
    assert report["metrics"]["authored_card_aggregate_readings"] == 0
    assert report["metrics"]["career"]["roles"] == 5
    assert report["metrics"]["career_dag_cycles"] == 0
    assert report["metrics"]["sandbox_validated_reference_solutions"] == 500
    assert report["metrics"]["search_holdout_queries"] >= 250
    assert report["metrics"]["analyzer_golden_passes"] == 50
    assert report["metrics"]["analyzer_execution_boundary_calls"] == 0
    assert report["metrics"]["math_render_snapshots"] == 18
    assert "android_touch" not in report["external_release_gates"]
