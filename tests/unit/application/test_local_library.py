from pathlib import Path

from aprendix.application.knowledge_structure import LOCAL_LIBRARY_SOURCES
from aprendix.application.local_library import resolve_library_uri


def test_approved_library_catalog_is_metadata_only_and_substantial() -> None:
    assert len(LOCAL_LIBRARY_SOURCES) >= 150
    assert all(source.url.startswith("aprendix-library://") for source in LOCAL_LIBRARY_SOURCES)
    assert all("copiar o texto integral" in source.overview for source in LOCAL_LIBRARY_SOURCES)


def test_library_uri_resolution_is_bounded_to_configured_root(tmp_path, monkeypatch) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    document = root / "book.pdf"
    document.write_bytes(b"pdf")
    monkeypatch.setenv("APRENDIX_LIBRARY_ESTUDO_FERIAS", str(root))
    assert resolve_library_uri("aprendix-library://estudo-ferias/book.pdf") == document.resolve()
    assert resolve_library_uri("aprendix-library://estudo-ferias/../private.txt") is None
    assert resolve_library_uri("https://example.test/book.pdf") is None
