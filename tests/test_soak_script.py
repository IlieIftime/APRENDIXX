from scripts.benchmark_soak import run


def test_bounded_soak_report_is_private_and_healthy(tmp_path) -> None:
    report = run(tmp_path / "soak.json", cycles=3)
    assert report["passed"] is True
    assert report["database_integrity"] == "ok"
    assert report["failure_count"] == 0
    assert report["profile"] == "fresh-temporary-no-user-data"
