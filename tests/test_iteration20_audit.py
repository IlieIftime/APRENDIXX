from scripts.audit_iteration20 import audit


def test_iteration20_desktop_audit_is_green_aggregate_and_mobile_frozen(tmp_path) -> None:
    report = audit(tmp_path / "iteration20")

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
    assert report["metrics"]["learning_units"] == 248
    assert report["metrics"]["viewable_units"] == 248
    assert report["metrics"]["search_holdout_queries"] >= 100
    assert report["metrics"]["visible_graph_nodes"] <= 150
    assert report["metrics"]["visible_graph_edges"] <= 300
    assert "android_touch" not in report["external_release_gates"]
