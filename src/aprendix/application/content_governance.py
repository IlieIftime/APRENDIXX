"""Application service for source policy and curriculum coverage."""

from __future__ import annotations

from aprendix.application.contracts import AuthorityLevel, ContentSourceDTO


def _source(identity, domain, kinds, licence, parser="html-semantic-v1", authority=AuthorityLevel.PRIMARY):
    return ContentSourceDTO(
        id=identity, domain=domain, allowed_content_types=kinds,
        license_policy=licence,
        robots_policy="Respeitar robots.txt, cache HTTP e máximo de um pedido por segundo.",
        parser_version=parser,
        change_detection="ETag, Last-Modified, versão canónica e SHA-256",
        authority_level=authority,
    )


DEFAULT_TRUSTED_SOURCES = (
    _source("python-docs", "docs.python.org", ("documentation", "tutorial", "reference"),
            "Licença da documentação Python; preservar atribuição e versão."),
    _source("python-peps", "peps.python.org", ("standard",),
            "Licença PEP; preservar autoria, estado e versão.", "pep-html-v1"),
    _source("sqlite-docs", "sqlite.org", ("documentation", "reference"),
            "Documentação em domínio público; registar revisão da origem."),
    _source("postgres-docs", "postgresql.org", ("documentation", "reference"),
            "Licença PostgreSQL; preservar atribuição e versão."),
    _source("mdn", "developer.mozilla.org", ("documentation", "reference"),
            "Guardar apenas transformação permitida com atribuição.", authority=AuthorityLevel.REVIEWED),
    _source("django-docs", "docs.djangoproject.com", ("documentation", "tutorial", "reference"),
            "Licença da documentação Django; preservar atribuição e versão.", "django-docs-v1"),
    _source("fastapi-docs", "fastapi.tiangolo.com", ("documentation", "tutorial"),
            "Licença MIT da origem; preservar atribuição."),
    _source("scikit-learn-docs", "scikit-learn.org", ("documentation", "example", "reference"),
            "Licença BSD do projeto; preservar atribuição e versão.", "sphinx-v1"),
    _source("pytorch-docs", "pytorch.org", ("documentation", "tutorial", "reference"),
            "Licença da documentação do projeto; preservar atribuição e versão.", "sphinx-v1"),
    _source("flask-docs", "flask.palletsprojects.com", ("documentation", "tutorial", "reference"),
            "Aplicar a licença publicada pela origem e preservar atribuição e versão.", "sphinx-v1"),
    _source("sqlalchemy-docs", "docs.sqlalchemy.org", ("documentation", "tutorial", "reference"),
            "Aplicar a licença publicada pela origem e preservar atribuição e versão.", "sphinx-v1"),
    _source("pytest-docs", "docs.pytest.org", ("documentation", "tutorial", "reference"),
            "Aplicar a licença publicada pela origem e preservar atribuição e versão.", "sphinx-v1"),
    _source("mongodb-docs", "www.mongodb.com", ("documentation", "tutorial", "reference"),
            "Guardar apenas metadata e transformações autorizadas, com atribuição e versão.", "mongodb-docs-v1"),
    _source("git-docs", "git-scm.com", ("documentation", "reference"),
            "Aplicar a licença publicada pela origem e preservar autoria e versão.", "git-docs-v1"),
    _source("docker-docs", "docs.docker.com", ("documentation", "tutorial", "reference"),
            "Guardar apenas metadata e transformações autorizadas, com atribuição e versão.", "docker-docs-v1"),
    _source("python-packaging", "packaging.python.org", ("documentation", "tutorial", "standard", "reference"),
            "Aplicar a licença PyPA da origem e preservar atribuição e versão.", "sphinx-v1"),
    _source("numpy-docs", "numpy.org", ("documentation", "tutorial", "reference"),
            "Aplicar a licença publicada pela origem e preservar atribuição e versão.", "sphinx-v1"),
    _source("pandas-docs", "pandas.pydata.org", ("documentation", "tutorial", "reference"),
            "Aplicar a licença publicada pela origem e preservar atribuição e versão.", "sphinx-v1"),
)


class ContentGovernanceService:
    def __init__(self, repository, *, on_content_changed=None) -> None:
        self._repository = repository
        self._on_content_changed = on_content_changed or (lambda: None)

    def initialize(self) -> None:
        self._repository.seed_sources(DEFAULT_TRUSTED_SOURCES)
        self._repository.backfill_existing_revisions()

    def sources(self): return self._repository.sources()
    def refresh_objective_evidence(self):
        return self._repository.refresh_objective_evidence()
    def refresh_coverage(self): return self._repository.refresh_coverage()
    def coverage(self, *, gaps_only: bool = False):
        return self._repository.coverage(gaps_only=gaps_only)
    def rollback(self, logical_source: str, sequence: int):
        result = self._repository.rollback(logical_source, sequence)
        self._on_content_changed()
        return result
