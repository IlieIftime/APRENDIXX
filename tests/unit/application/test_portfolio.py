import json
import zipfile

from aprendix.bootstrap import build_runtime


def test_every_track_has_capstone_and_portfolio_distinguishes_mode(tmp_path) -> None:
    runtime = build_runtime(tmp_path / "profile")
    templates = runtime.portfolio.templates()
    assert len(runtime.curriculum.tracks()) == 12
    assert len(templates) == 20
    assert sum(item.capstone for item in templates) >= 8
    capstone_tracks = {item.track_slug for item in templates if item.capstone}
    assert capstone_tracks == {item["slug"] for item in runtime.curriculum.tracks()}
    project = runtime.portfolio.start(templates[0].id, mode="autonomous")
    context = runtime.portfolio.context(project.id)
    assert context["template"].id == templates[0].id
    assert context["template"].track_slug == templates[0].track_slug
    assert context["work_mode"] == "autonomous"
    runtime.portfolio.set_milestone(project.id, 0)
    entry = runtime.portfolio.entries()[0]
    assert entry.work_mode == "autonomous"
    with runtime.database.read_connection() as connection:
        assert connection.execute(
            "SELECT completed FROM project_milestone_state WHERE project_id=? AND ordinal=0",
            (str(project.id),),
        ).fetchone()[0] == 1


def test_project_evaluation_and_explicit_export_exclude_private_data(tmp_path) -> None:
    runtime = build_runtime(tmp_path / "profile")
    template = runtime.portfolio.templates()[0]
    project = runtime.portfolio.start(template.id)
    runtime.desktop.save_project(
        project.name,
        '"""Projeto documentado."""\n\ndef soma(a, b):\n    return a+b\n\ndef main():\n    assert soma(2, 3) == 5\n\nmain()\n',
        project.id,
    )
    evaluation = runtime.portfolio.evaluate(project.id)
    assert evaluation.score >= .7 and evaluation.passed
    target = runtime.portfolio.export_zip(project.id, tmp_path / "portfolio.zip")
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist()) == {"main.py", "APRENDIX-PORTFOLIO.json"}
        report = json.loads(archive.read("APRENDIX-PORTFOLIO.json"))
        payload = b"".join(archive.read(name) for name in archive.namelist())
    assert report["status"] == "passed"
    assert b"fields.key" not in payload and b"aprendix.db" not in payload
