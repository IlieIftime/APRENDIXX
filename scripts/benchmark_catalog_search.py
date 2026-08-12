"""Run the versioned whole-catalog retrieval holdout locally."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from aprendix.application.search_holdout import CatalogSearchBenchmark
from aprendix.infrastructure.curriculum import CurriculumRepository
from aprendix.infrastructure.db import (
    Database,
    DatabaseConfig,
    KnowledgeRepository,
    KnowledgeStructureRepository,
    PedagogicalRepository,
)
from aprendix.infrastructure.security import AesGcmFieldCipher, FileKeyStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    database = Database(DatabaseConfig(args.database))
    database.initialize()
    cipher = AesGcmFieldCipher.from_key_store(FileKeyStore(args.key))
    pedagogy = PedagogicalRepository(database, cipher)
    if args.seed:
        KnowledgeStructureRepository(database, cipher).seed()
        CurriculumRepository(database, cipher).seed()
        KnowledgeRepository(database, cipher).seed_authored_facts()
    counts = pedagogy.rebuild_catalog_search()
    benchmark = CatalogSearchBenchmark(pedagogy)
    result = benchmark.run()
    benchmark.persist(result)
    payload = {"catalog": counts, "benchmark": asdict(result)}
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

