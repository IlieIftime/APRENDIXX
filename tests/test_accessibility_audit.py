from scripts.audit_accessibility import audit


def test_accessibility_audit_covers_all_release_dpi_profiles() -> None:
    report = audit()
    assert report["passed"] is True
    assert [item["scale_percent"] for item in report["dpi_profiles"]] == [
        100, 125, 150, 175, 200,
    ]
    assert all(item["minimum_touch_target_px"] >= 44 for item in report["dpi_profiles"])
    assert report["manual_gates"]["physical_touch"].startswith("requires-")
