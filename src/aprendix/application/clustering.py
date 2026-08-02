"""Offline taxonomy classification and stable HDBSCAN cluster orchestration."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from aprendix.application.contracts import LearningTheme, Technology


@dataclass(frozen=True, slots=True)
class ClusterInput:
    chunk_id: UUID
    title: str
    text: str
    embedding: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ClusterAssignment:
    chunk_id: UUID
    cluster_id: str
    probability: float
    technologies: tuple[Technology, ...]
    themes: tuple[LearningTheme, ...]


class ClusterStore(Protocol):
    def cluster_inputs(self) -> tuple[ClusterInput, ...]: ...
    def replace_clusters(self, assignments: tuple[ClusterAssignment, ...], labels: dict[str, str]) -> None: ...


class TaxonomyClassifier:
    """Deterministic, extensible metadata classifier; it never changes source text."""

    _TECHNOLOGIES = {
        Technology.PYTHON: ("python", "pip", "pydantic"),
        Technology.SQL: ("sql", "select ", "sqlite", "postgres", "mysql"),
        Technology.JAVA: ("java", "spring"),
        Technology.NOSQL: ("nosql", "mongodb", "redis", "cassandra"),
        Technology.DJANGO: ("django",), Technology.FASTAPI: ("fastapi",),
        Technology.FLASK: ("flask",), Technology.NUMPY: ("numpy",),
        Technology.PANDAS: ("pandas", "dataframe"), Technology.SCIPY: ("scipy",),
        Technology.SCIKIT_LEARN: ("scikit-learn", "sklearn"),
        Technology.PYTORCH: ("pytorch", "torch"),
        Technology.TENSORFLOW: ("tensorflow", "keras"),
        Technology.JUPYTER: ("jupyter", "notebook"),
        Technology.HTML: ("html",), Technology.CSS: (" css ", "stylesheet"),
        Technology.JAVASCRIPT: ("javascript", " node.js", " ecmascript", " js "),
        Technology.REACT: ("react", "jsx"), Technology.BOOTSTRAP: ("bootstrap",),
        Technology.GO: ("golang", " go "),
    }
    _THEMES = {
        LearningTheme.OOP: ("oop", "poo", "class", "object", "inheritance", "heranca"),
        LearningTheme.ALGORITHMS: ("algorithm", "algorit", "recurs", "sort", "search"),
        LearningTheme.DATA_STRUCTURES: ("estrutura de dados", "list", "tuple", "stack", "queue", "tree", "graph"),
        LearningTheme.WEB: ("web", "http", "html", "css", "django", "react"),
        LearningTheme.DATA: ("dataframe", "analytics", "dados", "numpy", "pandas"),
        LearningTheme.AI: ("machine learning", "neural", "inteligencia artificial", "pytorch", "tensorflow"),
        LearningTheme.FINANCE: ("financ", "portfolio", "juros", "stock", "trading"),
        LearningTheme.GAMES: ("game", "jogo", "pygame"),
        LearningTheme.DEVOPS: ("docker", "deploy", "ci/cd", "kubernetes"),
        LearningTheme.DATABASES: ("database", "base de dados", "sql", "mongodb"),
    }

    @classmethod
    def classify(cls, text: str) -> tuple[tuple[Technology, ...], tuple[LearningTheme, ...]]:
        folded = " " + unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold() + " "
        technologies = tuple(item for item, aliases in cls._TECHNOLOGIES.items() if any(alias in folded for alias in aliases))
        themes = tuple(item for item, aliases in cls._THEMES.items() if any(alias in folded for alias in aliases))
        if not technologies:
            technologies = (Technology.OTHER,)
        if not themes:
            themes = (LearningTheme.FUNDAMENTALS,)
        return technologies, themes


class HdbscanClusterService:
    """Run clustering as an explicit post-ingestion job, never on the GUI thread."""

    def __init__(self, store: ClusterStore, *, min_cluster_size: int = 5) -> None:
        self._store = store
        self._minimum = max(2, min_cluster_size)

    def rebuild(self) -> tuple[ClusterAssignment, ...]:
        items = self._store.cluster_inputs()
        if not items:
            self._store.replace_clusters((), {})
            return ()
        labels, probabilities = self._fit([item.embedding for item in items])
        members: dict[int, list[int]] = defaultdict(list)
        for index, label in enumerate(labels):
            members[int(label)].append(index)
        stable_ids: dict[int, str] = {}
        display_labels: dict[str, str] = {}
        for label, indices in members.items():
            if label == -1:
                cluster_id = "noise"
                display = "Sem cluster"
            else:
                identity = "|".join(sorted(str(items[index].chunk_id) for index in indices))
                cluster_id = "cluster-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
                tags: list[str] = []
                for index in indices:
                    tech, themes = TaxonomyClassifier.classify(f"{items[index].title} {items[index].text}")
                    tags.extend([value.value for value in tech if value is not Technology.OTHER])
                    tags.extend([value.value for value in themes if value is not LearningTheme.OTHER])
                display = " · ".join(value for value, _count in Counter(tags).most_common(2)) or "Tópico local"
            stable_ids[label] = cluster_id
            display_labels[cluster_id] = display
        assignments = []
        for index, item in enumerate(items):
            technologies, themes = TaxonomyClassifier.classify(f"{item.title} {item.text}")
            assignments.append(ClusterAssignment(
                chunk_id=item.chunk_id, cluster_id=stable_ids[int(labels[index])],
                probability=max(0.0, min(1.0, float(probabilities[index]))),
                technologies=technologies, themes=themes,
            ))
        result = tuple(assignments)
        self._store.replace_clusters(result, display_labels)
        return result

    def _fit(self, embeddings: list[tuple[int, ...]]) -> tuple[list[int], list[float]]:
        if len(embeddings) < self._minimum * 2:
            return [-1] * len(embeddings), [0.0] * len(embeddings)
        try:
            import numpy as np
            from sklearn.cluster import HDBSCAN
            from sklearn.decomposition import PCA
            from sklearn.preprocessing import normalize
        except ImportError as exc:
            raise RuntimeError('HDBSCAN requer o extra "cluster-build".') from exc
        matrix = np.asarray(embeddings, dtype=np.float32)
        components = min(48, matrix.shape[1], max(2, matrix.shape[0] - 1))
        reduced = PCA(n_components=components, random_state=0).fit_transform(matrix)
        reduced = normalize(reduced)
        model = HDBSCAN(
            min_cluster_size=self._minimum,
            min_samples=max(2, self._minimum // 3),
            metric="euclidean", algorithm="auto", leaf_size=80,
            cluster_selection_method="eom", n_jobs=1,
            copy=False,
        ).fit(reduced)
        return model.labels_.tolist(), model.probabilities_.tolist()
